# Second Brain Lab Operating Model

Status: Active architecture document  
Scope: AI evaluation, training, provenance, and governance lab  
Owner: DASHEM Technologies  
Relationship: supports future Atlas OS by producing validated evidence

## Lab Mission

Second Brain is an internal AI evaluation and training lab.

It exists to test, measure, evaluate, generate datasets, calibrate rubrics, and
audit evidence before any future operational system is allowed to act on that
evidence.

Second Brain must be honest about the state of every artifact. A run, trace,
rubric, recommendation, or export is useful only when its status, provenance,
review state, and limits are visible.

Second Brain does not grant autonomous agency.

## Core Experiment Types

### SxS evaluation

Compares two candidate outputs, models, or prompt variants under controlled
conditions.

Expected evidence:

- input prompt or prompt pair;
- system prompt where applicable;
- generation parameters;
- model labels and reveal state;
- candidate outputs;
- evaluator choice;
- evaluator rationale;
- optional rubric scoring;
- export eligibility state.

### SFT sample preparation

Produces supervised examples from accepted prompt-response pairs.

Expected evidence:

- source experiment or annotation;
- accepted response;
- reviewer rationale or acceptance state;
- dataset export metadata.

### DPO or preference-pair preparation

Produces chosen/rejected pairs for preference optimization.

Expected evidence:

- candidate A and candidate B;
- chosen and rejected outputs;
- scoring or human selection source;
- preference margin where applicable;
- judge warnings or conflicts;
- reviewer decision when needed.

### Rubric calibration

Creates, validates, reviews, and approves rubric cases for later scoring.

Expected evidence:

- case data;
- rubric state;
- structure validation;
- format validation;
- quality validation;
- human review state;
- approval state;
- provider audit when AI generation is used.

### RAG retrieval experiment

Tests retrieval behavior, prompt context assembly, and source traceability.

Expected evidence:

- query text or query embedding;
- embedding model;
- corpus version;
- metadata filters;
- retrieved chunks;
- rank and similarity score;
- selected-for-prompt state;
- retrieval trace.

### SMFP provenance experiment

Tests identity, signing, manifest generation, revision chains, and public
verification for synthetic media artifacts.

Expected evidence:

- content hash;
- signature mode;
- key id;
- manifest;
- revision chain;
- verification result;
- trust score.

### Hermes Advise diagnostic

Runs deterministic advisory checks against experiment context.

Expected evidence:

- request objective;
- context provided by the operator;
- rules evaluated;
- rules triggered;
- diagnosis;
- recommendations;
- tradeoffs;
- proposed next actions.

Hermes Advise output is diagnostic evidence only. It does not approve artifacts,
execute actions, or replace human review.

## Evidence Model

Evidence is structured information that can support a later decision.

Evidence must expose:

- source;
- timestamp or run id when available;
- input context;
- transformation or tool used;
- output;
- validation state;
- review state;
- provenance;
- known limits.

Not every output is evidence. Temporary UI state, partial diagnostics, failed
provider responses, unreviewed generated rubrics, and incomplete traces are not
decision-grade evidence.

## Approved Artifact

An approved artifact is a lab artifact that has passed its required gates and
can be reused by another workflow.

Examples:

- approved rubric case;
- reviewed SFT example;
- reviewed chosen/rejected DPO pair;
- verified SMFP manifest;
- retrieval trace accepted as context evidence;
- validated experiment result with known limits.

Approved does not mean universally correct. It means the artifact has passed the
lab's stated contract for its artifact type.

## Dataset Promotion Rules

An artifact may be promoted into a dataset only when:

- its source experiment or annotation is known;
- required fields are complete;
- model and provider provenance is available where applicable;
- any scoring or preference decision is traceable;
- required human review is complete;
- blocking warnings are resolved or explicitly accepted;
- export format matches the target training use.

Dataset promotion is blocked when:

- the artifact is a scaffold, draft, blocked item, or temporary diagnostic;
- provider fallback was silent or unauthorized;
- a chosen/rejected pair is missing either side;
- a preference pair was synthetically filled;
- rubric quality is pending;
- model identity is unknown where it matters;
- the item contains confidential material that should not be exported.

## Human Review Gates

Human review is required for:

- approving rubric quality;
- approving final rubric cases;
- resolving judge conflicts;
- accepting low-margin preference pairs;
- promoting examples into training datasets;
- authorizing provider or model fallback where such flow exists;
- accepting high-impact or ambiguous Hermes recommendations;
- approving any future Act-mode execution.

