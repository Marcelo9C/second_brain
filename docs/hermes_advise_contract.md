# Hermes Advise Contract

Status: Stability Green  
Internal version: hermes-advise-v1.1-stability-green  
Owner: DASHEM Technologies  
Depends on: [ADR 0001: The Hermes Fallacy](adr_0001_the_hermes_fallacy.md)
Canonical examples: [hermes_advise_examples.yaml](hermes_advise_examples.yaml)
Acceptance matrix: [hermes_advise_acceptance_matrix.md](hermes_advise_acceptance_matrix.md)
Changelog: [hermes_changelog.md](hermes_changelog.md)
Cooldown: [hermes_advise_cooldown.md](hermes_advise_cooldown.md)

## Purpose

Hermes Advisor is the proposed reentry point for Hermes after the v0 archive.

It does not execute experiments.

It interprets an experiment request, diagnoses risks, recommends a plan, and asks for human confirmation before any future execution path.

## Non-Goals

- No autonomous execution.
- No model switching without confirmation.
- No dataset export.
- No hidden fallback.
- No implicit retry.

## HermesAdviseRequest

```yaml
objective:
  type: string
  required: true
  examples:
    - generate_dpo_pairs
    - improve_sxs_evaluation
    - diagnose_rubric_quality

context:
  locale:
  category:
  rubric_case_id:
  available_models:
  current_models:
    stress:
    assistant:
    judge:
  current_thresholds:
    margin:
  dataset_goal:
  known_constraints:

constraints:
  max_runtime_minutes:
  local_only:
  allowed_providers:
  forbidden_models:
  require_human_confirmation:

user_preferences:
  preferred_models:
  avoid_cloud:
  prioritize_quality:
  prioritize_speed:
  risk_tolerance:
```

## HermesAdviseResponse

```yaml
mode: advise

interpreted_objective:

diagnosis:
  - issue:
    severity:
    evidence:
    impact:

recommendations:
  - action:
    reason:
    selected_by: recommendation
    alternatives_considered:
    confidence:
    requires_confirmation: true

tradeoffs:
  - option:
    benefit:
    cost:
    risk:

proposed_plan:
  - step:
    purpose:
    expected_output:
    provenance:
      selected_by:
      reason:
      confidence:
      requires_confirmation:

next_actions:
  - label:
    action_type:
    requires_confirmation:

advisor_trace:
  request_id:
  rules_evaluated:
  rules_triggered:
  response_hash:
```

## Deterministic Rules Before LLM

Hermes Advisor must produce useful advice before any LLM planner is introduced.

Initial deterministic diagnostics:

- Same model used for assistant and judge.
- Same provider used across stress, assistant, and judge.
- Only one rubric dimension or very small rubric set.
- `num_conversations=1` and `num_turns=1` for a dataset-quality objective.
- Missing margin threshold.
- Missing explicit model provenance.
- Local-only constraint with no local model diversity.

## Advisor Trace

`advisor_trace` is an in-memory contract field returned with every Advise response.

It is not persisted and must not be treated as a permanent audit log.

It contains:

- `request_id`: deterministic hash of the request payload.
- `rules_evaluated`: deterministic list of evaluated rule ids.
- `rules_triggered`: deterministic list of rule ids that produced recommendations.
- `response_hash`: deterministic hash of the response payload, excluding itself.

## Example

```yaml
mode: advise

interpreted_objective:
  generate higher-quality DPO pairs for pt-BR support conversations

diagnosis:
  - issue: assistant and judge use the same model family
    severity: high
    evidence: assistant=llama3.2:3b, judge=llama3.2:3b
    impact: reduced diversity and weak preference signal

recommendations:
  - action: use different models for assistant and judge
    reason: judgment should be less coupled to generation
    selected_by: recommendation
    alternatives_considered:
      - keep current local-only setup
      - use cloud judge
      - use separate local model as judge
    confidence: medium
    requires_confirmation: true

next_actions:
  - label: apply recommended model split
    action_type: propose_config_patch
    requires_confirmation: true
```
