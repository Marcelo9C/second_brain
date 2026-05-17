# ADR 0001: The Hermes Fallacy

**When Observable Pipelines Pretend to Be Agents**

Status: Accepted  
Owner: DASHEM Technologies  
Type: Architecture Decision Record  
Priority: Critical

## Context

Hermes foi introduzido no Second Brain Lab como uma entidade operacional capaz de orquestrar experimentos de SFT, RLHF, DPO e avaliação SxS.

Embora a interface e o posicionamento sugiram comportamento agentic, a implementação atual é um pipeline determinístico.

Isso criou um **identity gap**:

> O sistema se apresenta como sujeito operacional, mas se comporta como executor rígido.

Consequências:

- perda de confiança
- sensação de arbitrariedade
- falsa expectativa de autonomia
- telemetria sem explicabilidade
- UX percebida como "maquiagem sobre pipeline"

## Problem Statement

Hermes atualmente mistura três contratos incompatíveis:

**Pipeline**

Execução determinística e auditável.

**Advisor**

Interpretação de contexto e recomendação.

**Agent**

Autonomia operacional com intervenção mínima.

O usuário não sabe qual contrato está ativo.

> Arbitrariedade mata confiança em sistemas de IA.

## Design Principle

Every operational decision must carry provenance.

Toda decisão do Hermes deve expor:

```yaml
selected_by:
  - user
  - default
  - recommendation
  - fallback
  - retry

reason:

alternatives_considered:

confidence:

requires_confirmation:
```

Sem isso:

- defaults parecem ocultos
- retries parecem bugs
- fallbacks parecem aleatórios
- autonomia parece falsa

## Decision

Hermes será congelado como feature de produto.

Nenhuma nova feature será adicionada até que o contrato operacional seja definido.

Hermes passa a existir em três modos explícitos:

## Mode 1: Observe

Hermes opera como pipeline observável.

Não simula agência.

Expõe:

- objetivo
- plano
- etapa atual
- modelos usados
- scores
- margins
- thresholds
- decisão
- motivo de falha

Example:

```yaml
mode: observe

objective:
  generate_dpo_pair

execution_plan:
  - generate_candidates
  - run_sxs
  - apply_rubric
  - validate_margin
  - export_pair

result:
  score_a: 8.2
  score_b: 7.1
  margin: 1.1
  threshold: 1.0

decision:
  chosen_rejected_generated
```

## Mode 2: Advise

Hermes interpreta o experimento.

Pode recomendar:

- troca de modelos
- aumento de diversidade
- alteração de rubricas
- aumento de dificuldade

Nunca executa sem confirmação.

Example:

> Seu assistant e judge pertencem à mesma família de modelos. Isso pode reduzir diversidade. Deseja ajustar?

## Mode 3: Act

Hermes executa com autonomia limitada.

Permitido:

- trocar modelos
- refazer turnos
- ajustar thresholds
- repetir scoring
- exportar datasets

Toda ação exige:

- provenance
- confidence
- audit trail
- permission scope

## Immediate Actions

### Freeze Hermes Product Surface

- Sem novas tabs.
- Sem novos painéis.
- Sem novos logs visuais.

### Refactor Around Contract-First Design

Implementar primeiro:

- mode selector
- provenance schema
- operational state model
- decision explanation layer

### Separate From Main Lab

Hermes deixa de ser feature "peer" do lab.

Passa a ser:

> Hermes v0 — Archived Prototype

Reentrada futura:

> Hermes Advisor

## Success Metric

Hermes deixa de parecer mágico.

Hermes passa a parecer confiável.
