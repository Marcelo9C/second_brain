# Localization Rubric Lab Contract

## 1. Objetivo

O Localization Rubric Lab deve apoiar a criacao, revisao, auditoria e aprovacao de rubrics para casos de localization annotation. O sistema deve preservar uma separacao clara entre scaffolds, rascunhos, geracao assistida por IA, revisao humana e aprovacao final.

O lab deve ser honesto sobre o estado real do trabalho: ele pode validar JSON, conferir formato, registrar auditoria e orientar revisao, mas nao deve apresentar templates ou resultados nao revisados como rubrics finais.

## 2. Escopo e Nao Escopo

Escopo:

- Fluxo Localization Rubrics Annotation / Trial Localization.
- Criacao e salvamento de drafts.
- Uso de templates apenas como scaffolds.
- Geracao por IA somente quando houver dados reais suficientes do caso.
- Validacao em camadas.
- Auditoria de provider, modelo, payload e resultado.
- Gates para revisao e aprovacao.
- Mensagens de UI que descrevem o estado real do caso.

Nao escopo:

- Outros projetos ou fluxos de anotacao.
- Uso de material confidencial como fixture, prompt persistido, documentacao versionada ou exemplo real.
- Geracao de rubrics simuladas sem dados suficientes.
- Fallback silencioso de modelo ou provider.
- Aprovacao automatica baseada apenas em JSON parseavel.
- Exportacao de templates como resultado final.

## 3. Estados

### template_scaffold

Estado de um material inicial usado como ponto de partida. Pode conter sugestoes estruturais, slots ou criterios genericos, mas nao representa rubrics finais do caso.

Regras:

- Nao pode ser aprovado diretamente.
- Nao pode ser exportado como final sem revisao humana.
- Nao deve ser contado como resultado gerado.
- Deve ser exibido como scaffold, nao como rubrics validas.

### draft

Estado editavel de um caso em preparacao. Pode estar incompleto.

Regras:

- Pode ser salvo com campos pendentes.
- Deve indicar incompletude quando faltarem campos necessarios para geracao ou aprovacao.
- Nao implica revisao de qualidade.

### ai_generated

Estado de rubrics geradas por IA a partir de um caso real preenchido.

Regras:

- Deve manter auditoria da chamada.
- Deve armazenar output bruto e output parseado separadamente.
- Deve exigir revisao humana antes de reviewed ou approved.
- Nao pode ser criado se a chamada falhar.

### human_reviewed

Estado de rubrics revisadas por avaliador humano.

Regras:

- Exige revisao explicita de qualidade.
- Deve registrar que a revisao humana ocorreu.
- Nao implica aprovacao final automaticamente.

### approved

Estado final de aprovacao dentro do lab.

Regras:

- Exige que todas as camadas obrigatorias estejam em pass.
- Exige campos obrigatorios preenchidos.
- Exige revisao humana.
- Deve ser bloqueado quando houver erro bloqueante.

### blocked

Estado operacional para uma acao impedida por regra do sistema.

Regras:

- Deve informar a causa do bloqueio.
- Nao deve alterar rubrics existentes como se houvesse novo resultado.
- Nao deve chamar API quando o bloqueio for detectavel localmente.

## 4. Campos Obrigatorios Para Geracao Por IA

A acao de gerar rubrics com IA exige:

- `locale`
- `category`
- `prompt`
- `response_raw`
- `golden_response`

Se qualquer campo obrigatorio estiver ausente ou insuficiente, o sistema deve bloquear a geracao antes de chamar provider externo ou local.

Mensagem esperada:

```text
Nao e possivel gerar rubrics: preencha Prompt, Response_raw e Golden Response. As rubrics precisam ser derivadas do caso real, nao simuladas.
```

## 5. Camadas Conceituais

### JSON parseavel

Significa apenas que o conteudo pode ser lido como JSON. Nao garante schema, qualidade ou aprovacao.

### Estrutura valida

