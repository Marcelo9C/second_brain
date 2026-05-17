# Hermes Changelog

## hermes-advise-v1.1-stability-green

Status: Internal stability marker  
Scope: Hermes Advise deterministic advisor  
Validation: `16 passed`

### Summary

Hermes transitioned from an archived agentic-looking prototype into a deterministic advisory contract.

Hermes now interprets experiment context, returns explainable recommendations, and requires confirmation for every proposed next action.

It does not execute actions.

### Added

- ADR 0001: The Hermes Fallacy.
- Hermes v0 archive posture.
- Hermes Advise contract.
- Hermes Advise acceptance matrix.
- Canonical Advise examples.
- Deterministic Hermes Advisor service.
- `POST /api/hermes/advise`.
- Ask Hermes isolated inspection page.
- Contract tests for advisory behavior and no-side-effect API behavior.
- Golden fixtures and snapshot checks.
- Determinism checks for repeated calls.
- Local latency budget check.
- In-memory `advisor_trace` contract.

### Trace Scope

`advisor_trace` is non-persistent and must not be interpreted as permanent audit evidence.

It exists to support deterministic response inspection, snapshot testing, and local diagnostics.

## hermes-advise-v1.0-contract-green

Status: Superseded internal contract marker  
Validation: `11 passed`

Established the first deterministic Hermes Advise contract with schemas, service layer, endpoint, examples, acceptance matrix, isolated UI, and API tests.

### Diagnostics Covered

- Same generation and judge model family.
- Weak rubric.
- Low preference margin.
- Single-turn dataset overfit.
- Judge conflict.
- Missing margin threshold.
- Missing model selection provenance.
- Local-only setup with insufficient model family diversity.

### Guardrails

- No autonomous execution.
- No model switching.
- No threshold changes.
- No dataset export.
- No hidden retries.
- No LLM calls.
- No external provider calls.
- Ask Hermes remains outside main navigation.

### Supersedes

Hermes v0 archived prototype.

Hermes v0 remains accessible by direct URL only as forensic evidence of the identity gap described in ADR 0001.

## Next Track: Hermes Observe v1

Status: Contract draft only  
Document: [hermes_observe_contract.md](hermes_observe_contract.md)

Hermes Observe is the next proposed track after Advise stabilization.

No code, endpoint, UI, LLM integration, or run-engine integration is introduced by this track yet.

Observe may not begin until the Hermes Advise cooldown exits by evidence.

Cooldown document: [hermes_advise_cooldown.md](hermes_advise_cooldown.md)
