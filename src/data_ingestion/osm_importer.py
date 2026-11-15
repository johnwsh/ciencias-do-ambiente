"""
Importador da malha viária do Quadrilátero Central de Curitiba via OpenStreetMap (Overpass API)
e conversão para rede microscópica do SUMO (.net.xml) utilizando `netconvert`.

Inclui também catalogação automática das vias, sentidos (mão única/dupla) e semáforos
das ruas delimitadoras do projeto:
- Av. Pres. Kennedy
- Calçadão da Rua XV de Novembro
- Av. Mal. Floriano Peixoto
- Alameda Dr. Muricy / Rua Martim Afonso
- Rua Mariano Torres
- Av. Mário Tourinho
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

import requests
import sumolib
import yaml

OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

ROOT_DIR = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT_DIR / "config" / "study_area.yaml"
RAW_DIR = ROOT_DIR / "data" / "raw"
NET_DIR = ROOT_DIR / "data" / "network"


def load_config() -> dict[str, Any]:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def download_osm_bbox(bbox: list[float], output_osm_path: Path, timeout: int = 60) -> bool:
    """
    Baixa os dados viários do OpenStreetMap para o bounding box [min_lon, min_lat, max_lon, max_lat].
    """
    min_lon, min_lat, max_lon, max_lat = bbox
    output_osm_path.parent.mkdir(parents=True, exist_ok=True)
    headers = {
        "User-Agent": "UTFPR-SmartMobility-Curitiba/1.0 (https://utfpr.edu.br; ciencias-do-ambiente)",
        "Accept": "*/*",
    }

    # 1) Tentar API oficial do OpenStreetMap (/api/0.6/map) para o recorte geográfico
    osm_api_url = f"https://api.openstreetmap.org/api/0.6/map?bbox={min_lon},{min_lat},{max_lon},{max_lat}"
    try:
        print(f"[OSM] Baixando malha real de Curitiba via OpenStreetMap API ({osm_api_url})...")
        resp = requests.get(osm_api_url, headers=headers, timeout=timeout)
        if resp.status_code == 200 and b"<osm" in resp.content and b"<way" in resp.content:
            output_osm_path.write_bytes(resp.content)
            size_kb = len(resp.content) / 1024.0
            print(f"[OSM] Mapa real de Curitiba baixado com sucesso: {output_osm_path} ({size_kb:.1f} KB)")
            return True
    except Exception as exc:
        print(f"[OSM] Aviso na API direta OSM: {exc}")

    # 2) Tentar espelhos Overpass QL
    overpass_query = (
        f"[out:xml][timeout:{timeout}];"
        f"(way['highway']({min_lat},{min_lon},{max_lat},{max_lon});"
        f"node['highway'='traffic_signals']({min_lat},{min_lon},{max_lat},{max_lon});"
        f"relation['type'='restriction']({min_lat},{min_lon},{max_lat},{max_lon}););"
        f"(._;>;);out meta;"
    )

    for endpoint in OVERPASS_ENDPOINTS:
        try:
            print(f"[OSM] Consultando Overpass API ({endpoint}) para bbox={bbox}...")
            resp = requests.post(endpoint, data={"data": overpass_query}, headers=headers, timeout=timeout)
            if resp.status_code == 200 and b"<osm" in resp.content and b"<way" in resp.content:
                output_osm_path.write_bytes(resp.content)
                size_kb = len(resp.content) / 1024.0
                print(f"[OSM] Mapa baixado com sucesso: {output_osm_path} ({size_kb:.1f} KB)")
                return True
            else:
                print(f"[OSM] Resposta inesperada de {endpoint}: status={resp.status_code}")
        except Exception as exc:
            print(f"[OSM] Aviso: falha ao consultar {endpoint}: {exc}")

    return False


def build_fallback_curitiba_network(output_net_path: Path) -> None:
    """
    Gera uma malha viária fiel ao Quadrilátero Central de Curitiba via `netconvert` (nós e arestas XML)
    caso o computador esteja sem acesso externo à Overpass API no momento da execução.
    """
    print("[OSM-Fallback] Gerando malha estrutural de contingência do Quadrilátero Central de Curitiba...")
    output_net_path.parent.mkdir(parents=True, exist_ok=True)
    nod_file = RAW_DIR / "curitiba_fallback.nod.xml"
    edg_file = RAW_DIR / "curitiba_fallback.edg.xml"
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    nodes_xml = """<?xml version="1.0" encoding="UTF-8"?>
<nodes>
    <!-- Eixo Norte: Rua XV de Novembro / Calçadão -->
    <node id="n_muricy_xv" x="200.0" y="1000.0" type="traffic_light"/>
    <node id="n_floriano_xv" x="600.0" y="1000.0" type="traffic_light"/>
    <node id="n_mariano_xv" x="1000.0" y="1000.0" type="traffic_light"/>
    <node id="n_xv_leste" x="1350.0" y="1000.0" type="priority"/>
    <node id="n_martim_norte" x="0.0" y="1000.0" type="priority"/>

    <!-- Eixo Intermediário Central: Rua Monsenhor Celso / Rua Marechal Deodoro -->
    <node id="n_tourinho_deodoro" x="0.0" y="700.0" type="traffic_light"/>
    <node id="n_muricy_deodoro" x="200.0" y="700.0" type="traffic_light"/>
    <node id="n_floriano_deodoro" x="600.0" y="700.0" type="traffic_light"/>
    <node id="n_mariano_deodoro" x="1000.0" y="700.0" type="traffic_light"/>
    <node id="n_deodoro_leste" x="1350.0" y="700.0" type="priority"/>

    <!-- Eixo Saída Centro: Rua André de Barros / Praça Rui Barbosa -->
    <node id="n_tourinho_andre" x="0.0" y="400.0" type="traffic_light"/>
    <node id="n_muricy_andre" x="200.0" y="400.0" type="traffic_light"/>
    <node id="n_floriano_andre" x="600.0" y="400.0" type="traffic_light"/>
    <node id="n_mariano_andre" x="1000.0" y="400.0" type="traffic_light"/>
    <node id="n_andre_leste" x="1350.0" y="400.0" type="priority"/>

    <!-- Eixo Sul: Av. Visconde de Guarapuava / Conexão Av. Pres. Kennedy -->
    <node id="n_tourinho_kennedy" x="0.0" y="100.0" type="traffic_light"/>
    <node id="n_muricy_kennedy" x="200.0" y="100.0" type="traffic_light"/>
    <node id="n_floriano_kennedy" x="600.0" y="100.0" type="traffic_light"/>
    <node id="n_mariano_kennedy" x="1000.0" y="100.0" type="traffic_light"/>
    <node id="n_kennedy_leste" x="1350.0" y="100.0" type="priority"/>

    <!-- Alimentadores extremos Norte e Sul -->
    <node id="n_muricy_ext_n" x="200.0" y="1250.0" type="priority"/>
    <node id="n_floriano_ext_n" x="600.0" y="1250.0" type="priority"/>
    <node id="n_mariano_ext_n" x="1000.0" y="1250.0" type="priority"/>
    <node id="n_muricy_ext_s" x="200.0" y="-150.0" type="priority"/>
    <node id="n_floriano_ext_s" x="600.0" y="-150.0" type="priority"/>
    <node id="n_mariano_ext_s" x="1000.0" y="-150.0" type="priority"/>
