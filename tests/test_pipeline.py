"""
Testes automatizados de integridade do repositório Smart Mobility Curitiba (UTFPR):
1. Existência da malha SUMO (.net.xml) e catálogo de corredores do Quadrilátero Central.
2. Validação do Contrato de Dados JSON (Seção 5.2 do Manual) contra `schemas/integration_payload.schema.json`.
3. Validação estatística GEH (< 5.0 em >= 85% das vias monitoradas).
4. Verificação de melhoria quantitativa dos cenários To-Be frente ao cenário As-Is.
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pandas as pd

from src.analytics.geh_calibration import compute_geh

ROOT_DIR = Path(__file__).resolve().parents[1]


def test_network_and_catalog_exist() -> None:
    net_path = ROOT_DIR / "data" / "network" / "curitiba_as_is.net.xml"
    cat_path = ROOT_DIR / "data" / "network" / "network_catalog.json"
    assert net_path.exists(), "Malha SUMO As-Is não encontrada"
    assert cat_path.exists(), "Catálogo da malha não encontrado"
    cat = json.loads(cat_path.read_text(encoding="utf-8"))
    assert cat["total_edges"] > 50
    assert cat["total_traffic_lights"] > 10


def test_geh_formula_and_calibration() -> None:
    assert round(compute_geh(1800, 1750), 3) < 5.0
    master_csv = ROOT_DIR / "results" / "all_simulations_metrics.csv"
    assert master_csv.exists(), "Resultados de simulação não encontrados"
    df = pd.read_csv(master_csv)
    as_is_tarde = df[(df["condition"] == "pico_tarde") & (df["intervention"] == "as_is_baseline")]
    pass_rate = (as_is_tarde["geh"] < 5.0).mean()
    assert pass_rate >= 0.85, f"Critério GEH >= 85% não atendido: {pass_rate * 100:.1f}%"


def test_cyber_physical_json_contract() -> None:
    schema_path = ROOT_DIR / "schemas" / "integration_payload.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    telemetry_file = (
        ROOT_DIR
        / "results"
        / "runs"
        / "pico_tarde__as_is_baseline__seed42"
        / "cyber_physical_telemetry.jsonl"
    )
    assert telemetry_file.exists(), "Arquivo de telemetria JSONL não encontrado"
    first_line = telemetry_file.read_text(encoding="utf-8").splitlines()[0]
    payload = json.loads(first_line)
    jsonschema.validate(instance=payload, schema=schema)


def test_to_be_interventions_improve_bottlenecks() -> None:
    suite_path = ROOT_DIR / "results" / "experiment_suite_summary.json"
    suite = json.loads(suite_path.read_text(encoding="utf-8"))
    comps = suite["interventions_comparison_pico_tarde"]
    for int_key, metrics in comps.items():
        assert metrics["avg_queue_reduction_pct"] > 0, f"{int_key} não reduziu fila"
        assert metrics["avg_wait_reduction_pct"] > 0, f"{int_key} não reduziu atraso"
        assert metrics["total_co2_reduction_pct"] > 0, f"{int_key} não reduziu CO2"


def test_streamlit_dashboard_renders() -> None:
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(ROOT_DIR / "src" / "dashboard" / "app.py")).run(timeout=30)
    assert not at.exception, f"Erro ao renderizar Streamlit: {at.exception}"


if __name__ == "__main__":
    test_network_and_catalog_exist()
    test_geh_formula_and_calibration()
    test_cyber_physical_json_contract()
    test_to_be_interventions_improve_bottlenecks()
    test_streamlit_dashboard_renders()
    print("[TESTS] Todos os testes de engenharia e validação passaram com sucesso!")
