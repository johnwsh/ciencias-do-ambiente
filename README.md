# 🚦 Smart Mobility Curitiba — Quadrilátero Central (UTFPR)

Repositório de engenharia multidisciplinar para **Modelagem, Simulação Microscópica de Tráfego (SUMO/TraCI), Detecção de Gargalos e Sistemas Ciber-Físicos** aplicado ao **Quadrilátero Central de Curitiba** (delimitado por *Av. Pres. Kennedy, Calçadão da Rua XV de Novembro, Av. Mal. Floriano Peixoto, Alameda Dr. Muricy / Rua Martim Afonso, Rua Mariano Torres e Av. Mário Tourinho*).

---

## 📁 Estrutura do Repositório

```text
├── config/
│   ├── study_area.yaml              # Recortes geográficos (bbox), 10 corredores monitorados e 4 Condições Iniciais
│   └── interventions.yaml           # Catálogo de intervenções (As-Is vs. To-Be: Semáforos e Mão/Faixas de Ruas)
├── schemas/
│   └── integration_payload.schema.json  # Contrato de Dados JSON (Seção 5.2 do Manual: Automação <-> Computação <-> Mecânica)
├── data/
│   ├── raw/                         # Mapa bruto OpenStreetMap (.osm.xml) e metadados abertos URBS (C3SL/UFPR)
│   ├── processed/
│   │   ├── urbs_lines_quadrilatero.json       # Linhas da URBS mapeadas no Quadrilátero Central (BRT, Ligeirinho, Convencional)
│   │   └── reference_counts_ippuc_urbs.csv    # Contagens volumétricas horárias (VPH) de referência para calibração GEH
│   ├── network/
│   │   ├── curitiba_as_is.net.xml             # Malha viária real de Curitiba no SUMO (756 arestas, 77 ruas, 112 semáforos)
│   │   ├── curitiba_to_be.net.xml             # Malha viária modificada pós-intervenção (mão de ruas / faixas / velocidade)
│   │   ├── sensors.add.xml                    # Laços indutivos e detectores de área (E2) posicionados nos 10 corredores
│   │   ├── monitored_points_mapping.json      # Mapeamento de coordenadas, semáforos (tls_id) e faixas por ponto medido
│   │   ├── curitiba_as_is.sumocfg             # Configuração pronta para abrir o Cenário As-Is no sumo-gui
│   │   └── curitiba_to_be.sumocfg             # Configuração pronta para abrir o Cenário To-Be no sumo-gui
│   └── routes/                      # Arquivos de demanda multimodal (.rou.xml) para diferentes Condições Iniciais
├── src/
│   ├── data_ingestion/
│   │   ├── osm_importer.py          # Baixa o mapa real de Curitiba (OpenStreetMap API) e compila com `netconvert`
│   │   └── urbs_importer.py         # Sincroniza dados públicos da URBS (C3SL/UFPR) e contagens de referência IPPUC
│   ├── simulation/
│   │   ├── sensor_placer.py         # Posiciona detectores virtuais E2 nas aproximações semafóricas dos corredores
│   │   ├── demand_generator.py      # Gera rotas sob diferentes Condições Iniciais e perfil de frota de Curitiba (HBEFA3)
│   │   └── runner.py                # Orquestrador SUMO + TraCI (executa simulações, coleta fluxo e gera relatórios)
│   ├── interventions/
│   │   ├── traffic_light_control.py # Algoritmos TraCI: Tempo Fixo, Onda Verde e Controle Adaptativo + Prioridade BRT
│   │   └── network_modifier.py      # Altera mão de direção de ruas, número de faixas e velocidade via `netconvert`
│   ├── analytics/
│   │   ├── bottleneck_detector.py   # Calcula o Índice de Severidade de Gargalo (BSI 0-100), emissões e ruído CoRTN
│   │   └── geh_calibration.py       # Validação estatística GEH (< 5.0 em >= 85% das vias monitoradas)
│   ├── iot_mqtt/
│   │   └── mqtt_bridge.py           # Emite payloads JSON padronizados via MQTT (Eclipse Mosquitto) e JSONL
│   └── dashboard/
│       └── app.py                   # Painel interativo em Streamlit + Plotly com mapa de gargalos e comparativo To-Be
├── results/
│   ├── all_simulations_metrics.csv  # Tabela consolidada de todas as simulações e condições iniciais
│   ├── experiment_suite_summary.json# Resumo executivo dos gargalos, GEH e ganhos percentuais das intervenções
│   └── runs/                        # Logs detalhados, séries temporais e telemetria JSONL de cada simulação
└── tests/
    └── test_pipeline.py             # Testes automatizados de validação GEH, contrato JSON e melhoria To-Be
```

---

## 🚀 Como Executar (Passo a Passo)

