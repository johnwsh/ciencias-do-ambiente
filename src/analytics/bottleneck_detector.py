"""
Detector e Classificador de Gargalos de Trânsito (Bottleneck Severity Index - BSI)
e Comparador Quantitativo de Cenários (As-Is vs. To-Be).

Integra as métricas de:
1. Engenharia de Computação: Fluxo veicular (veh/h), tamanho de fila (m), atraso médio (s),
   velocidade média (km/h) e taxa de ocupação dos sensores (%).
2. Engenharia Mecânica / Ambiental: Emissões cinemáticas instantâneas e acumuladas
   (CO2, NOx, CO, PMx via HBEFA3) e nível de pressão sonora equivalente Leq em dB(A) (CoRTN / Harmonoise).
"""

from __future__ import annotations

import math
from typing import Any

import pandas as pd


def estimate_cortn_noise_dba(
    flow_vph: float,
    heavy_bus_pct: float,
    mean_speed_kmh: float,
    stop_and_go_queue_m: float,
) -> float:
    """
    Estima o nível de pressão sonora equivalente Leq em dB(A) segundo o modelo CoRTN / FHWA
    adaptado para vias urbanas arteriais com efeito de aceleração "para-e-anda" em semáforos.
    """
    q = max(float(flow_vph), 50.0)
    v = max(float(mean_speed_kmh), 8.0)
    p = min(max(float(heavy_bus_pct), 1.0), 40.0)

    # Termo base logarítmico de volume horário (CoRTN L10/Leq a 10m da faixa)
    base_leq = 42.2 + 10.0 * math.log10(q)
    # Correção por veículos pesados (ônibus URBS diesel/biodiesel e caminhões leves) e velocidade
    heavy_corr = 33.0 * math.log10(v + 40.0 + (500.0 / v)) + 10.0 * math.log10(1.0 + (5.0 * p) / v) - 68.8
    # Penalidade acústica de ciclos de frenagem/arrancada ("para-e-anda" em filas de semáforo)
    stop_go_penalty = min(stop_and_go_queue_m / 18.0, 4.2)

    return round(base_leq + heavy_corr + stop_go_penalty, 2)


def compute_bottleneck_ranking(metrics_df: pd.DataFrame) -> pd.DataFrame:
    """
    Calcula o Índice de Severidade de Gargalo (BSI: 0 a 100) para cada ponto monitorado
    e ordena do gargalo mais crítico para o menos crítico.
    """
    df = metrics_df.copy()

    bsi_scores = []
    classifications = []
    diagnoses = []

    for _, row in df.iterrows():
        q_norm = min(float(row["max_queue_m"]) / 75.0, 1.0)
        w_norm = min(float(row["avg_wait_s"]) / 55.0, 1.0)
        speed_limit = max(float(row.get("speed_limit_kmh", 40.0)), 20.0)
        speed_drop = max(0.0, min(1.0 - (float(row["avg_speed_kmh"]) / speed_limit), 1.0))
        occ_norm = min(float(row["avg_occupancy_pct"]) / 45.0, 1.0)

        bsi = 100.0 * (0.32 * q_norm + 0.28 * w_norm + 0.22 * speed_drop + 0.18 * occ_norm)
        bsi = round(min(max(bsi, 0.0), 100.0), 1)
        bsi_scores.append(bsi)

        if bsi >= 62.0:
            classifications.append("CRÍTICO (Gargalo Severo)")
            diagnoses.append(
                f"Saturação semafórica e fila extensa ({row['max_queue_m']:.1f}m). "
                "Recomendado: Controle adaptativo TraCI + Onda Verde e faixa exclusiva/reversível."
            )
        elif bsi >= 42.0:
            classifications.append("ALERTA (Saturação Moderada)")
            diagnoses.append(
                f"Retenção moderada ({row['avg_wait_s']:.1f}s de espera). "
                "Recomendado: Ajuste de defasagem semafórica e priorização de ônibus URBS."
            )
        else:
            classifications.append("NORMAL (Fluxo Fluido)")
            diagnoses.append("Capacidade viária compatível com a demanda atual.")

    df["bsi_score"] = bsi_scores
    df["bottleneck_status"] = classifications
    df["engineering_diagnosis"] = diagnoses
    df = df.sort_values(by="bsi_score", ascending=False).reset_index(drop=True)
    df["bottleneck_rank"] = df.index + 1
    return df


