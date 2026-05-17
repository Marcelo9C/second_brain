# Hermes Advise Acceptance Matrix

Status: Experimental / Isolated  
Owner: DASHEM Technologies  
Depends on:

- [ADR 0001: The Hermes Fallacy](adr_0001_the_hermes_fallacy.md)
- [Hermes Advise Contract](hermes_advise_contract.md)
- [Hermes Advise Examples](hermes_advise_examples.yaml)

## Feature

Hermes Advise

## Purpose

Hermes Advise interprets an experiment context and returns deterministic, explainable recommendations without executing any action.

## Must

- Never execute actions.
- Always expose `selected_by`.
- Always expose `reason`.
- Always expose `confidence`.
- Always expose `requires_confirmation`.
- Display advisory-only disclaimer.
- Return deterministic recommendations for canonical cases.
- Return deterministic `advisor_trace`.
- Keep `POST /api/hermes/advise` free of side effects.
- Keep Ask Hermes outside main navigation.

## Must Not

- Start runs.
- Change models.
- Change thresholds.
- Export datasets.
- Trigger retries.
- Call LLMs.
- Call embedding models.
- Call external providers.
- Appear in main navigation.
- Present recommendations as completed actions.

## Current Verification

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_hermes_advisor.py tests\test_hermes_advise_api.py
.\.venv\Scripts\python.exe -m pytest tests\test_hermes_advisor_stability.py
node --check web\hermes_advise.js
```

Expected:

```text
16 passed
```

## Acceptance Cases

| Case | Input Signal | Expected Recommendation | Required Fields |
| --- | --- | --- | --- |
| 001 | Same generation and judge family | `diversify_model_families` | `selected_by`, `reason`, `confidence`, `requires_confirmation` |
| 002 | Rubric criteria count below 3 | `increase_rubric_complexity` | `selected_by`, `reason`, `confidence`, `requires_confirmation` |
| 003 | Margin below threshold | `rerun_with_harder_prompt` | `selected_by`, `reason`, `confidence`, `requires_confirmation` |
| 004 | Single conversation / single turn dataset run | `increase_run_depth_before_export` | `selected_by`, `reason`, `confidence`, `requires_confirmation` |
| 005 | Judge conflict | `send_pair_to_human_review` | `selected_by`, `reason`, `confidence`, `requires_confirmation` |
| 006 | Margin exists without threshold | `define_margin_threshold` | `selected_by`, `reason`, `confidence`, `requires_confirmation` |
| 007 | Required model provenance is incomplete | `record_model_selection_provenance` | `selected_by`, `reason`, `confidence`, `requires_confirmation` |
| 008 | Local-only constraint has one model family | `add_distinct_local_model_before_judging` | `selected_by`, `reason`, `confidence`, `requires_confirmation` |

## Exit Criteria For Next Increment

Only add more diagnostics until the matrix remains green.

Do not introduce Act-mode behavior until a separate Act acceptance matrix exists.
