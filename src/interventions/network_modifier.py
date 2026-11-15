"""
Modificador de Malha Viária para Testes de Intervenção Física/Operacional (Cenário To-Be):
- Inversão de mão de direção de ruas/arestas (`reverse_edge_ids`)
- Transformação de estacionamento/faixa lateral em faixa de rolamento ou faixa exclusiva nos gargalos (`expand_lanes_on_corridors`)
- Ajuste de velocidade operacional nos corredores sincronizados (`corridor_speed_ms`)

Utiliza o `netconvert` do SUMO aplicando patches XML sobre a malha base (`curitiba_as_is.net.xml`)
e recomputando automaticamente as conexões de cruzamentos e semáforos em `curitiba_to_be.net.xml`.
"""

from __future__ import annotations

import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import sumolib
import yaml

ROOT_DIR = Path(__file__).resolve().parents[2]
INTERVENTIONS_CFG_PATH = ROOT_DIR / "config" / "interventions.yaml"
NET_DIR = ROOT_DIR / "data" / "network"


def load_interventions_config() -> dict[str, Any]:
    with open(INTERVENTIONS_CFG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_modified_network(
    base_net_path: Path | None = None,
    output_net_path: Path | None = None,
    expand_lanes_on_corridors: list[str] | None = None,
    reverse_edge_ids: list[str] | None = None,
    corridor_speed_ms: dict[str, float] | None = None,
) -> dict[str, Any]:
    """
    Aplica modificações pontuais na malha viária (mão de direção, número de faixas e velocidade)
    e compila a malha `curitiba_to_be.net.xml` via `netconvert`.
    """
    if base_net_path is None:
        base_net_path = NET_DIR / "curitiba_as_is.net.xml"
    if output_net_path is None:
        output_net_path = NET_DIR / "curitiba_to_be.net.xml"

    expand_lanes_on_corridors = expand_lanes_on_corridors or []
    reverse_edge_ids = reverse_edge_ids or []
    corridor_speed_ms = corridor_speed_ms or {}

    net = sumolib.net.readNet(str(base_net_path))
    edges_root = ET.Element("edges")

    modified_edges_summary = []

    for edge in net.getEdges():
        if edge.isSpecial():
            continue
        edge_id = edge.getID()
        street_name = edge.getName() or ""
        num_lanes = edge.getLaneNumber()
        speed = edge.getSpeed()
        from_node = edge.getFromNode().getID()
        to_node = edge.getToNode().getID()

        changed = False
        new_lanes = num_lanes
        new_speed = speed
        flipped = False

        # 1) Verificar se pertence a corredor com ampliação/reversão de faixa no horário de pico
        for corridor in expand_lanes_on_corridors:
            if corridor.lower() in street_name.lower():
                new_lanes = min(num_lanes + 1, 5)
                changed = True
                break

        # 2) Verificar ajuste de velocidade de sincronismo (Onda Verde)
        for corridor, target_speed in corridor_speed_ms.items():
            if corridor.lower() in street_name.lower():
                new_speed = float(target_speed)
                changed = True
                break

        # 3) Verificar inversão de mão de direção da rua/aresta
        if edge_id in reverse_edge_ids:
            from_node, to_node = to_node, from_node
            flipped = True
            changed = True

        if changed:
            attribs = {
                "id": edge_id,
                "numLanes": str(new_lanes),
                "speed": f"{new_speed:.2f}",
            }
            if flipped:
                attribs["from"] = from_node
                attribs["to"] = to_node
            ET.SubElement(edges_root, "edge", attribs)
            modified_edges_summary.append({
                "edge_id": edge_id,
                "street_name": street_name,
                "old_lanes": num_lanes,
                "new_lanes": new_lanes,
                "old_speed_kmh": round(speed * 3.6, 1),
                "new_speed_kmh": round(new_speed * 3.6, 1),
                "direction_reversed": flipped,
            })

    patch_path = NET_DIR / "to_be_patch.edg.xml"
    tree = ET.ElementTree(edges_root)
    ET.indent(tree, space="  ")
    tree.write(patch_path, encoding="utf-8", xml_declaration=True)

    netconvert_bin = sumolib.checkBinary("netconvert")
    cmd = [
        netconvert_bin,
        "--sumo-net-file", str(base_net_path),
        "--edge-files", str(patch_path),
        "--output-file", str(output_net_path),
        "--ignore-errors", "true",
        "--no-warnings", "true",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0 or not output_net_path.exists():
        raise RuntimeError(f"Erro ao compilar rede To-Be com netconvert: {res.stderr[:500]}")

    print(
        f"[NETWORK-MOD] Malha To-Be gerada com {len(modified_edges_summary)} arestas modificadas -> {output_net_path}"
    )
    return {
        "output_net_path": str(output_net_path),
        "modified_edges_count": len(modified_edges_summary),
        "modified_edges": modified_edges_summary,
    }


if __name__ == "__main__":
    cfg = load_interventions_config()
    mod_cfg = cfg["interventions"]["to_be_completo_viario_e_semaforo"]["network_modifications"]
    build_modified_network(
        expand_lanes_on_corridors=mod_cfg.get("expand_lanes_on_corridors", []),
        reverse_edge_ids=mod_cfg.get("reverse_edge_ids", []),
        corridor_speed_ms=mod_cfg.get("corridor_speed_ms", {}),
    )