Human review should record:

- reviewer identity or role when available;
- decision;
- rationale;
- timestamp;
- artifact version or run id.

## RAG Trace Requirements

RAG traces must preserve enough context to explain what the model saw and why it
was selected.

Required trace fields:

- experiment id or run id;
- retrieval stage;
- query text or query embedding source;
- embedding model;
- corpus version;
- source;
- title;
- section;
- document date where available;
- rank;
- similarity score;
- selected-for-prompt flag;
- chunk text;
- chunk token count;
- metadata.

RAG traces can support evaluation, debugging, and context inspection. They do
not approve answers by themselves.

## Rubric Lifecycle

Rubrics follow the lifecycle defined in:

- [Localization Rubric Lab Contract](localization_rubric_lab_contract.md)

Lifecycle states:

- `template_scaffold`
- `draft`
- `ai_generated`
- `human_reviewed`
- `approved`
- `blocked`

Only `approved` rubric cases may support training-quality claims or dataset
promotion. `ai_generated` means a provider produced candidate rubrics; it does
not mean the rubrics are valid or useful.

## Provenance Requirements

Every decision-grade artifact should expose provenance appropriate to its type.

Operational provenance includes:

- selected by user, default, recommendation, fallback, or retry;
- reason;
- alternatives considered where relevant;
- confidence where relevant;
- confirmation requirement;
- model/provider actually used;
- model/provider requested;
- fallback state;
- raw error when a provider fails.

Content provenance includes:

- content hash;
- signature;
- key id;
- manifest;
- revision chain;
- verification result.

Provenance does not replace quality review. It explains origin, identity, and
decision path.

## Hermes Relationship

Hermes exists inside Second Brain as a governed lab capability.

Current status:

- Hermes v0 is archived.
- Hermes Advise is deterministic and advisory-only.
- Hermes Observe is allowed only after Advise cooldown exits by evidence.
- Hermes Act remains out of scope.

Hermes may use:

- explicit experiment context supplied by the operator;
- rubric metadata;
- scoring summaries;
- thresholds;
- model provenance;
- constraints;
- known warnings;
- lab-approved artifact metadata.

Hermes must not treat these as available unless the calling workflow provides
them through an explicit contract.

Hermes may not use:

- temporary UI state as audit evidence;
- unreviewed rubrics as approved rubrics;
- incomplete preference pairs as dataset evidence;
- hidden provider fallback;
- persisted memory that has not been designed and approved;
- LLM planning during the Advise cooldown.

## Temporary Diagnostics

Temporary diagnostics help local inspection but must not be promoted into audit
or dataset evidence without an explicit contract.

Examples:

- in-memory Hermes `advisor_trace`;
- UI-only progress context;
- smoke-test runs;
- local latency checks;
- debug health responses;
- provider raw output from failed generation;
- draft rubric warnings;
- unreviewed retrieved chunks.

Temporary diagnostics can inform engineering work. They cannot approve
artifacts, close cooldown, or justify autonomous execution.

## Non-Goals

Second Brain does not:

- operate real business workflows;
- act autonomously;
- hide model or provider fallback;
- approve artifacts because JSON is parseable;
- export scaffolds or drafts as final datasets;
- replace human review with Hermes recommendations;
- treat observability as agency;
- treat diagnostic traces as permanent audit records;
- begin Hermes Act from the current lab state.

## Path To Atlas OS

Atlas OS should be born later as an operational layer above evidence validated
inside Second Brain.

The intended relationship:

- **Second Brain:** tests, measures, evaluates, generates datasets, calibrates
  rubrics, and audits.
- **Hermes:** observes and advises inside the lab.
- **Atlas OS:** uses validated knowledge to operate real workflows with
  permissions, memory, tools, and human gates.

Second Brain trains trust.

Atlas OS spends trust.

Atlas OS may consume Second Brain outputs only when those outputs are approved
artifacts or explicitly marked as diagnostic context. The boundary between lab
evidence and operational action must stay explicit.

## Relationship To Atlas OS

The future Atlas OS stack should include:

- agent runtime;
- memory systems;
- tool registry;
- permission scopes;
- human approval gates;
- RAG and semantic retrieval;
- semantic cache;
- cost governor;
- observability;
- replay and audit;
- guardrails;
- workflow execution.

Second Brain should not implement those as operational autonomy yet. It should
produce the calibrated evidence, test cases, traces, datasets, and contracts
that Atlas OS will need before it can act safely.
