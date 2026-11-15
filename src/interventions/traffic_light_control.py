"""
Controlador Semafórico Dinâmico via API TraCI/Python para o Quadrilátero Central de Curitiba.

Modos suportados:
1. `fixed_baseline`: Operação estática original (Cenário As-Is).
2. `green_wave_optimized`: Re-temporização coordenada (Onda Verde) priorizando a fase arterial
   dos corredores de maior fluxo (Mariano Torres, Mal. Floriano, André de Barros, XV de Novembro).
3. `adaptive_traci_brt`: Controle adaptativo em malha fechada (Max-Pressure / Queue-Actuated)
   com Priorização Semafórica de Transporte Público (Transit Signal Priority - TSP) para ônibus URBS.
"""

from __future__ import annotations

from typing import Any

import traci


class TrafficLightController:
    def __init__(
        self,
        mode: str = "fixed_baseline",
        target_tls_ids: list[str] | None = None,
        min_green_s: float = 8.0,
        max_green_s: float = 52.0,
    ) -> None:
        self.mode = mode
        self.target_tls_ids = set(target_tls_ids or [])
        self.min_green_s = min_green_s
        self.max_green_s = max_green_s
        self.phase_start_time: dict[str, float] = {}
        self.last_phase: dict[str, int] = {}
        self.interventions_count: int = 0
        self.brt_priority_activations: int = 0
        self._controlled_links_cache: dict[str, list[Any]] = {}

    def initialize_on_simulation_start(self) -> None:
        """
        Configura os planos semafóricos iniciais assim que o TraCI conecta ao SUMO.
        """
        all_tls = list(traci.trafficlight.getIDList())
        if not self.target_tls_ids:
            self.target_tls_ids = set(all_tls)
        else:
            # Incluir tanto os TLS monitorados quanto os cruzamentos adjacentes dos corredores
            self.target_tls_ids = self.target_tls_ids.intersection(all_tls) or set(all_tls)

        for tls_id in all_tls:
            self.phase_start_time[tls_id] = 0.0
            self.last_phase[tls_id] = traci.trafficlight.getPhase(tls_id)
            try:
                self._controlled_links_cache[tls_id] = traci.trafficlight.getControlledLinks(tls_id)
            except Exception:
                self._controlled_links_cache[tls_id] = []

        if self.mode in ("green_wave_optimized", "adaptive_traci_brt"):
            self._apply_green_wave_re_timing(all_tls)

    def _apply_green_wave_re_timing(self, tls_ids: list[str]) -> None:
        """
        Ajusta os tempos de verde das fases principais nos semáforos da rede para favorecer
        o escoamento arterial (Onda Verde) e evitar bloqueio de cruzamentos a jusante.
        """
        for tls_id in tls_ids:
            try:
                logics = traci.trafficlight.getAllProgramLogics(tls_id)
                if not logics:
                    continue
                logic = logics[0]
                phases = list(logic.phases)
                if len(phases) < 2:
                    continue

                # Identificar a fase com maior número de movimentos verdes ('G' ou 'g')
                green_counts = [p.state.count("G") + p.state.count("g") for p in phases]
                max_green_links = max(green_counts) if green_counts else 0
                if max_green_links == 0:
                    continue

                for idx, phase in enumerate(phases):
                    is_yellow = "y" in phase.state.lower()
                    if is_yellow:
                        phase.duration = min(phase.duration, 3.0)
                        continue
                    g_score = green_counts[idx]
                    if g_score >= max_green_links * 0.75:
                        # Fase arterial principal: +35% de tempo de verde
                        phase.duration = min(max(phase.duration * 1.35, 28.0), 50.0)
                    else:
                        # Fase secundária: reduzir tempo ocioso excessivo
                        phase.duration = max(phase.duration * 0.75, 10.0)

                traci.trafficlight.setProgramLogic(tls_id, logic)
                self.interventions_count += 1
            except Exception:
                continue

    def step(self, sim_time: float) -> dict[str, Any]:
        """
        Executa um passo de controle em tempo real.
        Retorna estatísticas das atuações realizadas até o momento.
        """
        if self.mode == "fixed_baseline":
            return {
                "mode": self.mode,
                "interventions_count": self.interventions_count,
                "brt_priority_activations": self.brt_priority_activations,
            }

        # No modo Onda Verde estática, atuamos a cada 10s apenas para destravar fases ociosas
        if self.mode == "green_wave_optimized":
            if int(sim_time) % 10 == 0:
                self._skip_empty_phases(sim_time, enable_brt_priority=False)
            return {
                "mode": self.mode,
                "interventions_count": self.interventions_count,
                "brt_priority_activations": self.brt_priority_activations,
            }

        # No modo `adaptive_traci_brt`, atuamos a cada 4 segundos em malha fechada
        if int(sim_time) % 4 == 0:
            self._skip_empty_phases(sim_time, enable_brt_priority=True)

        return {
            "mode": self.mode,
            "interventions_count": self.interventions_count,
            "brt_priority_activations": self.brt_priority_activations,
        }

    def _skip_empty_phases(self, sim_time: float, enable_brt_priority: bool) -> None:
        """
        Avalia ocupação das faixas e presença de ônibus URBS em cada cruzamento semaforizado:
        - Se a fase verde atual está vazia e há fila ou ônibus URBS esperando no sinal vermelho,
          avança imediatamente para o próximo estágio.
        - Se a fase verde atual está escoando uma fila intensa ou um ônibus URBS, estende o verde.
        """
        for tls_id, links in self._controlled_links_cache.items():
            if not links:
                continue
            try:
                curr_phase = traci.trafficlight.getPhase(tls_id)
                if curr_phase != self.last_phase.get(tls_id, -1):
                    self.last_phase[tls_id] = curr_phase
                    self.phase_start_time[tls_id] = sim_time

                elapsed = sim_time - self.phase_start_time.get(tls_id, 0.0)
                if elapsed < self.min_green_s:
                    continue

                state = traci.trafficlight.getRedYellowGreenState(tls_id)
                if "y" in state.lower():
                    continue

                green_lanes: set[str] = set()
                red_lanes: set[str] = set()
                for idx, link_group in enumerate(links):
                    if idx >= len(state) or not link_group:
                        continue
                    in_lane = link_group[0][0]
                    sig = state[idx]
                    if sig in ("G", "g"):
                        green_lanes.add(in_lane)
                    elif sig in ("r", "R"):
                        red_lanes.add(in_lane)

                green_queue = sum(traci.lane.getLastStepHaltingNumber(l) for l in green_lanes)
                green_vehs = sum(traci.lane.getLastStepVehicleNumber(l) for l in green_lanes)
                red_queue = sum(traci.lane.getLastStepHaltingNumber(l) for l in red_lanes)

                bus_on_green = False
                bus_on_red = False
                if enable_brt_priority:
                    for l in green_lanes:
                        for vid in traci.lane.getLastStepVehicleIDs(l):
                            if "urbs_bus" in vid:
                                bus_on_green = True
                                break
                    for l in red_lanes:
                        for vid in traci.lane.getLastStepVehicleIDs(l):
                            if "urbs_bus" in vid:
                                bus_on_red = True
                                break

                # Caso 1: Ônibus URBS ou fila pesada na fase verde atual -> estender verde
                if (bus_on_green or green_queue >= 4) and elapsed < self.max_green_s:
                    traci.trafficlight.setPhaseDuration(tls_id, 8.0)
                    self.interventions_count += 1
                    if bus_on_green:
                        self.brt_priority_activations += 1

                # Caso 2: Fase verde ociosa enquanto há fila ou ônibus URBS esperando no vermelho -> avançar fase
                elif (green_vehs <= 1 and (red_queue >= 2 or bus_on_red)) or (
                    enable_brt_priority and bus_on_red and not bus_on_green and red_queue >= 3 and elapsed >= 14.0
                ):
                    traci.trafficlight.setPhaseDuration(tls_id, 0.5)
                    self.interventions_count += 1
                    if bus_on_red:
                        self.brt_priority_activations += 1
            except Exception:
                continue