Significa que o JSON tem a forma esperada, como array de objetos com campos obrigatorios. Nao garante regras formais nem qualidade.

### Formato valido

Significa que os valores seguem regras formais do sistema, como tipos, ranges, dimensoes aceitas e campos em idioma esperado. Nao garante qualidade substantiva.

### Qualidade revisada

Significa que um avaliador humano revisou as rubrics contra o caso real, verificando relevancia, atomicidade, cobertura, clareza, pesos e alinhamento com o resultado esperado.

### Aprovacao final

Significa que o caso passou pelas camadas exigidas e pode ser tratado como aprovado no fluxo do lab.

## 6. Validacoes Em Camadas

### structureValidation

Confere apenas:

- JSON parseavel.
- Array nao vazio.
- Cada item e um objeto.
- Campos obrigatorios presentes:
  - `Rubric_dimensions`
  - `Rubric_title`
  - `Rubrics_description`
  - `Rubrics_weight`
  - `is_response_specific`

Resultado possivel:

- `pass`
- `fail`

Mensagem permitida:

```text
N rubrics encontradas. Campos obrigatorios presentes.
```

### formatValidation

Confere regras formais e mecanicas:

- Tipos dos campos.
- Dimensoes dentro do conjunto aceito pelo sistema.
- Peso numerico dentro da escala configurada.
- `is_response_specific` booleano.
- Titulo curto e nao vazio.
- Descricao nao vazia e avaliavel.

Resultado possivel:

- `pass`
- `fail`
- `pending`

Mensagem permitida:

```text
Estrutura e formato OK. Qualidade ainda nao avaliada.
```

### qualityValidation

Confere qualidade real das rubrics contra o caso:

- Criterios atomicos.
- Criterios self-contained.
- Criterios objetivamente avaliaveis.
- Ausencia de redundancia desnecessaria.
- Cobertura dos aspectos relevantes do caso.
- Pesos coerentes com importancia.
- Uso adequado de `is_response_specific`.
- Consistencia com `prompt`, `response_raw` e `golden_response`.
- Ausencia de criterio irrelevante, falso ou subjetivo demais.

Resultado possivel:

- `pass`
- `fail`
- `pending`

Mensagem permitida:

```text
Qualidade pendente: revise atomicidade, cobertura, pesos, relevancia e is_response_specific.
```

### approvalReadiness

Confere se o caso pode ser aprovado:

- `structureValidation = pass`
- `formatValidation = pass`
- `qualityValidation = pass`
- Campos obrigatorios preenchidos.
- Revisao humana registrada.
- Sem erro bloqueante.

Resultado possivel:

- `pass`
- `blocked`

Mensagem permitida:

```text
Rubrics prontas para aprovacao.
```

Mensagem de bloqueio permitida:

```text
Bloqueado: qualidade ainda nao revisada.
```

## 7. Regras De Bloqueio

- Nao gerar rubrics com IA sem campos obrigatorios.
- Nao aprovar `template_scaffold`.
- Nao aprovar sem revisao de qualidade.
- Nao aprovar se houver validacao pendente ou falha.
- Nao reaproveitar resultado anterior apos erro de API.
- Nao substituir rubrics existentes quando a geracao falhar.
- Nao marcar como `ai_generated` quando nenhuma chamada bem-sucedida ocorreu.
- Nao exportar como final quando o estado for `draft`, `template_scaffold` ou `blocked`.

## 8. Regras Anti-Fallback

- Default model e fallback sao conceitos diferentes.
- Default model e o modelo usado quando nenhum modelo foi solicitado pelo usuario.
- O uso de default model deve ser exibido e auditado antes/depois da chamada.
- Fallback e a substituicao de um modelo ou provider solicitado por outro.
- Registrar provider solicitado.
- Registrar modelo solicitado pelo usuario.
- Registrar modelo realmente executado.
- Registrar status da chamada.
- Registrar erro bruto quando houver falha.
- Registrar se fallback foi aplicado.
- Bloquear modelo nao configurado antes da chamada.
- Fallback automatico e proibido.
- Fallback silencioso e proibido.
- Fallback so pode ocorrer com autorizacao explicita antes da chamada, se essa opcao existir no futuro.
- Nunca trocar modelo silenciosamente.
- Nunca chamar outro provider sem confirmacao explicita.
- Nunca apresentar resultado anterior como novo resultado.

