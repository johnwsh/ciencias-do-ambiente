# 🚦 Smart Mobility Curitiba — Quadrilátero Central (UTFPR)

Simulador microscópico de tráfego urbano (**SUMO + TraCI/Python**), detector de gargalos e sistema de controle semafórico adaptativo aplicado ao **Quadrilátero Central de Curitiba** (*Rua XV de Novembro, Av. Mal. Floriano Peixoto, Alameda Dr. Muricy / Rua Martim Afonso, Rua Mariano Torres, Rua André de Barros, Av. Visconde de Guarapuava, Av. Pres. Kennedy e Av. Mário Tourinho*).

---

## ⚙️ Funcionalidades Principais

1. **Importação Geográfica Real (OpenStreetMap $\rightarrow$ SUMO):**
   * Baixa automaticamente a malha viária oficial de Curitiba via API do OpenStreetMap e compila no `netconvert` (**756 arestas, 77 ruas nomeadas e 112 semáforos**), preservando mãos de direção, número de faixas, limites de velocidade e canaletas exclusivas.
2. **Integração com Transporte Público (URBS) e Frota Local:**
   * Sincroniza dados abertos da URBS (C3SL/UFPR) e modela **10 linhas de ônibus** que cruzam o Centro (Biarticulados BRT, Ligeirinhos, Interbairros e Convencionais), além de 5 classes de veículos com curvas de emissão **HBEFA3** (carros flex, vans diesel, híbridos, motos e ônibus).
3. **Simulação sob Múltiplas Condições Iniciais:**
   * Gera e simula 4 perfis de demanda: **Entre-Pico** (`entre_pico`), **Pico da Manhã** (`pico_manha`, 06:30–09:00), **Pico da Tarde** (`pico_tarde`, 17:00–19:00) e **Teste de Estresse** (`estresse_severo`, $+40\%$ de demanda).
4. **Instrumentação Automática de Sensores Virtuais (`E2` + IoT/MQTT):**
   * Posiciona detectores de área/fila (`<laneAreaDetector>`) nos últimos $80\text{ m}$ antes dos semáforos nos **10 cruzamentos principais** (28 sensores de faixa dedicados).
   * Coleta em tempo real: fluxo ($\text{veíc/h}$), fila máxima ($\text{m}$), tempo de espera ($\text{s}$), velocidade ($\text{km/h}$), ocupação ($\%$), presença de ônibus da URBS e emissões ($\text{CO}_2$, $\text{NO}_x$, $\text{PM}_x$ e ruído $L_{eq}\text{ dB(A)}$).
   * Publica pacotes JSON padronizados via **MQTT / JSONL** para integração com sistemas ciber-físicos.
5. **Validação Estatística GEH e Classificação de Gargalos (BSI):**
   * Valida o volume simulado ($M$) frente ao volume real de referência ($C$) garantindo **$GEH < 5,0$ em $\ge 85\%$ das vias** ($90\%$ a $100\%$ alcançado).
   * Calcula o **Índice de Severidade de Gargalo (*BSI*, 0 a 100)** ponderando fila ($32\%$), espera no semáforo ($28\%$), perda de velocidade ($22\%$) e ocupação do sensor ($18\%$).
6. **Teste de Intervenções (*Cenários To-Be*):**
   * **To-Be 1 (Onda Verde):** Re-temporização semafórica aumentando em $+35\%$ o verde arterial.
   * **To-Be 2 (Controle Adaptativo TraCI + Prioridade BRT):** Atuação em malha fechada a cada $4\text{ s}$ que corta fases verdes vazias (*gap-out*) e estende o verde para ônibus da URBS (*Transit Signal Priority*).
   * **To-Be 3 (Readequação Viária + TraCI):** Alteração de número de faixas (faixa reversível no pico), velocidades e mão de direção de ruas via `netconvert`.
7. **Dashboard Interativo (Streamlit + Leaflet + Plotly):**
   * Painel web com mapa interativo de Curitiba, ranking de gargalos, comparação entre condições iniciais, comparativo *As-Is* vs. *To-Be*, gráficos de emissões/ruído e inspetor de telemetria JSON/MQTT.

---

## 📁 Estrutura de Pastas

