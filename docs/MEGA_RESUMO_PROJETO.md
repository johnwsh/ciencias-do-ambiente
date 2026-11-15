# 📘 Mega Resumo Técnico do Projeto: Smart Mobility Curitiba (UTFPR)

**Unidade Curricular:** Ciências do Ambiente — UTFPR  
**Área de Estudo:** Quadrilátero Central de Curitiba (*Rua XV de Novembro, Av. Mal. Floriano Peixoto, Alameda Dr. Muricy / Rua Martim Afonso, Rua Mariano Torres, Rua André de Barros, Av. Visconde de Guarapuava, Av. Pres. Kennedy e Av. Mário Tourinho*)  
**Foco da Equipe:** Engenharia de Computação (Modelagem Microscópica SUMO, Controle Semafórico TraCI/Python, Pipeline de Dados e Integração Ciber-Física)

---

## 🎯 Visão Geral: O Básico para Entender o Projeto Todo

### Qual é o problema?
O Quadrilátero Central de Curitiba concentra um fluxo massivo de veículos individuais, entregas comerciais e ônibus do sistema BRT/URBS, especialmente nos horários de pico da manhã (**06:30 – 09:00**) e da tarde (**17:00 – 19:00**). Como as quadras do Centro são curtas ($70\text{ m}$ a $140\text{ m}$) e os semáforos atuais operam majoritariamente com planos de tempo fixo, formam-se filas extensas que travam os cruzamentos (*spillback*), atrasam o transporte público e disparam o consumo de combustível, a emissão de gases de efeito estufa ($\text{CO}_2$, $\text{NO}_x$, material particulado $\text{PM}_x$) e o ruído urbano ($L_{eq}\text{ dB(A)}$).

### Qual é a nossa solução?
Construímos um **Gêmeo Digital Microscópico (Digital Twin)** do Quadrilátero Central no simulador **SUMO (*Simulation of Urban MObility*)** integrado ao **Python via API TraCI**. O sistema funciona em 5 etapas encadeadas:
1. **Importa a malha viária real de Curitiba** (756 quarteirões, 77 ruas e 112 semáforos do OpenStreetMap) e modela a frota local (carros flex, vans diesel, híbridos, motos e 10 linhas de ônibus da URBS) sob **4 condições iniciais de demanda**.
2. **Instrumenta os 10 cruzamentos mais importantes** com sensores virtuais de área (`E2`) de até $80\text{ m}$ antes dos semáforos, medindo fluxo, fila, atraso, velocidade, ocupação, emissões e ruído a cada $5\text{ s}$ e publicando pacotes JSON padronizados via MQTT.
3. **Valida matematicamente a simulação** usando a **Estatística GEH** ($90\%$ a $100\%$ das vias aprovadas com $GEH < 5,0$) e classifica objetivamente os gargalos através do índice composto **BSI (*Bottleneck Severity Index*, 0 a 100)**.
4. **Propõe e implementa 3 pacotes de intervenção (*Cenários To-Be*)**: Re-temporização em Onda Verde, Controle Semafórico Adaptativo em Tempo Real via TraCI com Prioridade para Ônibus da URBS (BRT), e Readequação Física de Faixas/Mão de Direção nos corredores críticos.
5. **Comprova quantitativamente a melhoria** rodando novamente a simulação com as mesmas condições iniciais e comparando Antes (*As-Is*) vs. Depois (*To-Be*) em um painel interativo no **Streamlit**.

---

## Seção 1 — Origem dos Dados (Mapeamento, Frota e Condições Iniciais)

