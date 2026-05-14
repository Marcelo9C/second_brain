from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from app.schemas.localization import normalize_candidate_response_payload
from app.services.providers.base_provider import BaseProvider, ProviderError, ProviderPrompt
from app.services.rubric_generation_service import RubricGenerationError


class CandidateRecommendationService:
    def __init__(
        self,
        *,
        providers: dict[str, BaseProvider],
        default_provider: str = "ollama",
        debug_trace: bool = False,
    ) -> None:
        self.providers = providers
        self.default_provider = default_provider
        self.debug_trace = debug_trace

    def recommend(self, payload: dict[str, Any]) -> dict[str, Any]:
        payload = normalize_candidate_response_payload(payload, require_selection=False)
        candidates = [
            candidate
            for candidate in payload.get("candidate_responses") or []
            if self._clean_optional_text(candidate.get("response_raw"))
        ]
        if not candidates:
            raise ValueError("candidate_responses must contain at least one non-empty candidate.")

        provider_requested = self._clean_optional_text(payload.get("provider"))
        model_requested = self._clean_optional_text(payload.get("model"))
        if not provider_requested:
            raise ValueError("provider is required.")
        if not model_requested:
            raise ValueError("model is required.")

        provider = self._provider(provider_requested)
        allowed_models = [m.get("id", m.get("name")) for m in provider.list_models()]
        model_allowed_by_backend = model_requested in allowed_models if allowed_models else True
        metadata = {
            "provider_requested": provider_requested,
            "model_requested": model_requested,
            "provider_used": None,
            "model_used": None,
            "candidate_count": len(candidates),
            "model_allowed_by_backend": model_allowed_by_backend,
            "generation_failure_type": "none",
            "fallback_applied": False,
            "result_discarded": False,
        }
        trace = self._new_trace(
            payload=payload,
            candidates=candidates,
            provider_requested=provider_requested,
            model_requested=model_requested,
        )
        if not model_allowed_by_backend:
            result = self._failure(
                metadata,
                "model_not_allowed_by_backend",
                "A IA não retornou uma candidata válida. Tente novamente ou selecione uma candidata manualmente.",
            )
            self._set_trace_failure(
                trace,
                generation_failure_type="model_not_allowed_by_backend",
                validation_error=f"Model not allowed: {model_requested}. Recommendation blocked.",
            )
            return self._with_trace(result, trace)

        prompt = self._build_prompt(payload, candidates)
        prompt_text = prompt.as_text()
        self._set_trace_prompt(trace, prompt_text, candidates)
        try:
            provider_result = provider.generate(prompt=prompt, model=model_requested)
        except ProviderError as error:
            result = self._failure(
                {**metadata, "raw_error": str(error)},
                "provider_failed",
                str(error),
            )
            self._set_trace_failure(
                trace,
                generation_failure_type="provider_failed",
                validation_error=str(error),
            )
            return self._with_trace(result, trace)

        metadata.update(
            {
                "provider_used": provider_result.provider_used,
                "model_used": provider_result.model_used,
                "exact_url_called": getattr(provider_result, "exact_url_called", None),
                "response_status": getattr(provider_result, "response_status", None),
                "generation_timestamp": datetime.now(timezone.utc).isoformat(),
                "generation_duration_ms": getattr(provider_result, "duration_ms", 0),
                "approx_prompt_tokens": self._approx_tokens(prompt_text),
                "approx_response_tokens": self._approx_tokens(provider_result.text),
                "response_char_count": len(provider_result.text),
            }
        )
        self._set_trace_provider_response(trace, provider_result.text)

        mismatch = self._audit_mismatch(
            provider_requested=provider_requested,
            model_to_call=model_requested,
            provider_used=provider_result.provider_used,
            model_used=provider_result.model_used,
        )
        if mismatch:
            metadata.update(
                {
                    "fallback_applied": True,
                    "result_discarded": True,
                    "blocked_reason": mismatch["reason"],
                }
            )
            result = self._failure(metadata, "provider_mismatch_discarded", mismatch["message"])
            self._set_trace_failure(
                trace,
                generation_failure_type="provider_mismatch_discarded",
                validation_error=mismatch["message"],
            )
            return self._with_trace(result, trace)

        parsed = self._extract_recommendation(provider_result.text)
        self._set_trace_parsed_response(trace, parsed)
        recommended_id = self._clean_optional_text(parsed.get("recommended_candidate_id"))
        validation_error = None
        if not recommended_id:
            validation_error = "recommended_candidate_id is required."
        elif not any(item["id"] == recommended_id for item in candidates):
            validation_error = "recommended_candidate_id does not match any submitted candidate."
        candidate = next((item for item in candidates if item["id"] == recommended_id), None)
        if candidate is None:
            result = self._failure(
                metadata,
                "invalid_recommendation_response",
                "A IA não retornou uma candidata válida. Tente novamente ou selecione uma candidata manualmente.",
            )
            self._set_trace_failure(
                trace,
                generation_failure_type="invalid_recommendation_response",
                validation_error=validation_error
                or "recommended_candidate_id does not match any submitted candidate.",
            )
            return self._with_trace(result, trace)

        warnings = parsed.get("warnings")
        if not isinstance(warnings, list):
            warnings = []

        result = {
            "success": True,
            "recommended_candidate_id": candidate["id"],
            "recommended_candidate_label": candidate.get("label") or f"Candidate {candidate['id']}",
            "reason": self._clean_optional_text(parsed.get("reason"))
            or "Selected as the strongest editable base for the Golden Response.",
            "warnings": [str(warning) for warning in warnings if str(warning).strip()],
            "metadata": metadata,
        }
        self._set_trace_success(trace)
        return self._with_trace(result, trace)

    def _provider(self, provider_name: str) -> BaseProvider:
        provider = self.providers.get(provider_name)
        if not provider:
            available = ", ".join(sorted(self.providers.keys()))
            raise RubricGenerationError(
                f"Provider '{provider_name}' is not registered. Available providers: {available}."
            )
        if not provider.implemented:
            raise RubricGenerationError(f"Provider '{provider_name}' is not implemented yet.")
        return provider

    def _build_prompt(self, payload: dict[str, Any], candidates: list[dict[str, Any]]) -> ProviderPrompt:
        case_payload = {
            "locale": payload.get("locale"),
            "category": payload.get("category"),
            "prompt": payload.get("prompt"),
            "candidate_responses": [
                {
                    "id": candidate.get("id"),
                    "label": candidate.get("label"),
                    "response_raw": candidate.get("response_raw"),
                }
                for candidate in candidates
            ],
        }
        system_contract = (
            "SYSTEM CONTRACT\n"
            "You help choose the best candidate response to serve as the base for a human-editable Golden Response.\n"
            "Consider prompt adherence, usefulness, clarity, naturalness, context fit, and ease of human editing.\n"
            "Do not write rubrics.\n"
            "Do not finalize the Golden Response.\n"
            "Do not use confidential guidelines or customer-specific examples.\n\n"
            "STRICT JSON MODE\n"
            "Return only a valid JSON object.\n"
            "Use exactly these keys: recommended_candidate_id, reason, warnings.\n"
            "recommended_candidate_id must be one of the provided candidate ids.\n"
            "reason must be short and abstract.\n"
            "warnings must be an array of short strings."
        )
        task_payload = (
            "TASK PAYLOAD\n"
            "Choose the best candidate for a revisable Golden Response draft.\n\n"
            f"{json.dumps(case_payload, ensure_ascii=False, indent=2)}"
        )
        return ProviderPrompt(
            system_contract=system_contract,
            task_payload=task_payload,
            response_schema=self._response_schema_for_candidates(candidates),
        )

    def _response_schema_for_candidates(self, candidates: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "type": "OBJECT",
            "properties": {
                "recommended_candidate_id": {
                    "type": "STRING",
                    "enum": [candidate["id"] for candidate in candidates],
                },
                "reason": {"type": "STRING"},
                "warnings": {
                    "type": "ARRAY",
                    "items": {"type": "STRING"},
                },
            },
            "required": ["recommended_candidate_id", "reason", "warnings"],
        }

    def _extract_recommendation(self, raw_response: str) -> dict[str, Any]:
        try:
            parsed = json.loads(raw_response)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        start = raw_response.find("{")
        end = raw_response.rfind("}")
        if start < 0 or end <= start:
            return {}
        try:
            parsed = json.loads(raw_response[start : end + 1])
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def _failure(
        self,
        metadata: dict[str, Any],
        failure_type: str,
        message: str,
    ) -> dict[str, Any]:
        return {
            "success": False,
            "recommended_candidate_id": None,
            "recommended_candidate_label": None,
            "reason": "",
            "warnings": [message] if message else [],
            "metadata": {
                **metadata,
                "generation_failure_type": failure_type,
            },
        }

    def _new_trace(
        self,
        *,
        payload: dict[str, Any],
        candidates: list[dict[str, Any]],
        provider_requested: str,
        model_requested: str,
    ) -> dict[str, Any] | None:
        if not self.debug_trace:
            return None
        candidate_ids = [candidate["id"] for candidate in candidates]
        return {
            "enabled": True,
            "request_payload": payload,
            "request_summary": {
                "locale": payload.get("locale"),
                "category": payload.get("category"),
                "candidate_ids": candidate_ids,
                "candidate_count": len(candidates),
                "provider_requested": provider_requested,
                "model_requested": model_requested,
            },
            "prompt_summary": {
                "requires_json": True,
                "required_keys": [
                    "recommended_candidate_id",
                    "reason",
                    "warnings",
                ],
                "allowed_candidate_ids": candidate_ids,
            },
            "raw_provider_response": None,
            "parsed_response": None,
            "validation_error": None,
            "endpoint_response": None,
            "generation_failure_type": "none",
        }

    def _set_trace_prompt(
        self,
        trace: dict[str, Any] | None,
        prompt_text: str,
        candidates: list[dict[str, Any]],
    ) -> None:
        if trace is None:
            return
        trace["prompt_summary"] = {
            **trace["prompt_summary"],
            "allowed_candidate_ids": [candidate["id"] for candidate in candidates],
            "prompt_char_count": len(prompt_text),
            "prompt_text": prompt_text,
        }

    def _set_trace_provider_response(self, trace: dict[str, Any] | None, raw_response: str) -> None:
        if trace is not None:
            trace["raw_provider_response"] = raw_response

    def _set_trace_parsed_response(self, trace: dict[str, Any] | None, parsed: dict[str, Any]) -> None:
        if trace is not None:
            trace["parsed_response"] = parsed

    def _set_trace_failure(
        self,
        trace: dict[str, Any] | None,
        *,
        generation_failure_type: str,
        validation_error: str,
    ) -> None:
        if trace is None:
            return
        trace["generation_failure_type"] = generation_failure_type
        trace["validation_error"] = validation_error

    def _set_trace_success(self, trace: dict[str, Any] | None) -> None:
        if trace is not None:
            trace["generation_failure_type"] = "none"

    def _with_trace(self, result: dict[str, Any], trace: dict[str, Any] | None) -> dict[str, Any]:
        if trace is None:
            return result
        endpoint_response = {
            key: value
            for key, value in result.items()
            if key != "metadata"
        }
        endpoint_response["metadata"] = {
            key: value
            for key, value in (result.get("metadata") or {}).items()
            if key != "recommendation_trace"
        }
        trace["endpoint_response"] = endpoint_response
        result["metadata"] = {
            **(result.get("metadata") or {}),
            "recommendation_trace": trace,
        }
        return result

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
                "message": f"Provider usado ({provider_used}) difere do solicitado ({provider_requested}). Recomendacao bloqueada.",
            }
        if model_to_call != model_used:
            return {
                "reason": "provider_executed_different_model",
                "message": f"Modelo usado ({model_used}) difere do autorizado ({model_to_call}). Recomendacao bloqueada.",
            }
        return None

    def _clean_optional_text(self, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _approx_tokens(self, value: str) -> int:
        if not value:
            return 0
        return max(1, round(len(value) / 4))