</nodes>
"""

    edges_xml = """<?xml version="1.0" encoding="UTF-8"?>
<edges>
    <!-- Rua Mariano Torres (Arterial Norte->Sul e Sul->Norte, 3 faixas, muito crítica) -->
    <edge id="mariano_torres_n1" from="n_mariano_ext_n" to="n_mariano_xv" name="Rua Mariano Torres" numLanes="3" speed="13.89"/>
    <edge id="mariano_torres_n2" from="n_mariano_xv" to="n_mariano_deodoro" name="Rua Mariano Torres" numLanes="3" speed="13.89"/>
    <edge id="mariano_torres_n3" from="n_mariano_deodoro" to="n_mariano_andre" name="Rua Mariano Torres" numLanes="3" speed="13.89"/>
    <edge id="mariano_torres_n4" from="n_mariano_andre" to="n_mariano_kennedy" name="Rua Mariano Torres" numLanes="3" speed="13.89"/>
    <edge id="mariano_torres_n5" from="n_mariano_kennedy" to="n_mariano_ext_s" name="Rua Mariano Torres" numLanes="3" speed="13.89"/>

    <edge id="mariano_torres_s1" from="n_mariano_ext_s" to="n_mariano_kennedy" name="Rua Mariano Torres" numLanes="2" speed="13.89"/>
    <edge id="mariano_torres_s2" from="n_mariano_kennedy" to="n_mariano_andre" name="Rua Mariano Torres" numLanes="2" speed="13.89"/>
    <edge id="mariano_torres_s3" from="n_mariano_andre" to="n_mariano_deodoro" name="Rua Mariano Torres" numLanes="2" speed="13.89"/>
    <edge id="mariano_torres_s4" from="n_mariano_deodoro" to="n_mariano_xv" name="Rua Mariano Torres" numLanes="2" speed="13.89"/>
    <edge id="mariano_torres_s5" from="n_mariano_xv" to="n_mariano_ext_n" name="Rua Mariano Torres" numLanes="2" speed="13.89"/>

    <!-- Av. Marechal Floriano Peixoto (Eixo Central Sul-Norte / Norte-Sul + BRT) -->
    <edge id="floriano_peixoto_s1" from="n_floriano_ext_s" to="n_floriano_kennedy" name="Avenida Marechal Floriano Peixoto" numLanes="3" speed="13.89"/>
    <edge id="floriano_peixoto_s2" from="n_floriano_kennedy" to="n_floriano_andre" name="Avenida Marechal Floriano Peixoto" numLanes="3" speed="13.89"/>
    <edge id="floriano_peixoto_s3" from="n_floriano_andre" to="n_floriano_deodoro" name="Avenida Marechal Floriano Peixoto" numLanes="2" speed="11.11"/>
    <edge id="floriano_peixoto_s4" from="n_floriano_deodoro" to="n_floriano_xv" name="Avenida Marechal Floriano Peixoto" numLanes="2" speed="11.11"/>
    <edge id="floriano_peixoto_s5" from="n_floriano_xv" to="n_floriano_ext_n" name="Avenida Marechal Floriano Peixoto" numLanes="2" speed="11.11"/>

    <edge id="floriano_peixoto_n1" from="n_floriano_ext_n" to="n_floriano_xv" name="Avenida Marechal Floriano Peixoto" numLanes="2" speed="11.11"/>
    <edge id="floriano_peixoto_n2" from="n_floriano_xv" to="n_floriano_deodoro" name="Avenida Marechal Floriano Peixoto" numLanes="2" speed="11.11"/>
    <edge id="floriano_peixoto_n3" from="n_floriano_deodoro" to="n_floriano_andre" name="Avenida Marechal Floriano Peixoto" numLanes="2" speed="11.11"/>
    <edge id="floriano_peixoto_n4" from="n_floriano_andre" to="n_floriano_kennedy" name="Avenida Marechal Floriano Peixoto" numLanes="3" speed="13.89"/>
    <edge id="floriano_peixoto_n5" from="n_floriano_kennedy" to="n_floriano_ext_s" name="Avenida Marechal Floriano Peixoto" numLanes="3" speed="13.89"/>

    <!-- Alameda Doutor Muricy (Mão única Sul -> Norte no trecho central) -->
    <edge id="alameda_muricy_1" from="n_muricy_ext_s" to="n_muricy_kennedy" name="Alameda Doutor Muricy" numLanes="2" speed="11.11"/>
    <edge id="alameda_muricy_2" from="n_muricy_kennedy" to="n_muricy_andre" name="Alameda Doutor Muricy" numLanes="2" speed="11.11"/>
    <edge id="alameda_muricy_3" from="n_muricy_andre" to="n_muricy_deodoro" name="Alameda Doutor Muricy" numLanes="2" speed="11.11"/>
    <edge id="alameda_muricy_4" from="n_muricy_deodoro" to="n_muricy_xv" name="Alameda Doutor Muricy" numLanes="2" speed="11.11"/>
    <edge id="alameda_muricy_5" from="n_muricy_xv" to="n_muricy_ext_n" name="Alameda Doutor Muricy" numLanes="2" speed="11.11"/>

    <!-- Av. Mário Tourinho / Rua Martim Afonso (Oeste) -->
    <edge id="mario_tourinho_n1" from="n_martim_norte" to="n_tourinho_deodoro" name="Avenida Mário Tourinho" numLanes="3" speed="16.67"/>
    <edge id="mario_tourinho_n2" from="n_tourinho_deodoro" to="n_tourinho_andre" name="Avenida Mário Tourinho" numLanes="3" speed="16.67"/>
    <edge id="mario_tourinho_n3" from="n_tourinho_andre" to="n_tourinho_kennedy" name="Avenida Mário Tourinho" numLanes="3" speed="16.67"/>
    <edge id="mario_tourinho_s1" from="n_tourinho_kennedy" to="n_tourinho_andre" name="Avenida Mário Tourinho" numLanes="3" speed="16.67"/>
    <edge id="mario_tourinho_s2" from="n_tourinho_andre" to="n_tourinho_deodoro" name="Avenida Mário Tourinho" numLanes="3" speed="16.67"/>
    <edge id="mario_tourinho_s3" from="n_tourinho_deodoro" to="n_martim_norte" name="Rua Martim Afonso" numLanes="2" speed="13.89"/>

    <!-- Rua XV de Novembro / Rua Martim Afonso (Oeste <-> Leste) -->
    <edge id="martim_afonso_w1" from="n_martim_norte" to="n_muricy_xv" name="Rua Martim Afonso" numLanes="2" speed="11.11"/>
    <edge id="rua_xv_1" from="n_muricy_xv" to="n_floriano_xv" name="Rua XV de Novembro" numLanes="1" speed="8.33"/>
    <edge id="rua_xv_2" from="n_floriano_xv" to="n_mariano_xv" name="Rua XV de Novembro" numLanes="2" speed="11.11"/>
    <edge id="rua_xv_3" from="n_mariano_xv" to="n_xv_leste" name="Rua XV de Novembro" numLanes="3" speed="13.89"/>
    <edge id="rua_xv_rev_3" from="n_xv_leste" to="n_mariano_xv" name="Rua XV de Novembro" numLanes="2" speed="13.89"/>

    <!-- Rua Marechal Deodoro / Rua Monsenhor Celso (Mão única Leste -> Oeste) -->
    <edge id="monsenhor_celso_1" from="n_deodoro_leste" to="n_mariano_deodoro" name="Rua Marechal Deodoro" numLanes="2" speed="11.11"/>
    <edge id="monsenhor_celso_2" from="n_mariano_deodoro" to="n_floriano_deodoro" name="Rua Marechal Deodoro" numLanes="2" speed="11.11"/>
    <edge id="monsenhor_celso_3" from="n_floriano_deodoro" to="n_muricy_deodoro" name="Rua Monsenhor Celso" numLanes="2" speed="11.11"/>
    <edge id="monsenhor_celso_4" from="n_muricy_deodoro" to="n_tourinho_deodoro" name="Rua Monsenhor Celso" numLanes="2" speed="11.11"/>

    <!-- Rua André de Barros (Mão única Oeste -> Leste, escoamento intenso do Centro) -->
    <edge id="andre_barros_1" from="n_tourinho_andre" to="n_muricy_andre" name="Rua André de Barros" numLanes="3" speed="13.89"/>
    <edge id="andre_barros_2" from="n_muricy_andre" to="n_floriano_andre" name="Rua André de Barros" numLanes="3" speed="13.89"/>
    <edge id="andre_barros_3" from="n_floriano_andre" to="n_mariano_andre" name="Rua André de Barros" numLanes="3" speed="13.89"/>
    <edge id="andre_barros_4" from="n_mariano_andre" to="n_andre_leste" name="Rua André de Barros" numLanes="3" speed="13.89"/>

    <!-- Av. Presidente Kennedy / Av. Visconde de Guarapuava (Eixo Sul) -->
    <edge id="pres_kennedy_e1" from="n_tourinho_kennedy" to="n_muricy_kennedy" name="Avenida Presidente Kennedy" numLanes="3" speed="16.67"/>
    <edge id="pres_kennedy_e2" from="n_muricy_kennedy" to="n_floriano_kennedy" name="Avenida Presidente Kennedy" numLanes="3" speed="16.67"/>
    <edge id="pres_kennedy_e3" from="n_floriano_kennedy" to="n_mariano_kennedy" name="Avenida Presidente Kennedy" numLanes="3" speed="16.67"/>
    <edge id="pres_kennedy_e4" from="n_mariano_kennedy" to="n_kennedy_leste" name="Avenida Presidente Kennedy" numLanes="3" speed="16.67"/>

    <edge id="visc_guarapuava_w1" from="n_kennedy_leste" to="n_mariano_kennedy" name="Avenida Visconde de Guarapuava" numLanes="4" speed="16.67"/>
    <edge id="visc_guarapuava_w2" from="n_mariano_kennedy" to="n_floriano_kennedy" name="Avenida Visconde de Guarapuava" numLanes="4" speed="16.67"/>
    <edge id="visc_guarapuava_w3" from="n_floriano_kennedy" to="n_muricy_kennedy" name="Avenida Visconde de Guarapuava" numLanes="4" speed="16.67"/>
    <edge id="visc_guarapuava_w4" from="n_muricy_kennedy" to="n_tourinho_kennedy" name="Avenida Visconde de Guarapuava" numLanes="4" speed="16.67"/>
