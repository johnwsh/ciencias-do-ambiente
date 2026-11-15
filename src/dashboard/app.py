"""
Painel Analítico Interativo (Streamlit) para o Projeto de Mobilidade Urbana,
Sustentabilidade e Sistemas Ciber-Físicos — Quadrilátero Central de Curitiba (UTFPR).

Exibe:
1. Mapa interativo dos 10 corredores monitorados e classificação de Gargalos (BSI).
2. Análise do fluxo de carros e filas sob diferentes Condições Iniciais (`pico_manha`, `pico_tarde`, `entre_pico`, `estresse_severo`).
3. Validação estatística de calibração pelo Índice GEH (< 5.0 em >= 85% das vias).
4. Comparação Antes vs. Depois (Cenário As-Is vs. Cenários To-Be: Onda Verde, TraCI + BRT e Mudança de Mão/Faixas).
5. Impacto Ambiental (Emissões cinemáticas HBEFA3 de CO2, NOx, PMx e Acústica Urbana Leq dBA).
6. Visualizador de Telemetria Ciber-Física (Payloads JSON MQTT da Seção 5.2 do Manual).
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

ROOT_DIR = Path(__file__).resolve().parents[2]
RESULTS_DIR = ROOT_DIR / "results"
PROCESSED_DIR = ROOT_DIR / "data" / "processed"
NET_DIR = ROOT_DIR / "data" / "network"


def render_interactive_curitiba_map(df_points: pd.DataFrame, height: int = 475) -> None:
    """
    Renderiza o mapa interativo do Quadrilátero Central de Curitiba usando Leaflet.js + OpenStreetMap
    (suporta pan livre com o mouse, zoom, troca de camadas, polilinhas reais das ruas do SUMO
    e popups/tooltips detalhados de cada gargalo).
    """
    polylines_path = NET_DIR / "corridors_polylines.json"
    corridors_polylines = {}
    if polylines_path.exists():
        try:
            corridors_polylines = json.loads(polylines_path.read_text(encoding="utf-8"))
        except Exception:
            corridors_polylines = {}

    points_payload = df_points[
        [
            "bottleneck_rank",
            "point_id",
            "corridor",
            "intersection_name",
            "direction",
            "lat",
            "lon",
            "simulated_vph",
            "reference_vph",
            "geh",
            "max_queue_m",
            "avg_wait_s",
            "avg_speed_kmh",
            "co2_kg_per_hour",
            "noise_leq_dba",
            "bsi_score",
            "bottleneck_status",
            "engineering_diagnosis",
        ]
    ].to_dict(orient="records")

    points_json = json.dumps(points_payload, ensure_ascii=False)
    polylines_json = json.dumps(corridors_polylines, ensure_ascii=False)

    html_code = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8" />
        <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
        <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
        <style>
            body {{ margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
            #map {{ width: 100%; height: {height - 15}px; border-radius: 10px; border: 1px solid #ddd; }}
            .map-legend {{
                background: rgba(255, 255, 255, 0.94);
                padding: 10px 12px;
                border-radius: 8px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.18);
                font-size: 12px;
                line-height: 1.5;
                color: #1f2937;
            }}
            .legend-dot {{
                display: inline-block;
                width: 11px;
                height: 11px;
                border-radius: 50%;
                margin-right: 6px;
                vertical-align: middle;
            }}
            .rank-badge {{
                background: #111827;
                color: #fff;
                font-weight: 700;
                font-size: 11px;
                border-radius: 50%;
                width: 22px;
                height: 22px;
                display: flex;
                align-items: center;
                justify-content: center;
                border: 2px solid #fff;
                box-shadow: 0 1px 4px rgba(0,0,0,0.4);
            }}
            .reset-btn {{
                background: #ffffff;
                border: 1px solid #ccc;
                padding: 6px 10px;
                border-radius: 6px;
                cursor: pointer;
                font-weight: 600;
                font-size: 12px;
                box-shadow: 0 1px 4px rgba(0,0,0,0.2);
            }}
            .reset-btn:hover {{ background: #f3f4f6; }}
        </style>
    </head>
    <body>
        <div id="map"></div>
        <script>
            const points = {points_json};
            const corridorsPolylines = {polylines_json};

            const osmLayer = L.tileLayer('https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
                maxZoom: 19,
                attribution: '&copy; OpenStreetMap contributors'
            }});

            const esriStreet = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
                maxZoom: 19,
                attribution: 'Tiles &copy; Esri'
            }});

            const esriSat = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
                maxZoom: 19,
                attribution: 'Tiles &copy; Esri'
            }});

            const map = L.map('map', {{
                center: [-25.4312, -49.2670],
                zoom: 14,
                layers: [osmLayer],
                scrollWheelZoom: true,
                dragging: true
            }});

            const baseMaps = {{
                "OpenStreetMap (Ruas de Curitiba)": osmLayer,
                "Esri Mapa Viário": esriStreet,
                "Esri Satélite": esriSat
            }};

            const corridorsLayer = L.layerGroup().addTo(map);
            const markersLayer = L.layerGroup().addTo(map);

            L.control.layers(baseMaps, {{
                "Corredores Viários (Malha SUMO)": corridorsLayer,
                "Sensores e Gargalos (E2)": markersLayer
            }}, {{ collapsed: true }}).addTo(map);

            function getColorByBSI(bsi) {{
                if (bsi >= 62.0) return '#dc2626'; // Crítico (Vermelho)
                if (bsi >= 42.0) return '#f97316'; // Alerta (Laranja)
                return '#16a34a';                  // Normal (Verde)
            }}

            // Mapear severidade máxima por corredor para colorir as vias da malha
            const corridorBsi = {{}};
            points.forEach(pt => {{
                if (!corridorBsi[pt.corridor] || pt.bsi_score > corridorBsi[pt.corridor]) {{
                    corridorBsi[pt.corridor] = pt.bsi_score;
                }}
            }});

            Object.keys(corridorsPolylines).forEach(corrName => {{
                const bsi = corridorBsi[corrName] || 35.0;
                const color = getColorByBSI(bsi);
                const lines = corridorsPolylines[corrName] || [];
                lines.forEach(coords => {{
                    L.polyline(coords, {{
                        color: color,
                        weight: 5,
                        opacity: 0.72
                    }}).bindTooltip(`<b>Via:</b> ${{corrName}}<br><b>BSI do Corredor:</b> ${{bsi.toFixed(1)}}`).addTo(corridorsLayer);
                }});
            }});

            const bounds = [];
            points.forEach(pt => {{
                const color = getColorByBSI(pt.bsi_score);
                const radius = Math.max(12, Math.min(pt.max_queue_m * 0.24, 32));
                bounds.push([pt.lat, pt.lon]);

                // Círculo proporcional ao tamanho da fila
                const circle = L.circleMarker([pt.lat, pt.lon], {{
                    radius: radius,
                    fillColor: color,
                    color: '#ffffff',
                    weight: 2.5,
                    opacity: 1.0,
                    fillOpacity: 0.82
                }}).addTo(markersLayer);

                const popupHtml = `
                    <div style="min-width: 240px; font-size: 12.5px; line-height: 1.45;">
                        <div style="font-weight: 700; font-size: 13.5px; color: #111827; margin-bottom: 4px;">
                            #${{pt.bottleneck_rank}} — ${{pt.intersection_name}}
                        </div>
                        <div style="margin-bottom: 6px;">
                            <span style="background:${{color}}; color:#fff; padding:2px 7px; border-radius:4px; font-weight:600; font-size:11px;">
                                ${{pt.bottleneck_status}} (BSI: ${{pt.bsi_score}})
                            </span>
                        </div>
                        <b>Corredor:</b> ${{pt.corridor}} (${{pt.direction}})<br/>
                        <b>Fluxo Medido:</b> ${{pt.simulated_vph}} veíc/h (Ref: ${{pt.reference_vph}} | GEH: ${{pt.geh}})<br/>
                        <b>Fila Máxima:</b> ${{pt.max_queue_m}} m<br/>
                        <b>Espera no Semáforo:</b> ${{pt.avg_wait_s}} s/veíc<br/>
                        <b>Velocidade Média:</b> ${{pt.avg_speed_kmh}} km/h<br/>
                        <b>Emissão CO₂:</b> ${{pt.co2_kg_per_hour}} kg/h | <b>Ruído:</b> ${{pt.noise_leq_dba}} dB(A)<br/>
                        <hr style="margin: 6px 0; border: 0; border-top: 1px solid #e5e7eb;"/>
                        <span style="color:#374151;"><b>Diagnóstico:</b> ${{pt.engineering_diagnosis}}</span>
                    </div>
                `;

                circle.bindPopup(popupHtml);
                circle.bindTooltip(
                    `<b>#${{pt.bottleneck_rank}} ${{pt.intersection_name}}</b><br/>` +
                    `Fila Máx: <b>${{pt.max_queue_m}} m</b> | Espera: <b>${{pt.avg_wait_s}} s</b> | BSI: <b>${{pt.bsi_score}}</b>`,
                    {{ direction: 'top', offset: [0, -8] }}
                );

                // Badge com o número do Ranking em cima do ponto
                const badgeIcon = L.divIcon({{
                    className: '',
                    html: `<div class="rank-badge" style="background:${{color}};">${{pt.bottleneck_rank}}</div>`,
                    iconSize: [22, 22],
                    iconAnchor: [11, 11]
                }});
                L.marker([pt.lat, pt.lon], {{ icon: badgeIcon, interactive: false }}).addTo(markersLayer);
            }});

            if (bounds.length > 0) {{
                map.fitBounds(bounds, {{ padding: [38, 38], maxZoom: 15 }});
            }}

            // Botão para centralizar novamente o mapa
            const resetControl = L.control({{ position: 'topleft' }});
            resetControl.onAdd = function() {{
                const btn = L.DomUtil.create('button', 'reset-btn');
                btn.innerHTML = '🎯 Centralizar Quadrilátero';
                btn.onclick = function(e) {{
                    L.DomEvent.stopPropagation(e);
                    if (bounds.length > 0) {{
                        map.fitBounds(bounds, {{ padding: [38, 38], maxZoom: 15 }});
                    }}
                }};
                return btn;
            }};
            resetControl.addTo(map);

            // Legenda no canto inferior direito
            const legend = L.control({{ position: 'bottomright' }});
            legend.onAdd = function() {{
                const div = L.DomUtil.create('div', 'map-legend');
                div.innerHTML = `
                    <b>Severidade do Gargalo (BSI)</b><br/>
                    <span class="legend-dot" style="background:#dc2626;"></span>Crítico (BSI &ge; 62)<br/>
                    <span class="legend-dot" style="background:#f97316;"></span>Alerta (42 &le; BSI &lt; 62)<br/>
                    <span class="legend-dot" style="background:#16a34a;"></span>Fluido (BSI &lt; 42)<br/>
                    <small style="color:#4b5563;">* Círculo = Fila Máx (m) | Arraste para mover</small>
                `;
                return div;
            }};
            legend.addTo(map);
        </script>
    </body>
    </html>
    """
    components.html(html_code, height=height)

