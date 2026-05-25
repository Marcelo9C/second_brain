# Guia Prático de MLOps: Dominando o Hermes Lab 🧪

Bem-vindo ao **Hermes Lab**! Este guia foi projetado para levar você do zero ao entendimento profundo da avaliação de agentes locais, geração de datasets para DPO/RLHF e diagnóstico estruturado de MLOps.

Agora que você tem o **`hermes:latest`** (seu auditor local leve) e o **`openhermes:latest`** (o gigante de 7B da comunidade) instalados no seu Ollama, você está equipado com o arsenal perfeito.

---

## 🧬 O Fluxo de Trabalho do Hermes Lab

Em MLOps de produção, o comportamento de um agente de IA não pode ser avaliado no "olhômetro". Ele passa por um ciclo rígido de avaliação:

```
  [1. Guia MLOps]        [2. Hermes Advisor]        [3. Orquestrador Runs]
        │                         │                           │
  Aprender Conceitos ───►  Ingerir Contexto JSON ───►  Simulação de Diálogo SxS
                         (Validar Heurísticas)        (Gerar Dataset DPO Real)
```

---

## 🧭 Parte 1: O Playground de Contratos (Hermes Advisor)

O **Hermes Advisor** é o guardião das boas práticas. Ele atua de forma determinística em cima de um arquivo JSON que descreve como foi planejado ou executado um experimento de IA.

### 📝 Passo a Passo do Teste JSON:

1. **Acesse a aba `2. Hermes Advisor`** no painel superior do laboratório.
2. **Selecione um Template de Run** no menu suspenso verde:
   * **SxS Preference Evaluation:** Simula o resultado de uma avaliação lado a lado onde dois modelos responderam e um juiz escolheu o vencedor.
   * **Rubric Case Calibration:** Avalia a qualidade estrutural das rubricas de tradução/localização.
   * **RAG Vector Retrieval:** Simula uma busca em banco vetorial com scores de similaridade.
3. **Clique em "Aplicar Template".** O editor de texto à direita será preenchido com a estrutura JSON.
4. **Clique em "Pedir Diagnóstico" (botão verde na barra lateral esquerda).**

### 🔬 O Teste da Verdade (Quebrando as regras de propósito):

Para ver o Hermes Auditor funcionando em tempo real, vamos forçar falhas estruturais no JSON à direita:

#### Cenário A: O Acoplamento Silencioso (Generation & Judge Coupling)
1. No JSON carregado, localize a chave `"current_models"`.
2. Altere o valor de `"generation"` e `"judge"` para o **mesmo modelo** (ex: ambos `"llama3.2:3b"`).
3. Clique em **Pedir Diagnóstico**.
4. **O que acontece:** O Hermes detectará que a geração e o julgamento usam a mesma família de modelos (reduzindo a independência da avaliação) e gerará um diagnóstico de **Alta Severidade**, sugerindo que você diversifique os modelos.

#### Cenário B: A Margem Fraca (Low Preference Margin)
1. Localize a chave `"result"` no JSON.
2. Altere o valor de `"margin"` para `0.10` (uma margem de vitória muito estreita).
3. Garanta que o `"current_thresholds" -> "margin"` está configurado como `0.50`.
4. Clique em **Pedir Diagnóstico**.
5. **O que acontece:** O Hermes alertará que a separação entre a melhor resposta (Chosen) e a pior resposta (Rejected) é muito fraca para ser usada como dado de treino de DPO confiável, sugerindo descartar o par ou rodar novamente com prompts mais difíceis.

---

## 🤖 Parte 2: O Orquestrador de Runs (Simulação Multiturn Agentic)

Aqui você sai da teoria determinística e coloca as IAs locais para conversar autonomamente na aba **`3. Orquestrador Runs (v0)`**. 

### 🎛️ Configurando o Painel de Controle:

* **Rubric Case:** Escolha a rubrica que definirá os critérios de qualidade (como *"Logic and Formatting"* ou *"Natural Language Fluency"*).
* **Parâmetros da Persona:** É o "agente estressor" simulado. Por exemplo, `"Cliente Impaciente"`, com o perfil de um usuário frustrado e sem tempo.
* **Modelos Ativos:**
  * **Stress Model:** Escolha o **`hermes:latest`** ou **`openhermes`** para gerar as provocações do usuário.
  * **Assistant Model:** Escolha o **`llama3.2:3b`** ou **`phi3:mini`** para atuar como o atendente do suporte.
  * **Scoring Model (O Juiz):** Escolha o **`openhermes`** ou **`hermes:latest`** para analisar as duas alternativas sob o crivo das rubricas.
* **Runs / Turnos:** Defina o tamanho da simulação (sugerimos `1 Run` com `2 Turnos` para testes locais rápidos).

---

## 🏃‍♀️ Executando uma Run e Interpretando o Log Vivo

Clique em **Iniciar Run** (botão verde). O fluxo de MLOps começará a rodar em background no servidor local.

### 📺 O que olhar na Janela de Contexto Vivo:

1. **Ações em Background:** O card da esquerda começará a piscar e mostrará em tempo real qual modelo está sendo chamado:
   ```
   [calling stress model] ──► [calling assistant model] ──► [scoring candidates]
   ```
2. **Contexto de Execução:** Você verá o JSON dinâmico contendo a persona, o prompt atual de estresse gerado, e a lista de candidatas (Resposta A e Resposta B).
3. **Resultado Gerado:** Ao final da run, um card estilizado surgirá no painel central contendo:
   * **Prompt:** A provocação realista em português gerada pela IA de estresse.
   * **Pairing:** O resultado do julgamento do modelo de Scoring, separando o lado vencedor (**Chosen**) do perdedor (**Rejected**) e explicando o motivo com base na rubrica.

---

## 🎯 Por que isso importa na Prática? (O Ciclo MLOps Real)

O que você está fazendo no **Hermes Lab** é o alicerce do alinhamento de IA moderna (RLHF/DPO):

1. **Geração Sintética Dirigida:** Você usa modelos locais menores para gerar variações realistas de diálogos complexos.
2. **Filtragem de Dados:** O Hermes Advisor garante que nenhum par de dados de má qualidade (com margens baixas ou vieses de avaliação) entre no dataset.
3. **Dataset de Preferência Pronto:** Os dados gerados com status `success` formam um dataset perfeito que pode ser exportado para realizar o **Fine-tuning** de modelos maiores (como o Atlas OS), tornando-os excepcionalmente polidos para atendimento local.
