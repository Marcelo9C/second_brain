# Hermes Advise v1.1 Cooldown

Status: Operational incubation  
Internal version: hermes-advise-v1.1-stability-green  
Duration: 1 to 2 weeks, but exit is evidence-based rather than time-based.
Manual log: [hermes_advise_cooldown_log.yaml](hermes_advise_cooldown_log.yaml)

## Goal

Validate Hermes Advise under internal use before any Observe implementation, Act implementation, LLM integration, or additional rule expansion.

The cooldown separates:

> rule correctness

from:

> operator usefulness

Correct is not the same as useful.

## Constraints

```yaml
constraints:
  no_new_rules: true
  no_observe_implementation: true
  no_act_implementation: true
  no_llm_integration: true
  no_run_engine_integration: true
  no_main_navigation_entry: true
```

## Manual Telemetry

Telemetry may be collected manually during internal use.

No persistence requirement exists for this cooldown.

```yaml
advise_usage:
  total_requests:
  unique_experiment_types:
  recommendations_per_request:
  empty_responses:

trust_signals:
  accepted_recommendations:
  ignored_recommendations:
  disputed_recommendations:

recommendation_quality:
  useful:
  obvious_but_correct:
  noisy:
  wrong:
  missing_expected_recommendation:
```

## Quality Semantics

### useful

The recommendation changed operator understanding or improved the next decision.

### obvious_but_correct

The recommendation is technically right but adds little new operational value.

### noisy

The recommendation is not wrong, but distracts from higher-priority concerns.

### wrong

The recommendation is incorrect for the given experiment context.

### missing_expected_recommendation

Hermes should have detected a meaningful risk but did not.

This is especially important because false negatives can be more expensive than false positives in diagnostic systems.

## Cooldown Exit Criteria

Do not exit cooldown because time elapsed.

Exit only when evidence supports it.

```yaml
cooldown_exit_criteria:
  deterministic_failures: 0
  contract_failures: 0
  latency_budget_violations: 0
  wrong_recommendations: below_threshold
  noisy_recommendations: below_threshold
  missing_expected_recommendations: below_threshold
```

Thresholds must be defined from internal usage volume before the cooldown can close.

## Next Allowed Track

Only after cooldown exit:

> Hermes Observe v1 may begin.

Act remains out of scope.