st.set_page_config(
    page_title="Smart Mobility Curitiba - UTFPR",
    page_icon="🚦",
    layout="wide",
)

st.title("🚦 Smart Mobility Curitiba — Quadrilátero Central (UTFPR)")
st.markdown(
    "**Engenharia de Computação, Elétrica/Automação e Mecânica** | "
    "Simulação Microscópica SUMO + Controle Semafórico TraCI + Diagnóstico de Gargalos e Emissões"
)

master_csv = RESULTS_DIR / "all_simulations_metrics.csv"
suite_json = RESULTS_DIR / "experiment_suite_summary.json"

if not master_csv.exists() or not suite_json.exists():
    st.warning(
        "Os resultados da bateria de simulação ainda não foram gerados. "
        "Execute `python -m src.simulation.runner --mode suite` no terminal."
    )
    st.stop()

df_all = pd.read_csv(master_csv)
suite_data = json.loads(suite_json.read_text(encoding="utf-8"))

# Barra lateral de filtros
st.sidebar.header("⚙️ Parâmetros de Análise")
condition_labels = {
    "pico_tarde": "Pico da Tarde (17:00 - 19:00)",
    "pico_manha": "Pico da Manhã (06:30 - 09:00)",
    "entre_pico": "Entre-Pico Comercial (12:00 - 14:00)",
    "estresse_severo": "Teste de Estresse (+40% Demanda)",
}
selected_cond = st.sidebar.selectbox(
    "Condição Inicial (Demanda):",
    options=list(condition_labels.keys()),
    format_func=lambda k: condition_labels.get(k, k),
)