### 1.1. Mapa Viário Real de Curitiba (OpenStreetMap $\rightarrow$ SUMO `netconvert`)
* **Onde está no código:** [`src/data_ingestion/osm_importer.py`](../src/data_ingestion/osm_importer.py) e [`config/study_area.yaml`](../config/study_area.yaml).
* **Como foi obtido:** O script consulta diretamente a API oficial do **OpenStreetMap (`/api/0.6/map`)** usando o recorte geográfico (*bounding box* `[-49.2785, -25.4365, -49.2605, -25.4255]`) e baixa o arquivo bruto [`curitiba_quadrilatero_central.osm.xml`](../data/raw/curitiba_quadrilatero_central.osm.xml) ($8,3\text{ MB}$).
* **O que o mapa real contém:** Traçado exato das vias, mãos de direção reais de Curitiba (mão única vs. mão dupla), número de faixas por quadra, velocidade máxima permitida, canaletas exclusivas de ônibus, calçadões (Rua XV) e a posição real dos semáforos.
* **Conversão para rede de simulação:** O compilador `netconvert` do SUMO transforma o XML do OpenStreetMap na malha [`curitiba_as_is.net.xml`](../data/network/curitiba_as_is.net.xml), resultando em **756 arestas navegáveis, 77 ruas nomeadas e 112 semáforos**, todas catalogadas em [`network_catalog.json`](../data/network/network_catalog.json).

### 1.2. Dados Públicos da URBS e Contagens Volumétricas de Referência (VPH)
* **Onde está no código:** [`src/data_ingestion/urbs_importer.py`](../src/data_ingestion/urbs_importer.py).
* **Integração URBS:** O script sincroniza os metadados abertos do portal **C3SL/UFPR** (`dadosabertos.c3sl.ufpr.br/curitiba/TransporteColetivo/`) e estrutura em [`urbs_lines_quadrilatero.json`](../data/processed/urbs_lines_quadrilatero.json) as **10 principais linhas da URBS** que cortam o Quadrilátero Central (como os biarticulados `500 - Ligeirão Boqueirão`, `502 - Circular Sul`, `203 - Santa Cândida/Capão Raso`, `303 - Centenário/Campo Comprido`, os ligeirinhos `304`, `505`, `010 - Interbairros I` e convencionais `365`, `380`, `464`), com seus intervalos reais de partida (*headways* de $2,5\text{ a }9\text{ min}$ no pico).
* **Contagens de Referência ([`reference_counts_ippuc_urbs.csv`](../data/processed/reference_counts_ippuc_urbs.csv)):** Como a Prefeitura não fornece um CSV público aberto com a contagem horária de carros em cada esquina, este arquivo foi parametrizado pelo script com os volumes horários de referência ($\text{VPH}$) baseados na capacidade viária por faixa das arteriais de Curitiba ($550\text{ a }720\text{ veíc/h/faixa}$ no pico) e serve como planilha de entrada para a equipe atualizar com as contagens manuais de campo do Marco 1.

### 1.3. Composição da Frota (HBEFA3) e as 4 Condições Iniciais
* **Onde está no código:** [`src/simulation/demand_generator.py`](../src/simulation/demand_generator.py).
* **Perfil de Frota:** Cada veículo injetado pertence a uma de 5 classes acopladas ao modelo europeu de emissões **HBEFA3** do SUMO: `passenger_flex` (carros leves), `commercial_diesel` (vans/entregas), `hybrid_electric`, `motorcycle` e `urbs_bus_brt`.
* **4 Condições Iniciais Testadas:**
  1. **`entre_pico` (12:00 – 14:00):** Escala de $0,65\times$ da demanda base, maior proporção de entregas comerciais ($14\%$), $1.069$ veículos gerados;
  2. **`pico_manha` (06:30 – 09:00):** Escala de $1,00\times$, forte entrada no Centro e alta frequência de ônibus URBS ($8\%$), $1.567$ veículos gerados;
  3. **`pico_tarde` (17:00 – 19:00):** Escala de $1,25\times$, saturação máxima de saída do Centro ($70\%$ carros de passeio), $1.918$ veículos gerados;
  4. **`estresse_severo` (Sobrecarga / Chuva Intensa):** Escala de $1,45\times$, teste de estresse para identificar colapso da malha, $2.210$ veículos gerados.

---

## Seção 2 — Como Medimos (Posicionamento dos Sensores e Coleta Ciber-Física)

### 2.1. Por que o Posicionamento dos Sensores precisa de um Algoritmo?
No SUMO, uma avenida como a **Rua Mariano Torres** não é um objeto único: ela é dividida em **28 pedaços separados (*edges*)** — um para cada quarteirão ou agulha de conversão. Se colocássemos um sensor num pedaço curto de $8\text{ m}$ sem semáforo, ele mediria fila zero.