### 1. Instalar Dependências
O projeto utiliza o pacote oficial `eclipse-sumo` (que já inclui os binários `sumo`, `sumo-gui` e `netconvert`), além de `traci`, `sumolib`, `streamlit`, `plotly` e `pandas`:
```powershell
pip install -r requirements.txt
```

### 2. Importar Mapa Real de Curitiba (OSM) e Dados Públicos da URBS/IPPUC
```powershell
python -m src.data_ingestion.osm_importer
python -m src.data_ingestion.urbs_importer
python -m src.simulation.sensor_placer
```

### 3. Rodar a Bateria Completa de Simulações (Condições Iniciais + Intervenções)
Executa todas as 4 condições iniciais (`entre_pico`, `pico_manha`, `pico_tarde`, `estresse_severo`) e testa as 3 intervenções propostas no horário de pico:
```powershell
python -m src.simulation.runner --mode suite --steps 180
```
Ou para rodar uma única simulação abrindo a interface gráfica do **SUMO (`sumo-gui`)**:
```powershell
python -m src.simulation.runner --mode single --condition pico_tarde --intervention to_be_adaptativo_brt --gui
```

### 4. Abrir o Painel Analítico Interativo (Streamlit)
```powershell
streamlit run src/dashboard/app.py
```

### 5. Executar os Testes Automatizados de Validação
```powershell
python -m tests.test_pipeline
```

---

## 🔍 Principais Gargalos Identificados no Quadrilátero Central (Cenário *As-Is* — Pico da Tarde 17h–19h)

| Ranking | Ponto / Cruzamento Monitorado | Fluxo Simulado (veíc/h) | Índice GEH | Fila Máx. (m) | Espera Média (s) | Score BSI (0-100) | Classificação |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **1º** | **Rua Mariano Torres x Rua XV de Novembro** (`PT_01_MARIANO_XV`) | 2.185 | 0,75 | 133,7 m | 55,9 s | **87,2** | 🔴 CRÍTICO |
| **2º** | **Av. Visconde de Guarapuava x Av. Mal. Floriano Peixoto** (`PT_09_VISCONDE_GUARAPUAVA`) | 2.264 | 0,34 | 82,3 m | 51,8 s | **84,8** | 🔴 CRÍTICO |
| **3º** | **Rua Mariano Torres x Rua André de Barros** (`PT_02_MARIANO_ANDRE`) | 2.126 | 1,00 | 132,0 m | 54,4 s | **84,0** | 🔴 CRÍTICO |

> **Calibração Estatística GEH:** **90% a 100%** dos pontos monitorados apresentaram $GEH < 5,0$ (média $GEH = 2,49$), superando a exigência mínima de $85\%$ do Marco 2 (M2).

---

## 🛠️ Comparativo das Mudanças Propostas (*As-Is* vs. *To-Be* no Pico da Tarde)

| Cenário / Intervenção | Fila Máx. Média | Espera Média | Velocidade Média | Emissão de $\text{CO}_2$ | Redução de $\text{CO}_2$ | Gargalos Críticos |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Cenário Base (*As-Is*)** | 85,8 m | 38,9 s | 28,4 km/h | 788,6 kg/h | — | 6 |
| **To-Be 1: Onda Verde (Re-temporização Semafórica)** | 50,2 m (-35,8%) | 27,6 s (-28,7%) | 32,4 km/h (+14,4%) | 572,1 kg/h | **-27,5%** | 2 |
| **To-Be 2: Semáforo Adaptativo TraCI + Prioridade BRT URBS** | 42,9 m (-45,9%) | 21,9 s (-43,3%) | 35,0 km/h (+23,8%) | 478,7 kg/h | **-39,3%** | 0 |
| **To-Be 3: Readequação Viária (Mão/Faixas) + Controle TraCI** | 36,5 m (-53,2%) | 18,5 s (-51,3%) | 37,2 km/h (+32,0%) | 432,0 kg/h | **-45,2%** | 0 |

---

## 🔧 Como Propor Novas Mudanças na Temporização ou na Mão de Certas Ruas

Para testar novas hipóteses de engenharia:
1. Abra [`config/interventions.yaml`](config/interventions.yaml).
2. Em `network_modifications`:
   - Adicione IDs de arestas (consultáveis em [`data/network/network_catalog.json`](data/network/network_catalog.json)) na lista `reverse_edge_ids` para **inverter a mão de direção** de uma rua.
   - Adicione o nome da rua em `expand_lanes_on_corridors` para converter estacionamento em faixa ativa/exclusiva no horário de pico.
   - Ajuste velocidades sincronizadas em `corridor_speed_ms`.
3. Em `tls_mode`, escolha entre `fixed_baseline`, `green_wave_optimized` ou `adaptive_traci_brt` (ou customize a lógica em [`src/interventions/traffic_light_control.py`](src/interventions/traffic_light_control.py)).
4. Execute `python -m src.simulation.runner --mode suite` e compare os resultados!
