from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from app.schemas.localization import (
    REQUIRED_RUBRIC_FIELDS,
    normalize_candidate_response_payload,
    validate_rubric_payload,
)
from app.schemas.rubric_contract import RubricContract
from app.services.providers.base_provider import BaseProvider, ProviderError, ProviderPrompt
from app.services.localization_workflow_engine import (
    CaseStateSnapshot,
    WorkflowDecisionEngine,
    WorkflowDecisionStatus,
    WorkflowIntent,
)


class RubricGenerationError(RuntimeError):
    pass


logger = logging.getLogger(__name__)


class RubricGenerationService:
    def __init__(
        self,
        *,
        providers: dict[str, BaseProvider],
        default_provider: str = "ollama",
        workflow_engine: WorkflowDecisionEngine | None = None,
    ) -> None:
        self.providers = providers
        self.default_provider = default_provider
        self.workflow_engine = workflow_engine or WorkflowDecisionEngine()

    def generate(
        self,
        payload: dict[str, Any],
        *,
        active_contract: RubricContract | None = None,
    ) -> dict[str, Any]:
        payload = normalize_candidate_response_payload(payload, require_selection=True)
        candidate_audit = self._candidate_generation_audit(payload)
        workflow_decision = self.workflow_engine.resolve(
            WorkflowIntent.GENERATE_WITH_AI,
            CaseStateSnapshot.from_payload(payload),
        )
        if not workflow_decision.model_call:
            return {
                "success": False,
                "rubrics": None,
                "metadata": {
                    "generation_executed": False,
                    "generation_failure_type": "none",
                    "workflow_decision": workflow_decision.to_dict(),
                    "fallback_applied": False,
                    **candidate_audit,
                },
                "raw_model_response": None,
                "error": workflow_decision.reason,
                "warning": workflow_decision.message,
                "workflow_decision": workflow_decision.to_dict(),
            }

        provider_requested = self._clean_optional_text(payload.get("provider")) or self.default_provider
        model_requested = self._clean_optional_text(payload.get("model"))
        provider = self._provider(provider_requested)

        default_model_used = False
        if not model_requested:
            model_to_call = provider.default_model()
            if not model_to_call:
                self._log_generation(provider_requested, "none", "error")
                blocked_decision = self._generation_decision(
                    "blocked",
                    reason="default_model_not_configured",
                    message=f"No requested model and no default model available for provider '{provider_requested}'.",
                    base_decision=workflow_decision,
                )
                blocked_decision["model_call"] = False
                return {
                    "success": False,
                    "rubrics": None,
                    "metadata": {
                        "provider_requested": provider_requested,
                        "model_requested": model_requested,
                        "model_to_call": None,
                        "default_model_configured": False,
                        "model_allowed_by_backend": False,
                        "generation_executed": False,
                        "generation_failure_type": "none",
                        "fallback_applied": False,
                        "blocked_reason": "default_model_not_configured",
                        "workflow_decision": blocked_decision,
                        **candidate_audit,
                    },
                    "raw_model_response": None,
                    "error": blocked_decision["message"],
                    "warning": blocked_decision["message"],
                    "workflow_decision": blocked_decision,
                }
            default_model_used = True
        else:
            model_to_call = model_requested

        allowed_models = [m.get("id", m.get("name")) for m in provider.list_models()]
        model_allowed_by_backend = model_to_call in allowed_models if allowed_models else True
        if not model_allowed_by_backend:
            blocked_decision = self._generation_decision(
                "blocked",
                reason="model_not_allowed_by_backend",
                message=f"Model not allowed: {model_to_call}. Generation blocked.",
                base_decision=workflow_decision,
            )
            blocked_decision["model_call"] = False
            return {
                "success": False,
                "rubrics": None,
                "metadata": {
                    "provider_requested": provider_requested,
                    "model_requested": model_requested,
                    "model_to_call": model_to_call,
                    "default_model_used": default_model_used,
                    "model_allowed_by_backend": False,
                    "generation_executed": False,
                    "generation_failure_type": "none",
                    "fallback_applied": False,
                    "blocked_reason": "model_not_allowed_by_backend",
                    "workflow_decision": blocked_decision,
                    **candidate_audit,
                },
                "raw_model_response": None,
                "error": blocked_decision["message"],
                "warning": blocked_decision["message"],
                "workflow_decision": blocked_decision,
            }

        contract = active_contract
        prompt = self._build_prompt(payload, contract=contract)
        prompt_text = prompt.as_text() if isinstance(prompt, ProviderPrompt) else str(prompt)
        
        metadata = {
            "provider_requested": provider_requested,
            "model_requested": model_requested,
            "model_to_call": model_to_call,
            "default_model_used": default_model_used,
            "model_allowed_by_backend": model_allowed_by_backend,
            "fallback_applied": False,
            "result_discarded": False,
            "blocked_reason": None,
            "generation_failure_type": "none",
            "template_used": self._template_name_for_category(payload.get("category")),
            "generation_executed": True,
            **candidate_audit,
        }

        try:
            provider_result = provider.generate(prompt=prompt, model=model_to_call)
        except ProviderError as error:
            self._log_generation(provider_requested, model_to_call, "error")
            failure_decision = self._generation_decision(
                WorkflowDecisionStatus.GENERATION_FAILED.value,
                reason="provider_error",
                message=str(error),
                base_decision=workflow_decision,
            )
            return {
                "success": False,
                "rubrics": None,
                "metadata": {
                    **metadata,
                    "workflow_decision": failure_decision,
                    "raw_error": str(error),
                    "generation_failure_type": "provider_failed",
                    "provider_used": None,
                    "model_used": None,
                },
                "raw_model_response": None,
                "error": str(error),
                "warning": "Provider failed after workflow allowed generation.",
                "workflow_decision": failure_decision,
            }

        mismatch = self._audit_mismatch(
            provider_requested=provider_requested,
            model_to_call=model_to_call,
            provider_used=provider_result.provider_used,
            model_used=provider_result.model_used,
        )
        
        metadata.update({
            "provider_used": provider_result.provider_used,
            "model_used": provider_result.model_used,
            "exact_url_called": getattr(provider_result, "exact_url_called", None),
            "response_status": getattr(provider_result, "response_status", None),
            "generation_timestamp": datetime.now(timezone.utc).isoformat(),
            "generation_duration_ms": getattr(provider_result, "duration_ms", 0),
            "approx_prompt_tokens": self._approx_tokens(prompt_text),
            "approx_response_tokens": self._approx_tokens(provider_result.text),
            "response_char_count": len(provider_result.text),
        })

        if mismatch:
            self._log_generation(provider_result.provider_used, provider_result.model_used, "mismatch")
            metadata.update({
                "fallback_applied": True,
                "result_discarded": True,
                "blocked_reason": mismatch["reason"],
                "generation_failure_type": "provider_mismatch_discarded",
            })
            blocked_decision = self._generation_decision(
                "blocked",
                reason=mismatch["reason"],
                message=mismatch["message"],
                base_decision=workflow_decision,
            )
            return {
                "success": False,
                "rubrics": None,
                "metadata": {**metadata, "workflow_decision": blocked_decision},
                "raw_model_response": None,
                "error": mismatch["message"],
                "warning": "Model fallback detected. Result discarded.",
                "workflow_decision": blocked_decision,
            }

        metadata["workflow_decision"] = workflow_decision.to_dict()

        try:
            rubrics = self._extract_rubrics(provider_result.text, contract=contract)
            validation = self._validate_generated_rubrics(rubrics, contract=contract)
        except RubricGenerationError as error:
            self._log_generation(provider_result.provider_used, provider_result.model_used, "failed")
            return {
                "success": False,
                "rubrics": None,
                "metadata": {
                    **metadata,
                    "validation_status": "failed",
                    "validation_error": str(error),
                    "generation_failure_type": "invalid_rubric_response",
                    "result_discarded": True,
                },
                "raw_model_response": provider_result.text,
                "error": str(error),
                "warning": (
                    "A resposta do modelo falhou na validacao. "
                    "Revise a resposta bruta; nada foi aplicado ao editor."
                ),
            }

        self._log_generation(provider_result.provider_used, provider_result.model_used, validation["status"])
        success_decision = self._generation_decision(
            WorkflowDecisionStatus.GENERATION_SUCCEEDED.value,
            reason="provider_success",
            message="Provider returned rubric JSON after workflow allowed generation.",
            base_decision=workflow_decision,
        )

        return {
            "success": True,
            "rubrics": rubrics,
            "metadata": {
                **metadata,
                "validation_status": validation["status"],
                "workflow_decision": success_decision,
            },
            "raw_model_response": provider_result.text,
            "warning": "Rubrics geradas por IA devem ser revisadas antes da aprovacao.",
            "workflow_decision": success_decision,
        }

    def list_providers(self) -> list[dict[str, Any]]:
        return [provider.summary() for provider in self.providers.values()]

    def list_models(self, provider_name: str) -> list[dict[str, Any]]:
        provider = self._provider_for_listing(provider_name)
        return provider.list_models()

    def _provider(self, provider_name: str) -> BaseProvider:
        provider = self._provider_for_listing(provider_name)
        if not provider.implemented:
            raise RubricGenerationError(f"Provider '{provider_name}' is not implemented yet.")
        return provider

    def _provider_for_listing(self, provider_name: str) -> BaseProvider:
        provider = self.providers.get(provider_name)
        if not provider:
            available = ", ".join(sorted(self.providers.keys()))
            raise RubricGenerationError(
                f"Provider '{provider_name}' is not registered. Available providers: {available}."
            )
        return provider

    def _log_generation(self, provider: str, model: str, status: str) -> None:
        logger.info("provider=%s model=%s status=%s", provider, model, status)

    def _clean_optional_text(self, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _audit_mismatch(
        self,
        *,
        provider_requested: str,
        model_to_call: str,
        provider_used: str,
        model_used: str,
    ) -> dict[str, str] | None:
        if provider_requested != provider_used:
            return {
                "reason": "provider_executed_different_provider",
                "message": f"Provider usado ({provider_used}) difere do solicitado ({provider_requested}). Geracao bloqueada.",
            }
        if model_to_call != model_used:
            return {
                "reason": "provider_executed_different_model",
                "message": f"Modelo usado ({model_used}) difere do autorizado ({model_to_call}). Geracao bloqueada.",
            }
        return None

    def _build_prompt(
        self,
        payload: dict[str, Any],
        *,
        contract: RubricContract | None = None,
    ) -> ProviderPrompt:
        case_payload = {
            "locale": payload.get("locale"),
            "category": payload.get("category"),
            "chat_history": payload.get("chat_history"),
            "prompt": payload.get("prompt"),
            "response_raw": payload.get("response_raw"),
            "golden_response_excerpt": self._truncate(payload.get("golden_response"), 1800),
            "base_template": payload.get("base_template"),
        }
        dimension_lines = (
            "\n".join(f"  - {dimension!r}" for dimension in contract.allowed_dimensions)
            if contract
            else (
                "  - 'Cultural Understanding and Application'\n"
                "  - 'Local Facts and Awareness'\n"
                "  - 'Logic and Formatting'\n"
                "  - 'Natural Language Fluency'"
            )
        )
        if contract:
            weight_policy = contract.weight_policy
            integer_text = "integer " if weight_policy.integer_only else ""
            zero_text = (
                "0 is allowed only when it fits the active contract."
                if weight_policy.zero_allowed
                else "Never use 0."
            )
            weight_lines = (
                f"Rubrics_weight values must follow the active template contract: "
                f"positive {integer_text}weights from {weight_policy.positive_min} to {weight_policy.positive_max}, "
                f"or negative {integer_text}weights from {weight_policy.negative_min} to {weight_policy.negative_max}.\n"
                f"{zero_text}\n"
                f"Never use weights below {weight_policy.negative_min} or above {weight_policy.positive_max}."
            )
        else:
            # Legacy fallback only for records/templates without formal RubricContract.
            weight_lines = (
                "Rubrics_weight values must be from -5 to 10, except 0.\n"
                "Use only integer weights from -5 to -1 for penalties, or 1 to 10 for positive criteria.\n"
                "Never use 0.\n"
                "Never use weights below -5 or above 10."
            )
        system_contract = (
            "SYSTEM CONTRACT\n"
            "You are an expert evaluator for Localization Trial tasks.\n"
            "Your goal is to generate evaluation rubrics similar to those created by high-quality human reviewers.\n"
            "Evaluate localization quality, naturalness, cultural adaptation, instruction following, factuality when relevant, "
            "conversational appropriateness, safety, coherence, grounding, harmfulness, verbosity, formatting, and any other "
            "dimension materially relevant to the case.\n"
            "Generate the appropriate number of rubric objects necessary to fully evaluate the response quality for this localization case.\n"
            "Generate rubrics that are atomic, non-overlapping, discriminative, and useful for a human evaluator.\n"
            "Avoid redundancy and avoid multiple rubrics that reward the same behavior.\n"
            "Cover all major evaluation dimensions relevant to the case without forcing irrelevant dimensions.\n"
            "Prefer completeness and evaluation quality over arbitrary limits.\n"
            "Include negative rubrics when there are important predictable failure modes.\n"
            "When case-specific contextual cues are present, include at least one response-specific rubric.\n"
            "Use varied weights that reflect actual importance; do not assign all rubrics high positive weights.\n"
            "Compare the prompt, response_raw, Golden Response excerpt, locale, category, and chat history when deciding coverage.\n"
            "Reflect meaningful differences between response_raw and the Golden Response excerpt when they matter.\n"
            "Do not infer repeated behavior, prior relationships, identity details, or user preferences unless the case data supports them.\n"
            "Do not invent context that is not supported by the provided case data.\n"
            "Use English for all field values.\n"
            "Do not copy the full Golden Response.\n\n"
            "STRICT JSON MODE\n"
            "RETURN ONLY VALID JSON ARRAY.\n"
            "DO NOT USE MARKDOWN.\n"
            "DO NOT EXPLAIN.\n"
            "DO NOT WRAP IN ```json.\n"
            "OUTPUT MUST START WITH [ AND END WITH ].\n"
            "Use exactly these keys: Rubric_dimensions, Rubric_title, Rubrics_description, "
            "Rubrics_weight, is_response_specific.\n"
            "Rubric_dimensions MUST be exactly one of the following strings:\n"
            f"{dimension_lines}\n"
            "Do not add extra keys.\n"
            f"{weight_lines}\n"
            "Rubrics_weight is schema-critical.\n"
            "Invalid weights cause the entire generation to be rejected.\n"
            "Use positive weights for desirable behavior and negative weights for penalties."
        )
        task_payload = (
            "TASK PAYLOAD\n"
            "Target schema:\n"
            "[{\"Rubric_dimensions\":\"string\",\"Rubric_title\":\"string\","
            "\"Rubrics_description\":\"string\",\"Rubrics_weight\":10,"
            "\"is_response_specific\":false}]\n\n"
            "Case data:\n"
            f"{json.dumps(case_payload, ensure_ascii=False, indent=2)}"
        )
        return ProviderPrompt(system_contract=system_contract, task_payload=task_payload)

    def _extract_rubrics(
        self,
        raw_response: str,
        *,
        contract: RubricContract | None = None,
    ) -> list[dict[str, Any]]:
        try:
            parsed = json.loads(raw_response)
            validate_rubric_payload(parsed, contract=contract)
            return parsed
        except Exception:
            pass

        start = raw_response.find("[")
        end = raw_response.rfind("]")
        if start < 0 or end <= start:
            raise RubricGenerationError("Could not find a JSON array in the model response.")

        extracted = raw_response[start : end + 1]
        try:
            parsed = json.loads(extracted)
        except json.JSONDecodeError as error:
            raise RubricGenerationError(f"Generated rubric JSON is invalid: {error.msg}.") from error

        try:
            validate_rubric_payload(parsed, contract=contract)
        except ValueError as error:
            raise RubricGenerationError(str(error)) from error
            
        return parsed

    def _validate_generated_rubrics(
        self,
        rubrics: list[dict[str, Any]],
        *,
        contract: RubricContract | None = None,
    ) -> dict[str, Any]:
        messages: list[str] = []
        try:
            validate_rubric_payload(rubrics, contract=contract)
        except ValueError as e:
            raise RubricGenerationError(str(e)) from e

        for index, rubric in enumerate(rubrics, start=1):
            required_fields = contract.required_fields if contract else REQUIRED_RUBRIC_FIELDS
            missing = sorted(required_fields - set(rubric.keys()))
            if missing:
                messages.append(f"Rubric {index} is missing: {', '.join(missing)}.")

            weight = rubric.get("Rubrics_weight")
            if contract:
                try:
                    contract.weight_policy.validate_weight(
                        weight,
                        label=f"Rubric {index} weight",
                    )
                except ValueError as error:
                    messages.append(str(error))
            else:
                # Legacy fallback only for records/templates without formal RubricContract.
                if not isinstance(weight, (int, float)):
                    messages.append(f"Rubric {index} weight must be numeric.")
                    continue

                if weight < 0:
                    if not -5 <= weight <= -1:
                        messages.append(f"Rubric {index} negative weight must be between -5 and -1.")
                elif not 1 <= weight <= 10:
                    messages.append(f"Rubric {index} positive weight must be between 1 and 10.")

        if messages:
            raise RubricGenerationError(" ".join(messages))

        return {"status": "valid", "messages": ["Generated rubric JSON passed validation."]}

    def _truncate(self, value: Any, max_chars: int) -> str | None:
        if value is None:
            return None
        text = str(value)
        if len(text) <= max_chars:
            return text
        return f"{text[:max_chars]}..."

    def _approx_tokens(self, value: str) -> int:
        if not value:
            return 0
        return max(1, round(len(value) / 4))

    def _template_name_for_category(self, category: Any) -> str:
        names = {
            "Writing": "writing_template.json",
            "Chitchat": "chitchat_template.json",
            "Knowledge": "knowledge_template.json",
        }
        return names.get(str(category), "base_template")

    def _candidate_generation_audit(self, payload: dict[str, Any]) -> dict[str, Any]:
        metadata = payload.get("metadata") or {}
        candidates = metadata.get("candidate_responses")
        if not isinstance(candidates, list):
            return {
                "candidate_count": 0,
                "selected_candidate_id": None,
                "selected_candidate_label": None,
                "response_raw_resolution": {
                    "mode": "legacy_response_raw",
                    "candidate_id": None,
                },
            }

        selected_candidate_id = metadata.get("selected_candidate_id")
        selected_candidate = next(
            (
                candidate
                for candidate in candidates
                if isinstance(candidate, dict) and candidate.get("id") == selected_candidate_id
            ),
            None,
        )
        return {
            "candidate_count": len(candidates),
            "selected_candidate_id": selected_candidate_id,
            "selected_candidate_label": (
                selected_candidate.get("label") if isinstance(selected_candidate, dict) else None
            ),
            "response_raw_resolution": metadata.get("response_raw_resolution")
            or {
                "mode": "candidate_selected",
                "candidate_id": selected_candidate_id,
            },
            "candidate_responses": candidates,
        }

    def _generation_decision(
        self,
        decision: str,
        *,
        reason: str,
        message: str,
        base_decision: Any,
    ) -> dict[str, Any]:
        payload = base_decision.to_dict() if hasattr(base_decision, "to_dict") else dict(base_decision)
        payload.update(
            {
                "decision": decision,
                "can_execute": decision == WorkflowDecisionStatus.GENERATION_SUCCEEDED.value,
                "model_call": True,
                "reason": reason,
                "message": message,
            }
        )
        return payload