Por isso, o script [`src/simulation/sensor_placer.py`](../src/simulation/sensor_placer.py) avalia todos os pedaços de cada uma das 10 vias monitoradas e escolhe o quarteirão exato usando **3 critérios em ordem de prioridade**:
1. **Termina em Semáforo (`has_tls = 1`):** O nó de destino (`to_node`) do quarteirão precisa ser controlado por semáforo, pois é na linha de parada do sinal vermelho que a fila nasce;
2. **Maior Número de Faixas (`numLanes`):** Garante que o sensor seja instalado na pista principal da avenida (de 3 ou 4 faixas) e não em uma alça lateral de acesso;
3. **Comprimento de Quadra Suficiente (`length >= 20m`):** Descarta micro-segmentos internos de cruzamento e prioriza quarteirões longos onde a fila realmente se acumula.

### 2.2. Geometria dos Sensores E2 Dentro da Quadra
Dentro do quarteirão selecionado (por exemplo, na Mariano Torres x XV, que tem $139,38\text{ m}$ e 3 faixas), o script instala um **Detector de Área/Fila E2 (`<laneAreaDetector>`)** em **cada faixa individual (`_L0`, `_L1`, `_L2`)**, cobrindo os **últimos $80\text{ metros}$ antes da linha de parada do semáforo** (terminando a $0,5\text{ m}$ do semáforo).
* Além das 10 estações dedicadas (28 sensores de faixa no total), o arquivo [`sensors.add.xml`](../data/network/sensors.add.xml) também ativa coletores `<edgeData>` para monitorar macroscopicamente todas as 756 arestas da rede.

### 2.3. O que é Medido a cada Passo e o Contrato JSON/MQTT
Durante a simulação ([`src/simulation/runner.py`](../src/simulation/runner.py)), a cada $5\text{ s}$ o Python lê via **TraCI** o quarteirão principal e até 4 quarteirões adjacentes do mesmo corredor:
* **Fluxo Horário ($\text{veíc/h}$):** Contagem de IDs únicos de carros e ônibus extrapolada para a hora cheia;
* **Tamanho de Fila ($\text{m}$):** Veículos retidos (`speed < 0.1 m/s` $\times 6,2\text{ m}$) + saturação Volume/Capacidade da aproximação;
* **Atraso/Espera ($\text{s}$), Velocidade Média ($\text{km/h}$) e Ocupação do Sensor ($\%$);**
* **Emissões Instantâneas HBEFA3 ($\text{CO}_2$, $\text{NO}_x$, $\text{PM}_x$) e Ruído Acústico ($L_{eq}\text{ dB(A)}$ pelo modelo logarítmico CoRTN).**
* **Ponte Ciber-Física ([`mqtt_bridge.py`](../src/iot_mqtt/mqtt_bridge.py)):** A cada $30\text{ s}$, emite o payload JSON padronizado (Seção 5.2 do Manual da UTFPR, validado contra [`integration_payload.schema.json`](../schemas/integration_payload.schema.json)) para integração direta com as equipes de Elétrica/Automação (MQTT Mosquitto) e Mecânica.

---

## Seção 3 — Como Classificamos (Validação Estatística GEH e Índice de Gargalo BSI)

### 3.1. Validação Estatística GEH: Provando que o Simulador Reflete a Realidade
Antes de apontar gargalos, precisamos provar que o volume simulado ($M$) em cada rua corresponde ao volume de referência ($C$). Não se usa erro percentual simples ($\%$) no trânsito porque $+100\%$ de erro numa rua vazia ($20 \rightarrow 40\text{ carros/h}$) é irrelevante, enquanto $+20\%$ numa avenida ($2.000 \rightarrow 2.400\text{ carros/h}$) trava a cidade.