intervention_labels = {
    "as_is_baseline": "Cenário Base (As-Is)",
    "to_be_semaforo_onda_verde": "To-Be 1: Re-temporização Semafórica (Onda Verde)",
    "to_be_adaptativo_brt": "To-Be 2: Semáforo Adaptativo TraCI + Prioridade BRT",
    "to_be_completo_viario_e_semaforo": "To-Be 3: Readequação Viária (Mão/Faixas) + TraCI",
}
available_interventions = df_all[df_all["condition"] == selected_cond]["intervention"].unique().tolist()
selected_int = st.sidebar.selectbox(
    "Cenário / Intervenção:",
    options=available_interventions,
    format_func=lambda k: intervention_labels.get(k, k),
)

df_sel = df_all[(df_all["condition"] == selected_cond) & (df_all["intervention"] == selected_int)].sort_values(
    by="bottleneck_rank"
)

# KPIs de Topo
col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Comprimento Médio de Fila", f"{df_sel['max_queue_m'].mean():.1f} m")
col2.metric("Atraso / Espera Média", f"{df_sel['avg_wait_s'].mean():.1f} s/veíc")
col3.metric("Velocidade Média da Rede", f"{df_sel['avg_speed_kmh'].mean():.1f} km/h")
col4.metric("Emissão Total de CO₂", f"{df_sel['co2_kg_per_hour'].sum():.1f} kg/h")
geh_pass_pct = (df_sel["geh"] < 5.0).mean() * 100.0
col5.metric("Calibração GEH (< 5.0)", f"{geh_pass_pct:.0f}% das vias", delta="Válido (>=85%)" if geh_pass_pct >= 85 else "Atenção")

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📍 Mapa e Ranking de Gargalos",
    "📊 Condições Iniciais (Fluxo e Filas)",
    "🔄 Comparativo As-Is vs. To-Be",
    "🌱 Impacto Ambiental e Ruído (HBEFA/CoRTN)",
    "📡 Contrato IoT/MQTT & Linhas URBS",
])