```text
├── config/
│   ├── study_area.yaml                  # Coordenadas do Quadrilátero Central, corredores e 4 condições iniciais
│   └── interventions.yaml               # Configuração dos cenários As-Is e To-Be (semáforos e mão/faixas de ruas)
├── schemas/
│   └── integration_payload.schema.json  # JSON Schema do contrato de telemetria IoT/MQTT
├── data/
│   ├── raw/                             # Mapa bruto OpenStreetMap (.osm.xml) e metadados da URBS
│   ├── processed/                       # Linhas da URBS mapeadas e tabela de contagens de referência (VPH)
│   ├── network/                         # Malhas SUMO (.net.xml), sensores (.add.xml) e arquivos .sumocfg
│   └── routes/                          # Rotas de veículos e ônibus (.rou.xml) por condição inicial
├── src/
│   ├── data_ingestion/                  # Importadores OpenStreetMap (osm_importer.py) e URBS (urbs_importer.py)
│   ├── simulation/                      # Posicionador de sensores, gerador de demanda e orquestrador TraCI (runner.py)
│   ├── interventions/                   # Controle semafórico inteligente TraCI e modificador de malha/mão de ruas
│   ├── analytics/                       # Detector de gargalos (BSI), modelo acústico CoRTN e validação GEH
│   ├── iot_mqtt/                        # Ponte de publicação de telemetria JSON/MQTT
│   └── dashboard/                       # Aplicação web interativa em Streamlit (app.py)
├── results/                             # CSVs consolidados, resumo executivo JSON e logs de cada simulação
├── docs/
│   └── MEGA_RESUMO_PROJETO.md           # Documentação teórica e técnica detalhada do projeto
└── tests/
    └── test_pipeline.py                 # Testes automatizados de validação (GEH, JSON Schema, KPIs e Streamlit)
```

---

## 🚀 Como Rodar o Projeto

### 1. Pré-requisitos e Instalação
Certifique-se de ter o **Python 3.10+** instalado. O pacote `eclipse-sumo` já instala automaticamente os binários do simulador (`sumo`, `sumo-gui` e `netconvert`).

No terminal (PowerShell ou Bash), na raiz do repositório, instale as dependências:
```powershell
pip install -r requirements.txt
```

---

### 2. Importar o Mapa, Dados da URBS e Posicionar os Sensores
*(O repositório já vem com os arquivos gerados em `data/`, mas você pode recriá-los a qualquer momento com os comandos abaixo)*:

```powershell
# 1. Baixar o mapa do OpenStreetMap e gerar a malha SUMO (curitiba_as_is.net.xml)
python -m src.data_ingestion.osm_importer

# 2. Processar as linhas da URBS e contagens de referência (VPH)
python -m src.data_ingestion.urbs_importer

# 3. Posicionar automaticamente os sensores E2 nos 10 cruzamentos e gerar as rotas
python -m src.simulation.sensor_placer
python -m src.simulation.demand_generator
```

---

### 3. Executar as Simulações no SUMO via TraCI

#### Opção A — Rodar a Bateria Completa de Experimentos (Recomendado)
Roda automaticamente as **4 condições iniciais** no cenário atual (*As-Is*) e as **3 soluções propostas (*To-Be*)** no horário de pico da tarde, gerando todas as tabelas e comparações na pasta `results/`:
```powershell
python -m src.simulation.runner --mode suite --steps 180
```

#### Opção B — Rodar uma Simulação Específica no Terminal
Você pode escolher a condição inicial (`entre_pico`, `pico_manha`, `pico_tarde`, `estresse_severo`) e a intervenção (`as_is_baseline`, `to_be_semaforo_onda_verde`, `to_be_adaptativo_brt`, `to_be_completo_viario_e_semaforo`):
```powershell
python -m src.simulation.runner --mode single --condition pico_tarde --intervention to_be_adaptativo_brt --steps 300
```

#### Opção C — Visualizar os Carros e Semáforos Ao Vivo na Interface Gráfica (`sumo-gui`)
Adicione a flag `--gui` para abrir a janela visual do SUMO controlada pelo algoritmo Python:
```powershell
python -m src.simulation.runner --mode single --condition pico_tarde --intervention to_be_adaptativo_brt --steps 600 --gui
```

---

### 4. Abrir o Dashboard Interativo (Streamlit)
Para visualizar o mapa interativo de gargalos, os gráficos comparativos Antes vs. Depois, as emissões de $\text{CO}_2$/ruído e os pacotes JSON/MQTT:
```powershell
streamlit run src/dashboard/app.py
```
O painel abrirá automaticamente no navegador em `http://localhost:8501`.

---

### 5. Rodar os Testes Automatizados de Validação
Para verificar se a malha, a calibração estatística $GEH < 5,0$ ($\ge 85\%$), o contrato JSON/MQTT e o painel Streamlit estão íntegros:
```powershell
python -m tests.test_pipeline
```

---

## 🛠️ Como Testar Novas Mudanças de Semáforo ou Mão de Ruas

1. **Alterar Mão de Ruas, Faixas ou Velocidades:**
   Edite o arquivo [`config/interventions.yaml`](config/interventions.yaml):
   * Em `reverse_edge_ids`, adicione o ID da aresta (consultável em [`data/network/network_catalog.json`](data/network/network_catalog.json)) para inverter a mão de direção de uma rua.
   * Em `expand_lanes_on_corridors`, informe o nome das ruas que terão faixa adicional/reversível liberada no pico.
   * Em `corridor_speed_ms`, defina a velocidade operacional sincronizada (em $\text{m/s}$).
2. **Atualizar Contagens de Tráfego Reais (Dados de Campo):**
   Edite os valores de `vph_pico_manha` e `vph_pico_tarde` em [`data/processed/reference_counts_ippuc_urbs.csv`](data/processed/reference_counts_ippuc_urbs.csv) e rode novamente `python -m src.simulation.runner --mode suite`.