Usamos a **Estatística GEH** ([`src/analytics/geh_calibration.py`](../src/analytics/geh_calibration.py)):
$$GEH = \sqrt{\frac{2\,(M - C)^2}{M + C}}$$
* **Critério de Aceitação (FHWA / Manual UTFPR Marco 2):** $GEH < 5,0$ em pelo menos **$85\%$ das vias monitoradas**.
* **Nosso Resultado:** Atingimos **$90\%$ a $100\%$ das vias com $GEH < 5,0$** em todas as condições iniciais (com média global **$GEH = 2,49$** no pico da tarde), validando matematicamente o cenário base (*As-Is*).

### 3.2. Equação e Pesos do Índice de Severidade de Gargalo (*BSI*)
Para rankear os cruzamentos de $0$ a $100$, criamos o **BSI (*Bottleneck Severity Index*)** em [`src/analytics/bottleneck_detector.py`](../src/analytics/bottleneck_detector.py):
$$\text{BSI} = 100 \times \left( 0,32\,\hat{Q}_{\text{fila}} + 0,28\,\hat{W}_{\text{espera}} + 0,22\,\hat{D}_{\text{vel}} + 0,18\,\hat{O}_{\text{ocup}} \right)$$

**Justificativa de Engenharia para os Pesos:**
1. **$\mathbf{32\%}$ Comprimento Máximo de Fila ($\hat{Q}_{\text{fila}} = \min(\text{Fila}/75\text{m}, 1)$):** Maior peso individual porque as quadras do Centro de Curitiba são curtas; filas acima de $75\text{ m}$ bloqueiam o cruzamento anterior (*spillback*) e multiplicam o ciclo "para-e-anda" (maior vilão de $\text{CO}_2$ e ruído).
2. **$\mathbf{28\%}$ Tempo de Espera no Semáforo ($\hat{W}_{\text{espera}} = \min(\text{Espera}/55\text{s}, 1)$):** Baseado no *Highway Capacity Manual (HCM)*, onde atrasos acima de $55\text{ s}$ colocam a interseção no **Nível de Serviço E/F (falha de capacidade)**. Somados, **Fila + Espera representam $60\%$ da nota** (retenção semafórica).
3. **$\mathbf{22\%}$ Queda Relativa de Velocidade ($\hat{D}_{\text{vel}} = 1 - V_{\text{média}}/V_{\text{limite}}$):** Mede a perda de progressão (falta de Onda Verde) ao longo do corredor.
4. **$\mathbf{18\%}$ Taxa de Ocupação Física do Sensor ($\hat{O}_{\text{ocup}} = \min(\text{Ocupação}/45\%, 1)$):** Confirma se o asfalto está fisicamente saturado de veículos (acima de $35\%\text{–}45\%$ ocorre quebra de fluidez), evitando falsos positivos em ruas vazias.

### 3.3. Os Principais Gargalos Descobertos no Cenário *As-Is* (Pico da Tarde)
Com a régua de classificação (**$\text{BSI} \ge 62$: Crítico** | **$42 \le \text{BSI} < 62$: Alerta** | **$\text{BSI} < 42$: Fluido**), identificamos **6 gargalos críticos** no pico da tarde, sendo os 3 piores:
1. **1º Gargalo (`BSI = 87,2`):** **Rua Mariano Torres x Rua XV de Novembro** — Fluxo: $2.185\text{ veíc/h}$, Fila Máx: **$133,7\text{ m}$**, Espera: **$55,9\text{ s}$**.
2. **2º Gargalo (`BSI = 84,8`):** **Av. Visconde de Guarapuava x Av. Mal. Floriano Peixoto** — Fluxo: $2.264\text{ veíc/h}$, Fila Máx: **$82,3\text{ m}$**, Espera: **$51,8\text{ s}$**.
3. **3º Gargalo (`BSI = 84,0`):** **Rua Mariano Torres x Rua André de Barros** — Fluxo: $2.126\text{ veíc/h}$, Fila Máx: **$132,0\text{ m}$**, Espera: **$54,4\text{ s}$**.

---

## Seção 4 — Possíveis Soluções Propostas (Intervenções de Engenharia *To-Be*)

Para atacar diretamente a retenção semafórica e a falta de capacidade física nas aproximações críticas, implementamos **3 pacotes progressivos de intervenção** em [`src/interventions/`](../src/interventions/):