with tab1:
    st.subheader(f"Diagnóstico de Gargalos — {condition_labels.get(selected_cond)} | {intervention_labels.get(selected_int)}")
    c_map, c_bar = st.columns([1.1, 1.0])

    with c_map:
        st.markdown("**Mapa Interativo da Rede e Gargalos (Arraste para mover, Scroll para Zoom, Clique nos pontos)**")
        render_interactive_curitiba_map(df_sel, height=455)

    with c_bar:
        fig_rank = px.bar(
            df_sel.sort_values("bsi_score", ascending=True),
            x="bsi_score",
            y="intersection_name",
            color="bottleneck_status",
            orientation="h",
            color_discrete_map={
                "CRÍTICO (Gargalo Severo)": "#d62728",
                "ALERTA (Saturação Moderada)": "#ff7f0e",
                "NORMAL (Fluxo Fluido)": "#2ca02c",
            },
            labels={"bsi_score": "Índice de Severidade de Gargalo (BSI 0-100)", "intersection_name": "Cruzamento Monitorado"},
            title="Ranking de Gargalos no Quadrilátero Central",
            height=460,
        )
        st.plotly_chart(fig_rank, width="stretch")

    st.markdown("#### Tabela de Medição nos Pontos Monitorados e Validação Estatística GEH")
    display_cols = [
        "bottleneck_rank",
        "point_id",
        "intersection_name",
        "reference_vph",
        "simulated_vph",
        "geh",
        "geh_status",
        "max_queue_m",
        "avg_wait_s",
        "avg_speed_kmh",
        "bsi_score",
        "bottleneck_status",
        "engineering_diagnosis",
    ]
    st.dataframe(df_sel[display_cols], width="stretch", hide_index=True)

with tab2:
    st.subheader("Comportamento da Rede sob Diferentes Condições Iniciais (Cenário Base As-Is)")
    df_conds = df_all[df_all["intervention"] == "as_is_baseline"].copy()
    df_conds["Condição Inicial"] = df_conds["condition"].map(condition_labels)

    col_a, col_b = st.columns(2)
    with col_a:
        fig_flow = px.bar(
            df_conds,
            x="corridor",
            y="simulated_vph",
            color="Condição Inicial",
            barmode="group",
            title="Fluxo Veicular Medido por Corredor (veículos/hora)",
            labels={"corridor": "Corredor Viário", "simulated_vph": "Fluxo (veíc/h)"},
        )
        st.plotly_chart(fig_flow, width="stretch")

    with col_b:
        fig_q_cond = px.bar(
            df_conds,
            x="corridor",
            y="max_queue_m",
            color="Condição Inicial",
            barmode="group",
            title="Tamanho Máximo de Fila por Condição Inicial (metros)",
            labels={"corridor": "Corredor Viário", "max_queue_m": "Fila Máxima (m)"},
        )
        st.plotly_chart(fig_q_cond, width="stretch")

