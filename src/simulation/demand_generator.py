"""
Gerador de Demanda Microscópica Multimodal para o SUMO sob diferentes Condições Iniciais:
- `pico_manha` (06:30 - 09:00)
- `pico_tarde` (17:00 - 19:00)
- `entre_pico` (12:00 - 14:00)
- `estresse_severo` (Sobrecarga de +40% / Chuva intensa)

Inclui:
1. Caracterização estatística da frota de Curitiba (Flex, Diesel Comercial, Híbrido/Elétrico,
   Motocicletas e Ônibus URBS/BRT) com classes de emissão HBEFA3 para cálculo de CO2, NOx, PM e ruído.
2. Rotas calibradas passando pelos 10 corredores monitorados do Quadrilátero Central + tráfego de fundo.
3. Re-roteamento automático caso a malha sofra intervenção de mudança de mão de direção (Cenário To-Be).
"""

from __future__ import annotations

import json
import random
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import sumolib
import yaml

ROOT_DIR = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT_DIR / "config" / "study_area.yaml"
NET_DIR = ROOT_DIR / "data" / "network"
ROUTES_DIR = ROOT_DIR / "data" / "routes"


# Definição dos tipos de veículos da frota de Curitiba (compatível com HBEFA3 do SUMO)
CURITIBA_VTYPES = [
    {
        "id": "passenger_flex",
        "vClass": "passenger",
        "emissionClass": "HBEFA3/PC_G_EU4",
        "guiShape": "passenger",
        "length": "4.5",
        "minGap": "2.2",
        "accel": "2.6",
        "decel": "4.5",
        "sigma": "0.5",
        "maxSpeed": "16.67",
        "color": "70,130,180",
    },
    {
        "id": "commercial_diesel",
        "vClass": "delivery",
        "emissionClass": "HBEFA3/LDV_D_EU4",
        "guiShape": "delivery",
        "length": "6.2",
        "minGap": "2.5",
        "accel": "1.9",
        "decel": "4.0",
        "sigma": "0.5",
        "maxSpeed": "13.89",
        "color": "210,140,60",
    },
    {
        "id": "hybrid_electric",
        "vClass": "passenger",
        "emissionClass": "HBEFA3/PC_Alternative",
        "guiShape": "passenger/sedan",
        "length": "4.6",
        "minGap": "2.0",
        "accel": "2.8",
        "decel": "4.5",
        "sigma": "0.4",
        "maxSpeed": "16.67",
        "color": "46,204,113",
    },
    {
        "id": "motorcycle",
        "vClass": "motorcycle",
        "emissionClass": "HBEFA3/PC_G_EU3",
        "guiShape": "motorcycle",
        "length": "2.2",
        "minGap": "1.5",
        "accel": "3.5",
        "decel": "5.0",
        "sigma": "0.6",
        "maxSpeed": "18.00",
        "color": "241,196,15",
    },
    {
        "id": "urbs_bus_brt",
        "vClass": "bus",
        "emissionClass": "HBEFA3/Bus",
        "guiShape": "bus/flexible",
        "length": "15.0",
        "minGap": "3.0",
        "accel": "1.4",
        "decel": "3.5",
        "sigma": "0.3",
        "maxSpeed": "13.89",
        "personCapacity": "160",
        "color": "231,76,60",
    },
]


def load_config() -> dict[str, Any]:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _build_corridor_paths(
    net: sumolib.net.Net,
    target_edge_id: str,
    max_paths: int = 8,
) -> list[list[str]]:
    """
    Constrói rotas válidas e conectadas que atravessam `target_edge_id`,
    expandindo para montante (incoming) e para jusante (outgoing) na malha do SUMO.
    """
    try:
        center_edge = net.getEdge(target_edge_id)
    except KeyError:
        return []

    # Expandir alguns saltos para trás (upstream) e para frente (downstream)
    upstream_Lists: list[list[sumolib.net.edge.Edge]] = [[center_edge]]
    for _ in range(3):
        new_up = []
        for path in upstream_Lists:
            first = path[0]
            inc = [
                e for e in first.getIncoming().keys()
                if not e.isSpecial() and e.allows("passenger") and e not in path
            ]
            if inc:
                for prev_e in inc[:3]:
                    new_up.append([prev_e] + path)
            else:
                new_up.append(path)
        upstream_Lists = new_up[:max_paths]

    full_paths: list[list[str]] = []
    for path in upstream_Lists:
        curr_paths = [path]
        for _ in range(3):
            next_list = []
            for p in curr_paths:
                last = p[-1]
                out = [
                    e for e in last.getOutgoing().keys()
                    if not e.isSpecial() and e.allows("passenger") and e not in p
                ]
                if out:
                    for nxt_e in out[:3]:
                        next_list.append(p + [nxt_e])
                else:
                    next_list.append(p)
            curr_paths = next_list[:max_paths]
        for p in curr_paths:
            edge_ids = [e.getID() for e in p]
            if edge_ids not in full_paths:
                full_paths.append(edge_ids)
            if len(full_paths) >= max_paths:
                return full_paths

    return full_paths if full_paths else [[target_edge_id]]


