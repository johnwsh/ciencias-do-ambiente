"""
Posicionamento automático de Sensores Virtuais (Laços Indutivos E1 e Detectores de Fila/Área E2)
na malha viária do SUMO para medir fluxo de veículos, tamanho de filas, ocupação e velocidade
em pontos estratégicos do Quadrilátero Central de Curitiba.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import pandas as pd
import sumolib

ROOT_DIR = Path(__file__).resolve().parents[2]
NET_DIR = ROOT_DIR / "data" / "network"
PROCESSED_DIR = ROOT_DIR / "data" / "processed"


def find_candidate_edges_for_corridor(net: sumolib.net.Net, corridor_name: str) -> list[sumolib.net.edge.Edge]:
    """
    Busca na malha do SUMO as arestas (edges) pertencentes ao corredor informado,
    ordenadas por proximidade de semáforo, número de faixas e comprimento.
    """
    tokens = [t.lower() for t in corridor_name.split() if len(t) > 3]
    candidates = []
    for edge in net.getEdges():
        if edge.isSpecial():
            continue
        if not edge.allows("passenger") and not edge.allows("bus"):
            continue
        name = (edge.getName() or "").lower()
        if not name:
            continue
        if corridor_name.lower() in name or (tokens and all(tok in name for tok in tokens[-2:])):
            candidates.append(edge)

    def score_edge(e: sumolib.net.edge.Edge) -> tuple[int, int, float]:
        has_tls = 1 if e.getToNode().getType() in ("traffic_light", "traffic_light_unregulated") else 0
        return (has_tls, e.getLaneNumber(), e.getLength())

    return sorted(candidates, key=score_edge, reverse=True)


def generate_sensors_and_mapping(net_path: Path | None = None) -> dict[str, Any]:
    if net_path is None:
        net_path = NET_DIR / "curitiba_as_is.net.xml"

    net = sumolib.net.readNet(str(net_path), withPrograms=True)
    counts_df = pd.read_csv(PROCESSED_DIR / "reference_counts_ippuc_urbs.csv")

    used_edge_ids: set[str] = set()
    monitored_points: list[dict[str, Any]] = []

    additional_root = ET.Element("additional")

    for _, row in counts_df.iterrows():
        point_id = str(row["point_id"])
        corridor = str(row["corridor"])
        candidates = find_candidate_edges_for_corridor(net, corridor)

        chosen_edge = None
        for cand in candidates:
            if cand.getID() not in used_edge_ids and cand.getLength() >= 20.0:
                chosen_edge = cand
                break
        if chosen_edge is None and candidates:
            chosen_edge = candidates[0]

        if chosen_edge is None:
            # Fallback para qualquer aresta semaforizada longa ainda não usada
            fallback_edges = sorted(
                [e for e in net.getEdges() if not e.isSpecial() and e.allows("passenger") and e.getID() not in used_edge_ids],
                key=lambda x: (x.getLaneNumber(), x.getLength()),
                reverse=True,
            )
            chosen_edge = fallback_edges[0]

        used_edge_ids.add(chosen_edge.getID())

        # Coordenadas geográficas (centro da aresta)
        shape = chosen_edge.getShape()
        mid_x, mid_y = shape[len(shape) // 2]
        try:
            lon, lat = net.convertXY2LonLat(mid_x, mid_y)
        except Exception:
            lon, lat = -49.2695, -25.4310

        to_node = chosen_edge.getToNode()
        tls_id = to_node.getID() if to_node.getType() in ("traffic_light", "traffic_light_unregulated") else None

        lane_ids = []
        det_length = min(max(chosen_edge.getLength() - 2.0, 5.0), 80.0)
        det_pos = max(chosen_edge.getLength() - det_length - 0.5, 0.0)

        for lane in chosen_edge.getLanes():
            lane_id = lane.getID()
            lane_ids.append(lane_id)
            e2_id = f"e2_{point_id}_L{lane.getIndex()}"
            ET.SubElement(
                additional_root,
                "laneAreaDetector",
                {
                    "id": e2_id,
                    "lane": lane_id,
                    "pos": f"{det_pos:.2f}",
                    "length": f"{det_length:.2f}",
                    "freq": "60",
                    "file": "sensors_e2_output.xml",
                },
            )

        monitored_points.append({
            "point_id": point_id,
            "corridor": corridor,
            "intersection_name": str(row["intersection_name"]),
            "direction": str(row["direction"]),
            "edge_id": chosen_edge.getID(),
            "street_name_osm": chosen_edge.getName() or corridor,
            "num_lanes": chosen_edge.getLaneNumber(),
            "length_m": round(chosen_edge.getLength(), 2),
            "speed_limit_kmh": round(chosen_edge.getSpeed() * 3.6, 1),
            "tls_id": tls_id,
            "lat": round(lat, 6),
            "lon": round(lon, 6),
            "lanes": lane_ids,
            "vph_pico_manha": int(row["vph_pico_manha"]),
            "vph_pico_tarde": int(row["vph_pico_tarde"]),
            "vph_entre_pico": int(row["vph_entre_pico"]),
            "vph_estresse_severo": int(row["vph_estresse_severo"]),
            "bus_per_hour_pico": int(row["bus_per_hour_pico"]),
            "reference_speed_kmh": float(row["reference_speed_kmh"]),
            "reference_noise_leq_dba": float(row["reference_noise_leq_dba"]),
        })

    # Adicionar coletor global de métricas por via e emissões (HBEFA / Harmonoise)
    ET.SubElement(
        additional_root,
        "edgeData",
        {
            "id": "macro_traffic",
            "file": "edgedata_traffic.xml",
            "excludeEmpty": "true",
        },
    )
    ET.SubElement(
        additional_root,
        "edgeData",
        {
            "id": "macro_emissions",
            "type": "emissions",
            "file": "edgedata_emissions.xml",
            "excludeEmpty": "true",
        },
    )
    ET.SubElement(
        additional_root,
        "edgeData",
        {
            "id": "macro_noise",
            "type": "harmonoise",
            "file": "edgedata_noise.xml",
            "excludeEmpty": "true",
        },
    )

    sensors_xml_path = NET_DIR / "sensors.add.xml"
    tree = ET.ElementTree(additional_root)
    ET.indent(tree, space="  ")
    tree.write(sensors_xml_path, encoding="utf-8", xml_declaration=True)

    mapping_payload = {
        "network_file": str(net_path.name),
        "total_monitored_points": len(monitored_points),
        "points": monitored_points,
    }
    mapping_path = NET_DIR / "monitored_points_mapping.json"
    mapping_path.write_text(json.dumps(mapping_payload, indent=2, ensure_ascii=False), encoding="utf-8")

    # Exportar também as polilinhas WGS84 dos corredores para renderização no mapa interativo
    corridors_polylines: dict[str, list[list[list[float]]]] = {}
    unique_corridors = sorted({str(r["corridor"]) for _, r in counts_df.iterrows()})
    for corr_name in unique_corridors:
        edges = find_candidate_edges_for_corridor(net, corr_name)
        lines = []
        for e in edges[:25]:
            pts = []
            for x, y in e.getShape():
                try:
                    lon_p, lat_p = net.convertXY2LonLat(x, y)
                    pts.append([round(lat_p, 6), round(lon_p, 6)])
                except Exception:
                    continue
            if len(pts) >= 2:
                lines.append(pts)
        corridors_polylines[corr_name] = lines

    polylines_path = NET_DIR / "corridors_polylines.json"
    polylines_path.write_text(json.dumps(corridors_polylines, ensure_ascii=False), encoding="utf-8")

    print(f"[SENSORS] {len(monitored_points)} pontos instrumentados salvos em: {sensors_xml_path}")
    print(f"[SENSORS] Mapeamento de sensores e coordenadas salvo em: {mapping_path}")
    return mapping_payload


if __name__ == "__main__":
    generate_sensors_and_mapping()