Mensagem obrigatoria para modelo nao configurado:

```text
Modelo nao configurado: {{model}}. Nenhuma rubrica foi gerada.
```

## 9. Regras De UI Honesta

Mensagens permitidas:

- `Template carregado. Preencha o caso real e revise antes de aprovar.`
- `N rubrics encontradas no JSON.`
- `Campos obrigatorios presentes.`
- `Estrutura OK; qualidade nao revisada.`
- `Nao e possivel gerar rubrics sem Prompt, Response_raw e Golden Response.`
- `Qualidade pendente de revisao.`
- `Rubrics com possiveis problemas: revise atomicidade, cobertura, pesos, relevancia e is_response_specific.`
- `Rubrics revisadas e aprovadas conforme as regras do lab.`

Mensagens proibidas quando houver apenas estrutura ou template:

- `Rubrics validas.`
- `Rubrics aprovadas.`
- `Prontas.`
- `Ready.`
- `Qualidade validada.`
- `Conforme guideline.`
- `Gerado por IA` quando a chamada falhou ou foi bloqueada.

## 10. Matriz De Regras Tecnicas

| Regra tecnica do sistema | Comportamento esperado |
| --- | --- |
| Novo draft criado | Editor de rubrics inicia vazio ou explicitamente marcado como scaffold, sem declarar rubrics validas. |
| Template carregado | UI informa que e scaffold e exige caso real e revisao antes de aprovacao. |
| JSON parseavel | Sistema informa apenas que o JSON foi parseado. |
| Campos obrigatorios presentes | Sistema informa estrutura OK, sem declarar qualidade. |
| Formato mecanico correto | Sistema informa formato OK e qualidade pendente. |
| Qualidade nao revisada | `reviewed` e `approved` permanecem bloqueados ou exigem revisao explicita. |
| Falta `prompt` | Geracao por IA bloqueada antes da chamada. |
| Falta `response_raw` | Geracao por IA bloqueada antes da chamada. |
| Falta `golden_response` | Geracao por IA bloqueada antes da chamada. |
| Modelo nao configurado | Chamada bloqueada e nenhuma rubric e gerada. |
| Provider retorna erro | Output anterior nao e reaproveitado e editor nao e sobrescrito. |
| Provider retorna sucesso | Output bruto e parseado sao registrados separadamente. |
| Modelo executado difere do solicitado | Resultado e invalido por padrao; caso fica bloqueado, nenhuma aprovacao e permitida, e a divergencia deve ser corrigida ou explicitamente autorizada em nova geracao. |
| Fallback nao autorizado detectado | Geracao bloqueada; UI e auditoria informam o motivo. Nenhuma rubric e gerada. |
| Template sem caso real | Nao pode ser approved nem exportado como final. |
| Aprovacao solicitada | Sistema avalia todas as camadas e bloqueia se qualquer uma estiver pendente/falhando. |

## 11. Criterios De Aceite Do Sprint 0

- Este arquivo existe em `docs/localization_rubric_lab_contract.md`.
- O documento contem apenas regras tecnicas abstratas.
- O documento nao contem material confidencial do cliente.
- O documento nao contem OCR, prints ou transcricoes de guideline.
- O documento nao contem exemplos reais, prompts reais ou outputs reais.
- O documento nao menciona conteudo proprietario.
- O documento define estados, validacoes, bloqueios, anti-fallback, UI honesta e matriz tecnica.
- Nenhum codigo funcional foi alterado neste sprint.
- Nenhum teste, fixture ou artefato com conteudo real foi criado.
