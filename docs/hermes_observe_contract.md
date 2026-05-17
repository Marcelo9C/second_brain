# Hermes Observe Contract

Status: Draft  
Owner: DASHEM Technologies  
Depends on:

- [ADR 0001: The Hermes Fallacy](adr_0001_the_hermes_fallacy.md)
- [Hermes Advise Contract](hermes_advise_contract.md)
- [Hermes Changelog](hermes_changelog.md)

## Purpose

Hermes Observe defines how Hermes exposes operational state without pretending to be an agent.

Observe does not recommend, decide, or execute.

It answers:

- Who is in control?
- What is happening now?
- What has already happened?
- What can fail?
- What failed?
- What comes next?

## Non-Goals

- No autonomous execution.
- No recommendations.
- No model switching.
- No threshold changes.
- No retries.
- No dataset export.
- No LLM calls.
- No hidden fallback.

## Mode

```yaml
mode: observe
```

## Operational State

```yaml
operational_state:
  - idle
  - planning
  - generating
  - scoring
  - validating
  - exporting
  - failed
  - completed
```

## Control Provenance

Every observable operational choice must expose provenance.

```yaml
selected_by:
  - user
  - default
  - recommendation
  - fallback
  - retry
  - system

reason:

requires_confirmation:
```

## HermesObserveResponse

```yaml
mode: observe

run:
  run_id:
  status:
  objective:
  created_at:
  completed_at:

control:
  selected_by:
  reason:
  requires_confirmation:

current_stage:
  name:
  status:
  started_at:
  active_models:
  thresholds:

completed_stages:
  - name:
    started_at:
    completed_at:
    outcome:
    selected_by:

failure_conditions:
  - condition:
    severity:
    detection_signal:
    recoverable:

failure:
  reason:
  diagnostics:
  recoverable:
  suggested_actions:

next_expected_action:
  label:
  actor:
  requires_confirmation:

trace:
  run_id:
  stage_started_at:
  stage_completed_at:
  selected_by:
  active_models:
  thresholds:
```

## State Semantics

### idle

No run is active.

### planning

Hermes has received a run configuration and is preparing the deterministic execution plan.

### generating

Hermes is generating candidate prompts or candidate responses.

### scoring

Hermes is applying scoring or rubric logic.

### validating

Hermes is checking whether outputs satisfy acceptance criteria, such as margin threshold and preference-pair completeness.

### exporting

Hermes is preparing an export artifact.

### failed

Hermes stopped because a failure condition was reached.

### completed

Hermes completed the configured pipeline.

## Failure Contract

Failures must be explainable.

```yaml
failure:
  reason: margin_below_threshold
  diagnostics:
    margin: 0.2
    threshold: 1.0
  recoverable: true
  suggested_actions:
    - increase_prompt_difficulty
    - generate_more_candidates
    - send_to_human_review
```

## Acceptance Rules

Hermes Observe must:

- Expose `mode: observe`.
- Expose `current_stage`.
- Expose `completed_stages`.
- Expose `selected_by` for operational choices.
- Expose `failure_conditions`.
- Expose `failure.reason` when failed.
- Expose `next_expected_action`.
- Avoid recommendations unless they are labeled as suggested actions after a failure.

Hermes Observe must not:

- Execute actions.
- Change configuration.
- Start new runs.
- Retry automatically.
- Call LLMs.
- Export datasets.
- Present itself as an autonomous agent.

## Relationship To Advise

Advise interprets and recommends.

Observe reports operational state.

Observe can expose suggested recovery actions after a failure, but it must not select or execute them.

Any future path from Observe to Advise must be explicit and user-initiated.