with tab3:
    st.subheader("Validação das Mudanças Propostas: Cenário As-Is vs. Cenários To-Be (Pico da Tarde)")
    df_pico = df_all[df_all["condition"] == "pico_tarde"].copy()
    df_pico["Cenário"] = df_pico["intervention"].map(intervention_labels)

    col_c1, col_c2 = st.columns(2)
    with col_c1:
        fig_comp_q = px.bar(
            df_pico,
            x="intersection_name",
            y="max_queue_m",
            color="Cenário",
            barmode="group",
            title="Redução do Comprimento de Fila nos Cruzamentos (m)",
            labels={"intersection_name": "Cruzamento", "max_queue_m": "Fila Máxima (m)"},
        )
        st.plotly_chart(fig_comp_q, width="stretch")

    with col_c2:
        fig_comp_w = px.bar(
            df_pico,
            x="intersection_name",
            y="avg_wait_s",
            color="Cenário",
            barmode="group",
            title="Redução do Tempo Médio de Espera nos Semáforos (s)",
            labels={"intersection_name": "Cruzamento", "avg_wait_s": "Espera Média (s)"},
        )
        st.plotly_chart(fig_comp_w, width="stretch")

    st.markdown("#### Resumo Executivo dos Ganhos de Engenharia (Pico da Tarde 17:00 - 19:00)")
    comp_dict = suite_data.get("interventions_comparison_pico_tarde", {})
    comp_rows = []
    for k, v in comp_dict.items():
        comp_rows.append({
            "Intervenção (To-Be)": intervention_labels.get(k, k),
            "Redução Média de Fila (%)": f"-{v['avg_queue_reduction_pct']}%",
            "Redução de Tempo de Espera (%)": f"-{v['avg_wait_reduction_pct']}%",
            "Ganho de Velocidade Média (%)": f"+{v['avg_speed_gain_pct']}%",
            "Redução de Emissões CO₂ (%)": f"-{v['total_co2_reduction_pct']}%",
            "Redução de NOx (%)": f"-{v['total_nox_reduction_pct']}%",
            "Redução de Material Particulado PMx (%)": f"-{v['total_pmx_reduction_pct']}%",
            "Mitigação Acústica Média (dB(A))": f"-{v['avg_noise_reduction_dba']} dB(A)",
            "Gargalos Críticos Restantes": f"{v['critical_bottlenecks_to_be']} (antes: {v['critical_bottlenecks_as_is']})",
        })
    if comp_rows:
        st.table(pd.DataFrame(comp_rows))

with tab4:
    st.subheader("Sustentabilidade: Emissões de Gases de Efeito Estufa (HBEFA3) e Acústica Urbana (CoRTN)")
    col_e1, col_e2 = st.columns(2)
    with col_e1:
        fig_co2 = px.bar(
            df_pico,
            x="corridor",
            y="co2_kg_per_hour",
            color="Cenário",
            barmode="group",
            title="Emissão de CO₂ por Corredor no Horário de Pico (kg/h)",
            labels={"corridor": "Corredor", "co2_kg_per_hour": "CO₂ (kg/h)"},
        )
        st.plotly_chart(fig_co2, width="stretch")

    with col_e2:
        fig_noise = px.bar(
            df_pico,
            x="corridor",
            y="noise_leq_dba",
            color="Cenário",
            barmode="group",
            title="Nível de Pressão Sonora Equivalente Leq dB(A) (ABNT NBR 10151 / CoRTN)",
            labels={"corridor": "Corredor", "noise_leq_dba": "Ruído Leq dB(A)"},
        )
        fig_noise.update_yaxes(range=[60, 82])
        st.plotly_chart(fig_noise, width="stretch")

with tab5:
    st.subheader("Integração Ciber-Física (MQTT / JSON) e Linhas de Transporte Público (URBS)")
    col_m1, col_m2 = st.columns(2)
    with col_m1:
        st.markdown("##### Exemplo Real de Payload JSON Gerado pela Simulação (Seção 5.2 do Manual)")
        sample_jsonl = RESULTS_DIR / "runs" / f"{selected_cond}__{selected_int}__seed42" / "cyber_physical_telemetry.jsonl"
        if sample_jsonl.exists():
            lines = sample_jsonl.read_text(encoding="utf-8").splitlines()
            if lines:
                st.json(json.loads(lines[-1]))
        else:
            st.info("Arquivo JSONL de telemetria não encontrado para esta combinação.")

    with col_m2:
        st.markdown("##### Linhas da URBS Mapeadas no Quadrilátero Central")
        urbs_path = PROCESSED_DIR / "urbs_lines_quadrilatero.json"
        if urbs_path.exists():
            urbs_data = json.loads(urbs_path.read_text(encoding="utf-8"))
            st.dataframe(pd.DataFrame(urbs_data["lines"]), width="stretch", hide_index=True)
