# Hermes Advise Endpoint Usage

Internal version: hermes-advise-v1.1-stability-green  
Status: Experimental / Isolated  
Endpoint: `POST /api/hermes/advise`

## Contract

Hermes Advise interprets an experiment context and returns deterministic recommendations.

It does not execute actions.

It does not start runs, change models, change thresholds, export datasets, call LLMs, or call external providers.

## Request

```json
{
  "objective": "generate_dpo_pairs",
  "context": {
    "current_models": {
      "generation": "llama3.2:3b",
      "judge": "llama3.2:3b"
    },
    "rubric": {
      "criteria_count": 2
    },
    "result": {
      "margin": 0.2
    },
    "current_thresholds": {
      "margin": 1.0
    },
    "num_conversations": 1,
    "num_turns": 1
  },
  "constraints": {
    "local_only": true
  },
  "user_preferences": {}
}
```

## Response

```json
{
  "mode": "advise",
  "interpreted_objective": "generate_dpo_pairs",
  "diagnosis": [
    {
      "issue": "generation_and_judge_model_coupling",
      "severity": "high",
      "evidence": "generation=llama3.2:3b, judge=llama3.2:3b",
      "impact": "Shared model families can reduce judgment independence."
    }
  ],
  "recommendations": [
    {
      "action": "diversify_model_families",
      "reason": "shared_family_may_reduce_judgment_independence",
      "selected_by": "recommendation",
      "alternatives_considered": [
        "keep_current_models",
        "use_separate_local_judge",
        "use_cloud_judge_with_confirmation"
      ],
      "confidence": 0.92,
      "requires_confirmation": true
    }
  ],
  "advisor_trace": {
    "request_id": "64-character deterministic hash",
    "rules_evaluated": ["model_independence"],
    "rules_triggered": ["model_independence"],
    "response_hash": "64-character deterministic hash"
  }
}
```

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_hermes_advisor.py tests\test_hermes_advise_api.py
.\.venv\Scripts\python.exe -m pytest tests\test_hermes_advisor_stability.py
node --check web\hermes_advise.js
```

Expected:

```text
16 passed
```
