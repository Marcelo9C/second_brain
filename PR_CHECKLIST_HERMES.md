# Hermes PR Checklist

Branch: `hermes-advise-v1.1-stability-green`  
Scope: Hermes v0 archive + Hermes Advise v1.1 stability-green  
Purpose: prevent the Hermes identity gap from being reintroduced during review.

## Merge Governance

```yaml
identity_gap_reintroduced: false

new_side_effects_introduced: false

advise_contract_changed: false

acceptance_matrix_updated: true

snapshots_green: true

determinism_green: true

latency_budget_green: true

cooldown_constraints_preserved: true

observe_implemented: false

act_implemented: false

llm_integration_added: false

main_navigation_entry_added: false
```

## Required Verification

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_rubric_candidate_scoring_service.py tests\test_hermes_orchestrator.py tests\test_hermes_advisor.py tests\test_hermes_advise_api.py tests\test_hermes_advisor_stability.py
node --check web\hermes.js
node --check web\hermes_advise.js
```

Expected:

```text
25 passed
```

## Reviewer Questions

- Does Hermes v0 remain archived and outside the main navigation?
- Does Hermes Advise remain advisory-only?
- Does every recommendation expose `selected_by`, `reason`, `confidence`, and `requires_confirmation`?
- Does `advisor_trace` remain in-memory and non-persistent?
- Does the cooldown still block new rules, Observe implementation, Act implementation, LLM integration, and run-engine integration?
- Does this PR preserve the distinction between operator usefulness and rule correctness?

## Explicit Non-Goals

- Do not promote Hermes v0.
- Do not call Hermes an autonomous agent.
- Do not add Act behavior.
- Do not add hidden retries or fallbacks.
- Do not persist cooldown telemetry.
- Do not treat `advisor_trace` as permanent audit evidence.
