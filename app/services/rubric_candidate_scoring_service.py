from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from app.schemas.localization import normalize_candidate_response_payload, validate_rubric_payload
from app.schemas.rubric_contract import RubricContract
from app.services.providers.base_provider import BaseProvider, ProviderError, ProviderPrompt
from app.services.rubric_generation_service import RubricGenerationError


class RubricCandidateScoringService:
    def __init__(
        self,
        *,
        providers: dict[str, BaseProvider],
        default_provider: str = "ollama",
    ) -> None:
        self.providers = providers
        self.default_provider = default_provider

    def score(
        self,
        payload: dict[str, Any],
        *,
        active_contract: RubricContract | None = None,
    ) -> dict[str, Any]:
        payload = normalize_candidate_response_payload(payload, require_selection=False)
        rubrics = payload.get("rubrics")
        validate_rubric_payload(rubrics, contract=active_contract)

        candidates = [
            candidate
            for candidate in payload.get("candidate_responses") or []
            if self._clean_optional_text(candidate.get("response_raw"))
        ]
        if len(candidates) < 2:
            raise ValueError("candidate_responses must contain at least two non-empty candidates.")

        provider_requested = self._clean_optional_text(payload.get("provider")) or self.default_provider
        model_requested = self._clean_optional_text(payload.get("model"))
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
            "rubric_count": len(rubrics),
            "model_allowed_by_backend": model_allowed_by_backend,
            "scoring_failure_type": "none",
            "fallback_applied": False,
            "result_discarded": False,
        }
        if not model_allowed_by_backend:
            return self._failure(
                metadata,
                "model_not_allowed_by_backend",
                f"Model not allowed: {model_requested}. Candidate scoring blocked.",
            )

        prompt = self._build_prompt(payload, rubrics, candidates)
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
                "scoring_timestamp": datetime.now(timezone.utc).isoformat(),
                "scoring_duration_ms": getattr(provider_result, "duration_ms", 0),
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
            return self._failure(
                {
                    **metadata,
                    "fallback_applied": True,
                    "result_discarded": True,
                    "blocked_reason": mismatch["reason"],
                },
                "provider_mismatch_discarded",
                mismatch["message"],
            )

        try:
            parsed = self._extract_scoring(provider_result.text)
            candidate_scores = self._score_candidates(parsed, rubrics, candidates)
        except ValueError as error:
            return self._failure(
                {
                    **metadata,
                    "raw_model_response": provider_result.text,
                    "validation_error": str(error),
                    "result_discarded": True,
                },
                "invalid_scoring_response",
                str(error),
            )

        preference = self._preference(candidate_scores)
        return {
            "success": True,
            "candidate_scores": candidate_scores,
            "preference": preference,
            "metadata": metadata,
            "raw_model_response": provider_result.text,
            "warnings": preference["warnings"],
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

    def _build_prompt(
        self,
        payload: dict[str, Any],
        rubrics: list[dict[str, Any]],
        candidates: list[dict[str, Any]],
    ) -> ProviderPrompt:
        case_payload = {
            "locale": payload.get("locale"),
            "category": payload.get("category"),
            "chat_history": payload.get("chat_history"),
            "prompt": payload.get("prompt"),
            "golden_response_excerpt": self._truncate(payload.get("golden_response"), 1800),
            "rubrics": [
                {
                    "index": index,
                    "dimension": rubric.get("Rubric_dimensions"),
                    "title": rubric.get("Rubric_title"),
                    "description": rubric.get("Rubrics_description"),
                    "weight": rubric.get("Rubrics_weight"),
                    "is_response_specific": rubric.get("is_response_specific"),
                }
                for index, rubric in enumerate(rubrics, start=1)
            ],
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
            "You are a rubric judge for Localization Trial candidate responses.\n"
            "Apply every rubric independently to every candidate response.\n"
            "Return only structured judgments; do not rewrite any candidate response.\n"
            "Use score_factor 1 when the rubric fully applies, 0.5 when partially applies, and 0 when it does not apply.\n"
            "For negative-weight rubrics, score_factor 1 means the penalty fully applies; 0 means the candidate avoided that failure.\n"
            "Keep rationales short and grounded in the provided case data.\n"
            "Do not use confidential guidelines or examples.\n\n"
            "STRICT JSON MODE\n"
            "Return only a valid JSON object.\n"
            "Use exactly this top-level key: candidate_scores.\n"
            "candidate_scores must contain one object for each candidate.\n"
            "Each candidate object must use exactly these keys: candidate_id, rubric_scores.\n"
            "Each rubric score must use exactly these keys: rubric_index, score_factor, judgment, rationale.\n"
            "rubric_index must match a provided rubric index.\n"
            "score_factor must be one of 0, 0.5, or 1.\n"
            "judgment must be one of: met, partial, not_met."
        )
        task_payload = (
            "TASK PAYLOAD\n"
            f"{json.dumps(case_payload, ensure_ascii=False, indent=2)}"
        )
        return ProviderPrompt(
            system_contract=system_contract,
            task_payload=task_payload,
            response_schema=self._response_schema(rubrics, candidates),
        )

    def _response_schema(
        self,
        rubrics: list[dict[str, Any]],
        candidates: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "type": "OBJECT",
            "properties": {
                "candidate_scores": {
                    "type": "ARRAY",
                    "minItems": len(candidates),
                    "maxItems": len(candidates),
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "candidate_id": {
                                "type": "STRING",
                                "enum": [candidate["id"] for candidate in candidates],
                            },
                            "rubric_scores": {
                                "type": "ARRAY",
                                "minItems": len(rubrics),
                                "maxItems": len(rubrics),
                                "items": {
                                    "type": "OBJECT",
                                    "properties": {
                                        "rubric_index": {
                                            "type": "INTEGER",
                                            "minimum": 1,
                                            "maximum": len(rubrics),
                                        },
                                        "score_factor": {
                                            "type": "NUMBER",
                                            "enum": [0, 0.5, 1],
                                        },
                                        "judgment": {
                                            "type": "STRING",
                                            "enum": ["met", "partial", "not_met"],
                                        },
                                        "rationale": {"type": "STRING"},
                                    },
                                    "required": [
                                        "rubric_index",
                                        "score_factor",
                                        "judgment",
                                        "rationale",
                                    ],
                                },
                            },
                        },
                        "required": ["candidate_id", "rubric_scores"],
                    },
                }
            },
            "required": ["candidate_scores"],
        }

    def _extract_scoring(self, raw_response: str) -> dict[str, Any]:
        try:
            parsed = json.loads(raw_response)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        start = raw_response.find("{")
        end = raw_response.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("Could not find a JSON object in the scoring response.")
        try:
            parsed = json.loads(raw_response[start : end + 1])
        except json.JSONDecodeError as error:
            raise ValueError(f"Generated scoring JSON is invalid: {error.msg}.") from error
        if not isinstance(parsed, dict):
            raise ValueError("Generated scoring response must be a JSON object.")
        return parsed

    def _score_candidates(
        self,
        parsed: dict[str, Any],
        rubrics: list[dict[str, Any]],
        candidates: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        raw_candidate_scores = parsed.get("candidate_scores")
        if isinstance(raw_candidate_scores, dict):
            raw_candidate_scores = [
                {
                    "candidate_id": candidate_id,
                    "rubric_scores": rubric_scores,
                }
                for candidate_id, rubric_scores in raw_candidate_scores.items()
            ]
        if not isinstance(raw_candidate_scores, list):
            raise ValueError("candidate_scores must be a JSON array.")

        candidate_ids = [candidate["id"] for candidate in candidates]
        rubric_by_index = {
            index: rubric
            for index, rubric in enumerate(rubrics, start=1)
        }
        results: list[dict[str, Any]] = []
        seen_candidates: set[str] = set()

        for raw_candidate_score in raw_candidate_scores:
            if not isinstance(raw_candidate_score, dict):
                raise ValueError("candidate score items must be objects.")
            candidate_id = self._clean_optional_text(raw_candidate_score.get("candidate_id"))
            if candidate_id not in candidate_ids:
                raise ValueError("candidate_id does not match any submitted candidate.")
            if candidate_id in seen_candidates:
                raise ValueError(f"duplicate candidate score: {candidate_id}.")
            seen_candidates.add(candidate_id)

            rubric_scores = self._score_rubrics(
                raw_candidate_score.get("rubric_scores"),
                rubric_by_index,
            )
            total_score = round(sum(score["points"] for score in rubric_scores), 4)
            max_positive = sum(
                rubric.get("Rubrics_weight")
                for rubric in rubrics
                if isinstance(rubric.get("Rubrics_weight"), (int, float))
                and not isinstance(rubric.get("Rubrics_weight"), bool)
                and rubric.get("Rubrics_weight") > 0
            )
            max_penalty = sum(
                rubric.get("Rubrics_weight")
                for rubric in rubrics
                if isinstance(rubric.get("Rubrics_weight"), (int, float))
                and not isinstance(rubric.get("Rubrics_weight"), bool)
                and rubric.get("Rubrics_weight") < 0
            )
            results.append(
                {
                    "candidate_id": candidate_id,
                    "candidate_label": next(
                        candidate.get("label") or f"Candidate {candidate_id}"
                        for candidate in candidates
                        if candidate["id"] == candidate_id
                    ),
                    "total_score": total_score,
                    "max_positive_score": max_positive,
                    "max_penalty_score": max_penalty,
                    "rubric_scores": rubric_scores,
                }
            )

        missing_candidates = [candidate_id for candidate_id in candidate_ids if candidate_id not in seen_candidates]
        if missing_candidates:
            raise ValueError("candidate_scores missing candidates: " + ", ".join(missing_candidates) + ".")
        return sorted(results, key=lambda item: candidate_ids.index(item["candidate_id"]))

    def _score_rubrics(
        self,
        raw_rubric_scores: Any,
        rubric_by_index: dict[int, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if isinstance(raw_rubric_scores, dict):
            raw_rubric_scores = [
                {
                    **raw_score,
                    "rubric_index": self._coerce_int(rubric_index),
                }
                for rubric_index, raw_score in raw_rubric_scores.items()
                if isinstance(raw_score, dict)
            ]
        if not isinstance(raw_rubric_scores, list):
            raise ValueError("rubric_scores must be a JSON array.")

        scores: list[dict[str, Any]] = []
        seen_indexes: set[int] = set()
        for raw_score in raw_rubric_scores:
            if not isinstance(raw_score, dict):
                raise ValueError("rubric score items must be objects.")
            rubric_index = raw_score.get("rubric_index")
            if not isinstance(rubric_index, int) or isinstance(rubric_index, bool):
                raise ValueError("rubric_index must be an integer.")
            if rubric_index not in rubric_by_index:
                raise ValueError("rubric_index does not match any submitted rubric.")
            if rubric_index in seen_indexes:
                raise ValueError(f"duplicate rubric score: {rubric_index}.")
            seen_indexes.add(rubric_index)

            score_factor = raw_score.get("score_factor")
            if score_factor not in (0, 0.5, 1):
                raise ValueError("score_factor must be one of 0, 0.5, or 1.")
            judgment = self._clean_optional_text(raw_score.get("judgment"))
            if judgment not in {"met", "partial", "not_met"}:
                raise ValueError("judgment must be one of: met, partial, not_met.")
            rubric = rubric_by_index[rubric_index]
            weight = rubric.get("Rubrics_weight")
            points = round(weight * score_factor, 4)
            scores.append(
                {
                    "rubric_index": rubric_index,
                    "rubric_title": rubric.get("Rubric_title"),
                    "rubric_dimension": rubric.get("Rubric_dimensions"),
                    "weight": weight,
                    "score_factor": score_factor,
                    "judgment": judgment,
                    "points": points,
                    "rationale": self._clean_optional_text(raw_score.get("rationale")) or "",
                }
            )

        missing_indexes = [
            rubric_index
            for rubric_index in sorted(rubric_by_index)
            if rubric_index not in seen_indexes
        ]
        if missing_indexes:
            raise ValueError("rubric_scores missing rubrics: " + ", ".join(map(str, missing_indexes)) + ".")
        return sorted(scores, key=lambda item: item["rubric_index"])

    def _coerce_int(self, value: Any) -> Any:
        try:
            return int(value)
        except (TypeError, ValueError):
            return value

    def _preference(self, candidate_scores: list[dict[str, Any]]) -> dict[str, Any]:
        ranked = sorted(candidate_scores, key=lambda item: item["total_score"], reverse=True)
        warnings: list[str] = []
        if len(ranked) < 2:
            return {
                "chosen_candidate_id": None,
                "rejected_candidate_id": None,
                "margin": None,
                "ranking": [item["candidate_id"] for item in ranked],
                "warnings": ["At least two scored candidates are required for preference output."],
            }

        top = ranked[0]
        second = ranked[1]
        if top["total_score"] == second["total_score"]:
            warnings.append("Top candidates are tied; no automatic chosen/rejected pair was produced.")
            chosen = None
            rejected = None
            margin = 0
        else:
            chosen = top["candidate_id"]
            rejected = ranked[-1]["candidate_id"]
            margin = round(top["total_score"] - ranked[-1]["total_score"], 4)

        return {
            "chosen_candidate_id": chosen,
            "rejected_candidate_id": rejected,
            "margin": margin,
            "ranking": [item["candidate_id"] for item in ranked],
            "warnings": warnings,
        }

    def _failure(
        self,
        metadata: dict[str, Any],
        failure_type: str,
        message: str,
    ) -> dict[str, Any]:
        return {
            "success": False,
            "candidate_scores": [],
            "preference": {
                "chosen_candidate_id": None,
                "rejected_candidate_id": None,
                "margin": None,
                "ranking": [],
                "warnings": [message] if message else [],
            },
            "metadata": {
                **metadata,
                "scoring_failure_type": failure_type,
            },
            "raw_model_response": metadata.get("raw_model_response"),
            "warnings": [message] if message else [],
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
                "message": f"Provider usado ({provider_used}) difere do solicitado ({provider_requested}). Scoring bloqueado.",
            }
        if model_to_call != model_used:
            return {
                "reason": "provider_executed_different_model",
                "message": f"Modelo usado ({model_used}) difere do autorizado ({model_to_call}). Scoring bloqueado.",
            }
        return None

    def _truncate(self, value: Any, max_chars: int) -> str | None:
        if value is None:
            return None
        text = str(value)
        if len(text) <= max_chars:
            return text
        return f"{text[:max_chars]}..."

    def _clean_optional_text(self, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _approx_tokens(self, value: str) -> int:
        if not value:
            return 0
        return max(1, round(len(value) / 4))