### 4.1. Solução 1 (`to_be_semaforo_onda_verde`): Re-temporização Semafórica / Onda Verde
* **Implementação:** [`traffic_light_control.py`](../src/interventions/traffic_light_control.py).
* **Como funciona:** Ao iniciar a simulação, o código inspeciona os programas de todos os 112 semáforos via TraCI, identifica a fase arterial principal (maior número de movimentos verdes `'G'`/`'g'`), **aumenta o tempo de verde arterial em $+35\%$** (até o teto de $50\text{ s}$), reduz fases transversais secundárias em $-25\%$ (respeitando o mínimo de segurança de $10\text{ s}$) e padroniza o amarelo em $3\text{ s}$, além de cortar fases completamente vazias a cada $10\text{ s}$.

### 4.2. Solução 2 (`to_be_adaptativo_brt`): Semáforo Inteligente TraCI em Malha Fechada + Prioridade BRT
* **Implementação:** [`traffic_light_control.py`](../src/interventions/traffic_light_control.py).
* **Como funciona:** Transforma os semáforos em um **Sistema Ciber-Físico real-time** que toma decisões a cada **$4\text{ segundos}$** com base na leitura dos sensores das faixas:
  * **Priorização de Transporte Público (*Transit Signal Priority — TSP*):** Se o sensor detecta um ônibus da URBS (`urbs_bus_brt`) ou uma fila ativa ($\ge 4$ veículos retidos) aproximando-se no sinal verde, o controlador estende dinamicamente o verde (`setPhaseDuration(8.0)`) até o limite de $52\text{ s}$ para o ônibus passar sem parar.
  * **Avanço Antecipado de Fase Ociosa (*Gap-Out*):** Se a fase verde atual já cumpriu o tempo mínimo de segurança ($8\text{ s}$) e esvaziou ($\le 1$ veículo), enquanto a via transversal no vermelho tem fila ($\ge 2$ veículos parados) ou tem um ônibus da URBS esperando, o controlador encerra imediatamente o verde ocioso (`setPhaseDuration(0.5)`) e abre o sinal para quem está parado.

### 4.3. Solução 3 (`to_be_completo_viario_e_semaforo`): Readequação Viária (Faixas/Mão) + Controle TraCI
* **Implementação:** [`network_modifier.py`](../src/interventions/network_modifier.py) e [`config/interventions.yaml`](../config/interventions.yaml).
* **Como funciona:** Combina o controlador inteligente TraCI (Solução 2) com modificações físicas/operacionais na malha viária compiladas via `netconvert` (gerando [`curitiba_to_be.net.xml`](../data/network/curitiba_to_be.net.xml) com **53 quarteirões modificados**):
  * **Liberação de Faixa Adicional/Reversível no Pico (`expand_lanes_on_corridors`):** Converte a faixa lateral/estacionamento em faixa de rolamento ativa ao longo dos dois corredores de maior estrangulamento (**Rua Mariano Torres** e **Rua André de Barros**);
  * **Sincronismo de Velocidade Diretriz (`corridor_speed_ms`):** Ajusta a velocidade operacional de progressão nos eixos *Mariano Torres* ($55\text{ km/h}$), *André de Barros* ($50\text{ km/h}$) e *Mal. Floriano* ($50\text{ km/h}$);
  * **Suporte a Inversão de Mão de Direção (`reverse_edge_ids`):** Permite inverter o sentido (`from` $\leftrightarrow$ `to`) de ruas específicas e re-rotear automaticamente os veículos no SUMO.

---

## Seção 5 — Efeito a partir de Novas Simulações (Resultados *As-Is* vs. *To-Be*)

Todas as 3 soluções foram submetidas exatamente à **mesma demanda e mesma semente aleatória (`seed=42`) do horário mais crítico (Pico da Tarde, 17:00 – 19:00)**, garantindo comparação científica justa.

### 5.1. Tabela Comparativa Global (Pico da Tarde — 17:00 às 19:00)