</edges>
"""
    nod_file.write_text(nodes_xml, encoding="utf-8")
    edg_file.write_text(edges_xml, encoding="utf-8")

    netconvert_bin = sumolib.checkBinary("netconvert")
    cmd = [
        netconvert_bin,
        "--node-files", str(nod_file),
        "--edge-files", str(edg_file),
        "--output-file", str(output_net_path),
        "--output.street-names", "true",
        "--tls.default-type", "static",
    ]
    subprocess.run(cmd, check=True)
    print(f"[OSM-Fallback] Rede gerada em: {output_net_path}")


def convert_osm_to_sumo_net(osm_path: Path, output_net_path: Path) -> bool:
    """
    Converte um arquivo .osm.xml do OpenStreetMap para uma rede SUMO (.net.xml) calibrada.
    """
    output_net_path.parent.mkdir(parents=True, exist_ok=True)
    netconvert_bin = sumolib.checkBinary("netconvert")

    cmd = [
        netconvert_bin,
        "--osm-files", str(osm_path),
        "--output-file", str(output_net_path),
        "--geometry.remove", "true",
        "--ramps.guess", "true",
        "--junctions.join", "true",
        "--tls.guess-signals", "true",
        "--tls.discard-simple", "true",
        "--tls.join", "true",
        "--tls.default-type", "static",
        "--output.street-names", "true",
        "--output.original-names", "true",
        "--keep-edges.by-vclass", "passenger,bus,motorcycle,delivery,bicycle",
        "--remove-edges.isolated", "true",
        "--no-turnarounds", "true",
        "--ignore-errors", "true",
        "--no-warnings", "true",
    ]
    print(f"[NETCONVERT] Convertendo {osm_path.name} -> {output_net_path.name}...")
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0 or not output_net_path.exists():
        print(f"[NETCONVERT] Erro na conversão: {res.stderr[:500]}")
        return False

    print(f"[NETCONVERT] Rede SUMO gerada com sucesso em: {output_net_path}")
    return True


def catalog_network(net_path: Path, config: dict[str, Any]) -> dict[str, Any]:
    """
    Inspeciona a rede SUMO gerada e cria um catálogo detalhado das ruas, arestas (edges),
    sentidos, número de faixas e semáforos (TLS) — destacando as vias do Quadrilátero Central.
    """
    net = sumolib.net.readNet(str(net_path), withPrograms=True)
    monitored_names = [c["name"] for c in config.get("monitored_corridors", [])]

    streets: dict[str, list[dict[str, Any]]] = {}
    all_edges_summary = []

    for edge in net.getEdges():
        if edge.isSpecial():
            continue
        street_name = edge.getName() or ""
        edge_info = {
            "edge_id": edge.getID(),
            "street_name": street_name,
            "from_node": edge.getFromNode().getID(),
            "to_node": edge.getToNode().getID(),
            "num_lanes": edge.getLaneNumber(),
            "length_m": round(edge.getLength(), 2),
            "speed_limit_kmh": round(edge.getSpeed() * 3.6, 1),
            "has_traffic_light": edge.getToNode().getType() in ("traffic_light", "traffic_light_unregulated"),
            "tls_id": edge.getToNode().getID() if edge.getToNode().getType() in ("traffic_light", "traffic_light_unregulated") else None,
        }
        all_edges_summary.append(edge_info)
        if street_name:
            streets.setdefault(street_name, []).append(edge_info)

    # Identificar correspondência com os corredores monitorados do projeto
    corridor_matches: dict[str, list[dict[str, Any]]] = {}
    for target in monitored_names:
        target_tokens = [t.lower() for t in target.split() if len(t) > 3]
        matched = []
        for s_name, e_list in streets.items():
            s_lower = s_name.lower()
            if all(tok in s_lower for tok in target_tokens[-2:]) or target.lower() in s_lower:
                matched.extend(e_list)
        corridor_matches[target] = sorted(matched, key=lambda x: x["length_m"], reverse=True)

    tls_list = []
    for tls in net.getTrafficLights():
        programs = list(tls.getPrograms().keys())
        controlled_edges = sorted({conn[0].getEdge().getID() for conn in tls.getConnections()})
        controlled_streets = sorted({
            conn[0].getEdge().getName()
            for conn in tls.getConnections()
            if conn[0].getEdge().getName()
        })
        tls_list.append({
            "tls_id": tls.getID(),
            "programs": programs,
            "controlled_edges": controlled_edges,
            "controlled_streets": controlled_streets,
        })

    catalog = {
        "network_file": str(net_path.relative_to(ROOT_DIR)),
        "total_edges": len(all_edges_summary),
        "total_named_streets": len(streets),
        "total_traffic_lights": len(tls_list),
        "monitored_corridors_found": {
            k: {
                "edge_count": len(v),
                "total_length_m": round(sum(item["length_m"] for item in v), 1),
                "sample_edges": [item["edge_id"] for item in v[:8]],
            }
            for k, v in corridor_matches.items()
        },
        "traffic_lights": tls_list,
        "corridor_edges": corridor_matches,
    }

    catalog_path = NET_DIR / "network_catalog.json"
    catalog_path.write_text(json.dumps(catalog, indent=2, ensure_ascii=False), encoding="utf-8")
    print(
        f"[CATALOG] Rede catalogada: {catalog['total_edges']} arestas, "
        f"{catalog['total_named_streets']} ruas nomeadas, "
        f"{catalog['total_traffic_lights']} semáforos -> {catalog_path}"
    )
    return catalog


def build_network_pipeline(region_key: str = "quadrilatero_central", force_download: bool = False) -> Path:
    config = load_config()
    region_cfg = config["regions"].get(region_key, config["regions"]["quadrilatero_central"])
    bbox = region_cfg["bbox"]

    osm_path = RAW_DIR / f"curitiba_{region_key}.osm.xml"
    net_path = NET_DIR / "curitiba_as_is.net.xml"

    if force_download or not osm_path.exists():
        downloaded = download_osm_bbox(bbox, osm_path)
    else:
        print(f"[OSM] Usando arquivo OSM em cache: {osm_path}")
        downloaded = True

    if downloaded and osm_path.exists():
        ok = convert_osm_to_sumo_net(osm_path, net_path)
        if not ok:
            build_fallback_curitiba_network(net_path)
    else:
        build_fallback_curitiba_network(net_path)

    catalog_network(net_path, config)
    return net_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Importa mapa OSM/GIS de Curitiba e gera malha SUMO (.net.xml)")
    parser.add_argument(
        "--region",
        default="quadrilatero_central",
        choices=["quadrilatero_central", "eixo_expandido"],
        help="Região geográfica definida em config/study_area.yaml",
    )
    parser.add_argument("--force", action="store_true", help="Força novo download do OpenStreetMap")
    args = parser.parse_args()
    build_network_pipeline(region_key=args.region, force_download=args.force)


if __name__ == "__main__":
    main()
