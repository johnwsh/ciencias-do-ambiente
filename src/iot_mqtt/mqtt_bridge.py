"""
Ponte Ciber-Física (MQTT / JSONL) para integração entre:
- Engenharia Elétrica/Automação (Sensores virtuais IoT / Wokwi / Node-RED / Eclipse Mosquitto)
- Engenharia de Computação (Gerenciador Semafórico TraCI/SUMO)
- Engenharia Mecânica (Modelo Cinemático de Emissões e Acústica)

Implementa exatamente o Contrato de Dados JSON especificado na Seção 5.2 do Manual do Projeto.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


class CyberPhysicalTelemetryBridge:
    def __init__(
        self,
        output_jsonl_path: Path,
        broker_host: str = "localhost",
        broker_port: int = 1883,
        enable_mqtt: bool = False,
        base_datetime_iso: str = "2026-08-21T17:00:00Z",
    ) -> None:
        self.output_jsonl_path = output_jsonl_path
        self.output_jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        if self.output_jsonl_path.exists():
            self.output_jsonl_path.unlink()

        self.enable_mqtt = enable_mqtt
        self.mqtt_client = None
        self.base_dt = datetime.fromisoformat(base_datetime_iso.replace("Z", "+00:00"))

        if self.enable_mqtt:
            try:
                import paho.mqtt.client as mqtt
                client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="sumo_traci_curitiba")
                client.connect_async(broker_host, broker_port, keepalive=60)
                client.loop_start()
                self.mqtt_client = client
            except Exception as exc:
                print(f"[MQTT] Broker local indisponível ({exc}); gravando telemetria em arquivo JSONL.")
                self.mqtt_client = None

    def build_payload(
        self,
        sim_seconds: float,
        intersection_id: str,
        sensors_data: list[dict[str, Any]],
        queue_length_meters: float,
        co2_grams_per_second: float,
        nox_mg_per_second: float = 0.0,
        pmx_mg_per_second: float = 0.0,
        noise_dba: float = 65.0,
        waiting_time_seconds: float = 0.0,
        scenario: str = "as_is",
    ) -> dict[str, Any]:
        ts = (self.base_dt + timedelta(seconds=float(sim_seconds))).astimezone(timezone.utc)
        payload = {
            "timestamp": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "intersection_id": intersection_id,
            "scenario": scenario,
            "sensors": sensors_data,
            "instantaneous_metrics": {
                "queue_length_meters": round(float(queue_length_meters), 2),
                "co2_grams_per_second": round(float(co2_grams_per_second), 3),
                "nox_mg_per_second": round(float(nox_mg_per_second), 3),
                "pmx_mg_per_second": round(float(pmx_mg_per_second), 4),
                "noise_dba": round(float(noise_dba), 2),
                "waiting_time_seconds": round(float(waiting_time_seconds), 2),
            },
        }
        return payload

    def publish_telemetry(self, payload: dict[str, Any]) -> None:
        with open(self.output_jsonl_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")

        if self.mqtt_client is not None:
            topic = f"utfpr/curitiba/quadrilatero/{payload['intersection_id']}/telemetry"
            try:
                self.mqtt_client.publish(topic, json.dumps(payload), qos=0)
            except Exception:
                pass

    def close(self) -> None:
        if self.mqtt_client is not None:
            try:
                self.mqtt_client.loop_stop()
                self.mqtt_client.disconnect()
            except Exception:
                pass
