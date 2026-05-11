from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from app.schemas.localization import REQUIRED_RUBRIC_FIELDS, validate_rubric_payload
from app.services.providers.base_provider import BaseProvider, ProviderError, ProviderPrompt


class RubricGenerationError(RuntimeError):
    pass


logger = logging.getLogger(__name__)


class RubricGenerationService:
    def __init__(
        self,
        *,
        providers: dict[str, BaseProvider],
        default_provider: str = "ollama",
    ) -> None:
        self.providers = providers
        self.default_provider = default_provider

    def generate(self, payload: dict[str, Any]) -> dict[str, Any]:
        provider_requested = self._clean_optional_text(payload.get("provider")) or self.default_provider
        model_requested = self._clean_optional_text(payload.get("model"))
        provider = self._provider(provider_requested)

        fallback_model = provider.default_model() if not model_requested else None
        log_model = model_requested or fallback_model or "none"
        if not model_requested and not fallback_model:
            self._log_generation(provider_requested, "none", "error")
            raise RubricGenerationError(f"No model available for provider '{provider_requested}'.")

        prompt = self._build_prompt(payload)
        prompt_text = prompt.as_text() if isinstance(prompt, ProviderPrompt) else str(prompt)
        try:
            provider_result = provider.generate(prompt=prompt, model=model_requested)
        except ProviderError as error:
            self._log_generation(provider_requested, log_model, "error")
            raise RubricGenerationError(str(error)) from error

        mismatch = self._audit_mismatch(
            provider_requested=provider_requested,
            model_requested=model_requested,
            provider_used=provider_result.provider_used,
            model_used=provider_result.model_used,
        )
        if mismatch:
            self._log_generation(provider_result.provider_used, provider_result.model_used, "mismatch")
            raise RubricGenerationError(mismatch)

        metadata = {
            "provider_requested": provider_requested,
            "model_requested": model_requested,
            "provider_used": provider_result.provider_used,
            "model_used": provider_result.model_used,
            "exact_url_called": provider_result.exact_url_called,
            "response_status": provider_result.response_status,
            "generation_timestamp": datetime.now(timezone.utc).isoformat(),
            "template_used": self._template_name_for_category(payload.get("category")),
            "mismatch": False,
            "generation_duration_ms": provider_result.duration_ms,
            "approx_prompt_tokens": self._approx_tokens(prompt_text),
            "approx_response_tokens": self._approx_tokens(provider_result.text),
            "response_char_count": len(provider_result.text),
        }

        try:
            rubrics = self._extract_rubrics(provider_result.text)
            validation = self._validate_generated_rubrics(rubrics)
        except RubricGenerationError as error:
            self._log_generation(provider_result.provider_used, provider_result.model_used, "failed")
            return {
                "success": False,
                "rubrics": None,
                "metadata": {
                    **metadata,
                    "validation_status": "failed",
                    "validation_error": str(error),
                },
                "raw_model_response": provider_result.text,
                "error": str(error),
                "warning": (
                    "A resposta do modelo falhou na validacao. "
                    "Revise a resposta bruta; nada foi aplicado ao editor."
                ),
            }

        self._log_generation(provider_result.provider_used, provider_result.model_used, validation["status"])

        return {
            "success": True,
            "rubrics": rubrics,
            "metadata": {
                **metadata,
                "validation_status": validation["status"],
            },
            "raw_model_response": provider_result.text,
            "warning": "Rubrics geradas por IA devem ser revisadas antes da aprovacao.",
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
        model_requested: str | None,
        provider_used: str,
        model_used: str,
    ) -> str | None:
        if provider_requested != provider_used:
            return (
                f"Provider usado ({provider_used}) difere do solicitado "
                f"({provider_requested}). Geracao bloqueada."
            )
        if model_requested and model_requested != model_used:
            return (
                f"Modelo usado ({model_used}) difere do solicitado "
                f"({model_requested}). Geracao bloqueada."
            )
        return None

    def _build_prompt(self, payload: dict[str, Any]) -> ProviderPrompt:
        case_payload = {
            "locale": payload.get("locale"),
            "category": payload.get("category"),
            "chat_history": payload.get("chat_history"),
            "prompt": payload.get("prompt"),
            "response_raw": payload.get("response_raw"),
            "golden_response_excerpt": self._truncate(payload.get("golden_response"), 1800),
            "base_template": payload.get("base_template"),
        }
        system_contract = (
            "SYSTEM CONTRACT\n"
            "You are an expert evaluator for Localization Trial tasks.\n"
            "Your goal is to generate evaluation rubrics similar to those created by high-quality human reviewers.\n"
            "Evaluate localization quality, naturalness, cultural adaptation, instruction following, factuality when relevant, "
            "conversational appropriateness, safety, coherence, grounding, harmfulness, verbosity, formatting, and any other "
            "dimension materially relevant to the case.\n"
            "Generate the appropriate number of rubric objects necessary to fully evaluate the response quality for this localization case.\n"
            "Avoid redundancy.\n"
            "Cover all major evaluation dimensions relevant to the case.\n"
            "Prefer completeness and evaluation quality over arbitrary limits.\n"
            "Include positive and negative rubrics when they materially improve evaluation coverage.\n"
            "Make rubrics case-specific when appropriate.\n"
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
            "Do not add extra keys.\n"
            "Positive Rubrics_weight values: 5 to 10.\n"
            "Negative Rubrics_weight values: -10 to -5."
        )
        task_payload = (
            "TASK PAYLOAD\n"
            "Target schema:\n"
            "[{\"Rubric_dimensions\":\"string\",\"Rubric_title\":\"string\","
            "\"Rubrics_description\":\"string\",\"Rubrics_weight\":10,"
            "\"is_response_specific\":false}]\n\n"
            "Few-shot shape example:\n"
            "[\n"
            "  {\n"
            "    \"Rubric_dimensions\": \"Task Fulfillment\",\n"
            "    \"Rubric_title\": \"Addresses the User Request\",\n"
            "    \"Rubrics_description\": \"The response directly addresses the user's request in the expected locale and style.\",\n"
            "    \"Rubrics_weight\": 8,\n"
            "    \"is_response_specific\": false\n"
            "  },\n"
            "  {\n"
            "    \"Rubric_dimensions\": \"Safety and Quality\",\n"
            "    \"Rubric_title\": \"Avoids Unsupported Claims\",\n"
            "    \"Rubrics_description\": \"The response does not introduce unsupported facts, promises, or details not grounded in the case.\",\n"
            "    \"Rubrics_weight\": -7,\n"
            "    \"is_response_specific\": false\n"
            "  }\n"
            "]\n\n"
            "Case data:\n"
            f"{json.dumps(case_payload, ensure_ascii=False, indent=2)}"
        )
        return ProviderPrompt(system_contract=system_contract, task_payload=task_payload)

    def _extract_rubrics(self, raw_response: str) -> list[dict[str, Any]]:
        try:
            parsed = json.loads(raw_response)
            validate_rubric_payload(parsed)
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

        validate_rubric_payload(parsed)
        return parsed

    def _validate_generated_rubrics(self, rubrics: list[dict[str, Any]]) -> dict[str, Any]:
        messages: list[str] = []
        validate_rubric_payload(rubrics)

        for index, rubric in enumerate(rubrics, start=1):
            missing = sorted(REQUIRED_RUBRIC_FIELDS - set(rubric.keys()))
            if missing:
                messages.append(f"Rubric {index} is missing: {', '.join(missing)}.")

            weight = rubric.get("Rubrics_weight")
            if not isinstance(weight, (int, float)):
                messages.append(f"Rubric {index} weight must be numeric.")
                continue

            if weight < 0:
                if not -10 <= weight <= -5:
                    messages.append(f"Rubric {index} negative weight must be between -10 and -5.")
            elif not 5 <= weight <= 10:
                messages.append(f"Rubric {index} positive weight must be between 5 and 10.")

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
