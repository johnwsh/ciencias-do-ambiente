"""
Validação Estatística e Calibração por Índice GEH (Geoffrey E. Havers)
conforme exigido na Fase 2 (Marco 2 - M2) e Rubrica 6.1 do Manual do Projeto UTFPR.

Fórmula:
    GEH = sqrt( (2 * (M - C)^2) / (M + C) )
Onde:
    M = Volume horário simulado no modelo microscópico (veículos/hora)
    C = Volume horário real contado / referência IPPUC-URBS (veículos/hora)

Critério de Aceitação (FHWA / Manual UTFPR):
    - GEH < 5.0 para pelo menos 85% das vias monitoradas -> Modelo Calibrado (VÁLIDO)
    - 5.0 <= GEH < 10.0 -> Requer atenção / ajuste fino de matriz OD
    - GEH >= 10.0 -> Inconsistência estatística
"""

from __future__ import annotations

import math
from typing import Any

import pandas as pd


def compute_geh(simulated_vph: float, observed_vph: float) -> float:
    denom = float(simulated_vph) + float(observed_vph)
    if denom <= 0.0:
        return 0.0
    return math.sqrt((2.0 * ((float(simulated_vph) - float(observed_vph)) ** 2)) / denom)


def classify_geh(geh_value: float) -> str:
    if geh_value < 5.0:
        return "CALIBRADO (GEH < 5)"
    if geh_value < 10.0:
        return "ACEITÁVEL PARCIAL (5 <= GEH < 10)"
    return "RECALIBRAR (GEH >= 10)"


def evaluate_network_calibration(points_df: pd.DataFrame) -> dict[str, Any]:
    """
    Recebe um DataFrame contendo `point_id`, `corridor`, `simulated_vph` e `reference_vph`
    e calcula a estatística GEH individual e global da malha.
    """
    df = points_df.copy()
    df["geh"] = [
        round(compute_geh(m, c), 3)
        for m, c in zip(df["simulated_vph"], df["reference_vph"])
    ]
    df["geh_status"] = [classify_geh(g) for g in df["geh"]]
    df["geh_passed"] = df["geh"] < 5.0

    passed_ratio = float(df["geh_passed"].mean()) if len(df) > 0 else 0.0
    mean_geh = float(df["geh"].mean()) if len(df) > 0 else 0.0
    max_geh = float(df["geh"].max()) if len(df) > 0 else 0.0

    return {
        "total_points": len(df),
        "points_passing_geh_lt_5": int(df["geh_passed"].sum()),
        "passing_percentage": round(passed_ratio * 100.0, 1),
        "meets_utfpr_85pct_criterion": passed_ratio >= 0.85,
        "mean_geh": round(mean_geh, 3),
        "max_geh": round(max_geh, 3),
        "calibrated_table": df,
    }