def generate_routes_for_condition(
    condition_key: str = "pico_tarde",
    net_path: Path | None = None,
    seed: int = 42,
    duration_override: int | None = None,
    demand_multiplier: float = 1.0,
    output_rou_path: Path | None = None,
) -> Path:
    """
    Gera o arquivo `.rou.xml` com os veículos ordenados por instante de partida (`depart`)
    para a condição inicial escolhida.
    """
    config = load_config()
    if condition_key not in config["initial_conditions"]:
        raise ValueError(f"Condição inicial inválida: {condition_key}. Opções: {list(config['initial_conditions'].keys())}")

    cond_cfg = config["initial_conditions"][condition_key]
    duration_s = duration_override or int(cond_cfg["duration_seconds"])
    modal_split: dict[str, float] = cond_cfg["modal_split"]

    if net_path is None:
        net_path = NET_DIR / "curitiba_as_is.net.xml"
    net = sumolib.net.readNet(str(net_path))

    mapping_path = NET_DIR / "monitored_points_mapping.json"
    if not mapping_path.exists():
        from src.simulation.sensor_placer import generate_sensors_and_mapping
        generate_sensors_and_mapping(net_path)
    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))

    rng = random.Random(seed)
    vtype_keys = [k for k in modal_split.keys() if k != "urbs_bus_brt"]
    vtype_weights = [modal_split[k] for k in vtype_keys]

    vph_col = f"vph_{condition_key}"
    vehicles_to_write: list[dict[str, Any]] = []
    veh_counter = 0

    for pt in mapping["points"]:
        point_id = pt["point_id"]
        edge_id = pt["edge_id"]
        target_vph = float(pt.get(vph_col, pt["vph_pico_tarde"])) * demand_multiplier
        bus_vph = float(pt.get("bus_per_hour_pico", 30)) * demand_multiplier

        paths = _build_corridor_paths(net, edge_id, max_paths=8)
        if not paths:
            # Se a aresta foi removida ou invertida num cenário To-Be, buscar alternativa no mesmo corredor
            from src.simulation.sensor_placer import find_candidate_edges_for_corridor
            alt_edges = find_candidate_edges_for_corridor(net, pt["corridor"])
            if alt_edges:
                paths = _build_corridor_paths(net, alt_edges[0].getID(), max_paths=6)
        if not paths:
            continue

        # Número esperado de veículos durante a janela `duration_s`
        # Usamos fator de escala microscópica (0.45) porque as rotas de múltiplos pontos compartilham vias adjacentes
        effective_vph = target_vph * 0.45
        num_cars = max(int((effective_vph * duration_s) / 3600.0), 10)
        num_buses = max(int((bus_vph * duration_s) / 3600.0), 2)

        for _ in range(num_cars):
            veh_counter += 1
            depart_t = round(rng.uniform(0.0, float(duration_s - 60)), 2)
            vtype = rng.choices(vtype_keys, weights=vtype_weights, k=1)[0]
            chosen_path = rng.choice(paths)
            vehicles_to_write.append({
                "id": f"veh_{point_id}_{veh_counter}",
                "type": vtype,
                "depart": depart_t,
                "edges": " ".join(chosen_path),
            })

        # Injetar ônibus da URBS regularmente espaçados no corredor
        bus_interval = max(duration_s / float(num_buses), 15.0)
        for b_idx in range(num_buses):
            veh_counter += 1
            depart_t = round(min(b_idx * bus_interval + rng.uniform(0.0, 8.0), duration_s - 30.0), 2)
            chosen_path = paths[b_idx % len(paths)]
            vehicles_to_write.append({
                "id": f"urbs_bus_{point_id}_{veh_counter}",
                "type": "urbs_bus_brt",
                "depart": max(0.0, depart_t),
                "edges": " ".join(chosen_path),
            })

    # Ordenar estritamente por tempo de partida (exigência do SUMO)
    vehicles_to_write.sort(key=lambda x: x["depart"])

    ROUTES_DIR.mkdir(parents=True, exist_ok=True)
    if output_rou_path is None:
        output_rou_path = ROUTES_DIR / f"curitiba_{condition_key}_seed{seed}.rou.xml"

    root = ET.Element("routes")
    for vt in CURITIBA_VTYPES:
        ET.SubElement(root, "vType", vt)

    for v in vehicles_to_write:
        veh_el = ET.SubElement(
            root,
            "vehicle",
            {
                "id": v["id"],
                "type": v["type"],
                "depart": f"{v['depart']:.2f}",
                "departLane": "best",
                "departSpeed": "max",
            },
        )
        ET.SubElement(veh_el, "route", {"edges": v["edges"]})

    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    tree.write(output_rou_path, encoding="utf-8", xml_declaration=True)
    print(
        f"[DEMAND] Condição '{condition_key}' (seed={seed}): "
        f"{len(vehicles_to_write)} veículos gerados -> {output_rou_path}"
    )
    return output_rou_path


def generate_all_initial_conditions(seed: int = 42, duration_override: int | None = None) -> dict[str, Path]:
    config = load_config()
    generated: dict[str, Path] = {}
    for cond_key in config["initial_conditions"].keys():
        generated[cond_key] = generate_routes_for_condition(
            condition_key=cond_key,
            seed=seed,
            duration_override=duration_override,
        )
    return generated


if __name__ == "__main__":
    generate_all_initial_conditions()