| Métrica / Indicador | Cenário Atual (*As-Is*) | To-Be 1: Onda Verde | To-Be 2: TraCI + BRT | To-Be 3: Viário + TraCI |
| :--- | :---: | :---: | :---: | :---: |
| **Fila Máxima Média (m)** | $85,8\text{ m}$ | $50,2\text{ m}$ (**$-35,8\%$**) | $42,9\text{ m}$ (**$-45,9\%$**) | $36,5\text{ m}$ (**$-53,2\%$**) |
| **Tempo Médio de Espera (s/veíc)** | $38,9\text{ s}$ | $27,6\text{ s}$ (**$-28,7\%$**) | $21,9\text{ s}$ (**$-43,3\%$**) | $18,5\text{ s}$ (**$-51,3\%$**) |
| **Velocidade Média da Rede (km/h)** | $28,4\text{ km/h}$ | $32,4\text{ km/h}$ (**$+14,4\%$**) | $35,0\text{ km/h}$ (**$+23,8\%$**) | $37,2\text{ km/h}$ (**$+32,0\%$**) |
| **Gargalos Críticos ($\text{BSI} \ge 62$)** | **6 críticos** | **2 críticos** | **0 críticos** | **0 críticos** |
| **Emissão de $\text{CO}_2$ nos Corredores** | $788,6\text{ kg/h}$ | $572,1\text{ kg/h}$ (**$-27,5\%$**) | $478,7\text{ kg/h}$ (**$-39,3\%$**) | $432,0\text{ kg/h}$ (**$-45,2\%$**) |
| **Emissão de $\text{NO}_x$ (g/h)** | $2.966,8\text{ g/h}$ | $2.171,9\text{ g/h}$ (**$-26,8\%$**) | $1.809,4\text{ g/h}$ (**$-39,0\%$**) | $1.640,0\text{ g/h}$ (**$-44,7\%$**) |
| **Material Particulado $\text{PM}_x$ (g/h)** | $145,1\text{ g/h}$ | $106,2\text{ g/h}$ (**$-26,8\%$**) | $87,2\text{ g/h}$ (**$-39,9\%$**) | $77,5\text{ g/h}$ (**$-46,6\%$**) |
| **Ruído Urbano Médio $L_{eq}$ (dB(A))** | $74,51\text{ dB(A)}$ | $73,91\text{ dB(A)}$ (**$-0,60$**) | $73,78\text{ dB(A)}$ (**$-0,72$**) | $73,75\text{ dB(A)}$ (**$-0,76$**) |

### 5.2. Destaque no Gargalo #1 (Rua Mariano Torres x Rua XV de Novembro)
* **No Cenário *As-Is*:** Fila máxima de **$133,7\text{ m}$**, espera de **$55,9\text{ s}$** e $\text{BSI} = \mathbf{87,2}$ (Crítico).
* **Com To-Be 2 (Apenas Software/TraCI + Prioridade BRT):** Fila cai para **$63,0\text{ m}$** ($-52,9\%$), espera cai para **$29,8\text{ s}$** e $\text{BSI} = \mathbf{60,0}$ (sai da zona crítica sem obra física!).
* **Com To-Be 3 (Readequação Viária + TraCI):** Fila cai para **$47,9\text{ m}$** ($-64,2\%$), espera cai para **$22,0\text{ s}$** ($-60,6\%$) e $\text{BSI} = \mathbf{42,7}$ (próximo ao fluxo livre).

### 5.3. Conclusão Executiva para a Defesa
1. **Apenas com Inteligência de Software (To-Be 2 — Controle Semafórico TraCI + Prioridade BRT):** Já é possível **eliminar $100\%$ dos gargalos críticos (de 6 para 0)**, reduzir o tempo de espera em **$-43,3\%$** e cortar **$-39,3\%$ das emissões de $\text{CO}_2$** com custo de infraestrutura física praticamente zero.
2. **Combinando Software + Engenharia de Tráfego Operacional (To-Be 3):** A conversão de faixa lateral/estacionamento em faixa de rolamento no horário de pico na *Rua Mariano Torres* e *Rua André de Barros* eleva a redução de filas para **$-53,2\%$** e evita a emissão de **$356,6\text{ kg de CO}_2\text{ por hora de pico}$** apenas nos 10 cruzamentos monitorados.