def compare_as_is_vs_to_be(as_is_df: pd.DataFrame, to_be_df: pd.DataFrame) -> dict[str, Any]:
    """
    Compara quantitativamente o cenário de referência (As-Is) com o cenário pós-intervenção (To-Be)
    ponto a ponto e em termos agregados na malha.
    """
    merged = pd.merge(
        as_is_df,
        to_be_df,
        on=["point_id", "corridor", "intersection_name"],
        suffixes=("_as_is", "_to_be"),
    )

    merged["queue_reduction_pct"] = (
        (merged["max_queue_m_as_is"] - merged["max_queue_m_to_be"])
        / merged["max_queue_m_as_is"].clip(lower=1.0)
        * 100.0
    ).round(1)

    merged["wait_reduction_pct"] = (
        (merged["avg_wait_s_as_is"] - merged["avg_wait_s_to_be"])
        / merged["avg_wait_s_as_is"].clip(lower=1.0)
        * 100.0
    ).round(1)

    merged["speed_gain_pct"] = (
        (merged["avg_speed_kmh_to_be"] - merged["avg_speed_kmh_as_is"])
        / merged["avg_speed_kmh_as_is"].clip(lower=1.0)
        * 100.0
    ).round(1)

    merged["co2_reduction_pct"] = (
        (merged["co2_kg_per_hour_as_is"] - merged["co2_kg_per_hour_to_be"])
        / merged["co2_kg_per_hour_as_is"].clip(lower=0.1)
        * 100.0
    ).round(1)

    merged["noise_reduction_dba"] = (
        merged["noise_leq_dba_as_is"] - merged["noise_leq_dba_to_be"]
    ).round(2)

    merged["bsi_delta"] = (merged["bsi_score_to_be"] - merged["bsi_score_as_is"]).round(1)

    summary = {
        "avg_queue_reduction_pct": round(float(merged["queue_reduction_pct"].mean()), 1),
        "avg_wait_reduction_pct": round(float(merged["wait_reduction_pct"].mean()), 1),
        "avg_speed_gain_pct": round(float(merged["speed_gain_pct"].mean()), 1),
        "total_co2_as_is_kg_h": round(float(merged["co2_kg_per_hour_as_is"].sum()), 2),
        "total_co2_to_be_kg_h": round(float(merged["co2_kg_per_hour_to_be"].sum()), 2),
        "total_co2_reduction_pct": round(
            float(
                (merged["co2_kg_per_hour_as_is"].sum() - merged["co2_kg_per_hour_to_be"].sum())
                / max(float(merged["co2_kg_per_hour_as_is"].sum()), 0.1)
                * 100.0
            ),
            1,
        ),
        "total_nox_reduction_pct": round(
            float(
                (merged["nox_g_per_hour_as_is"].sum() - merged["nox_g_per_hour_to_be"].sum())
                / max(float(merged["nox_g_per_hour_as_is"].sum()), 0.1)
                * 100.0
            ),
            1,
        ),
        "total_pmx_reduction_pct": round(
            float(
                (merged["pmx_g_per_hour_as_is"].sum() - merged["pmx_g_per_hour_to_be"].sum())
                / max(float(merged["pmx_g_per_hour_as_is"].sum()), 0.1)
                * 100.0
            ),
            1,
        ),
        "avg_noise_reduction_dba": round(float(merged["noise_reduction_dba"].mean()), 2),
        "critical_bottlenecks_as_is": int((merged["bsi_score_as_is"] >= 62.0).sum()),
        "critical_bottlenecks_to_be": int((merged["bsi_score_to_be"] >= 62.0).sum()),
        "comparison_table": merged,
    }
    return summary
