from __future__ import annotations

import json
import re
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
    ) -> None:
        self.providers = providers
        self.default_provider = default_provider

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
        if not model_allowed_by_backend:
            return self._failure(
                metadata,
                "model_not_allowed_by_backend",
                f"Model not allowed: {model_requested}. Recommendation blocked.",
            )

        prompt = self._build_prompt(payload, candidates)
        prompt_text = prompt.as_text()
        try:
            provider_result = provider.generate(prompt=prompt, model=model_requested)
        except ProviderError as error:
            return self._failure(
                {**metadata, "raw_error": str(error)},
                "provider_failed",
                str(error),
            )

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
            return self._failure(metadata, "provider_mismatch_discarded", mismatch["message"])

        parsed = self._extract_recommendation(provider_result.text)
        recommended_id = self._resolve_recommended_candidate_id(
            parsed.get("recommended_candidate_id"),
            candidates,
        )
        candidate = next((item for item in candidates if item["id"] == recommended_id), None)
        if candidate is None:
            return self._failure(
                {**metadata, "raw_model_response": provider_result.text},
                "invalid_recommendation_response",
                "recommended_candidate_id does not match any submitted candidate.",
            )

        warnings = parsed.get("warnings")
        if not isinstance(warnings, list):
            warnings = []

        return {
            "success": True,
            "recommended_candidate_id": candidate["id"],
            "recommended_candidate_label": candidate.get("label") or f"Candidate {candidate['id']}",
            "reason": self._clean_optional_text(parsed.get("reason"))
            or "Selected as the strongest editable base for the Golden Response.",
            "warnings": [str(warning) for warning in warnings if str(warning).strip()],
            "metadata": metadata,
        }

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
        return ProviderPrompt(system_contract=system_contract, task_payload=task_payload)

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

    def _resolve_recommended_candidate_id(
        self,
        raw_candidate_id: Any,
        candidates: list[dict[str, Any]],
    ) -> str | None:
        value = self._clean_optional_text(raw_candidate_id)
        if not value:
            return None

        candidate_ids = {str(candidate.get("id")) for candidate in candidates}
        if value in candidate_ids:
            return value

        normalized = value.upper().strip()
        normalized = re.sub(r"^(CANDIDATE|CANDIDATA|CANDIDATO)\s*[:#._-]?\s*", "", normalized)
        normalized = normalized.strip()
        if normalized in candidate_ids:
            return normalized

        matches = {
            match
            for match in re.findall(r"\b[A-D]\b", value.upper())
            if match in candidate_ids
        }
        return next(iter(matches)) if len(matches) == 1 else None

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
