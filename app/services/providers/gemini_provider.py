from __future__ import annotations

import json
from time import perf_counter
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.services.providers.base_provider import BaseProvider, ProviderError, ProviderPrompt, ProviderResult


class GeminiProvider(BaseProvider):
    name = "gemini"
    label = "Gemini API"
    implemented = True

    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str,
        default_model: str,
        models: tuple[str, ...],
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.default_model_name = default_model
        self.models = models or (default_model,)

    def list_models(self) -> list[dict[str, Any]]:
        return [
            {
                "name": model_name,
                "label": model_name,
                "provider": self.name,
                "default": model_name == self.default_model_name,
                "details": {},
            }
            for model_name in self.models
        ]

    def default_model(self) -> str | None:
        return self.default_model_name

    def generate(self, *, prompt: ProviderPrompt | str, model: str | None = None) -> ProviderResult:
        if not self.api_key:
            raise ProviderError("Gemini API key is not configured.")

        model_name = model or self.default_model_name
        if model_name not in self.models:
            allowed = ", ".join(self.models)
            raise ProviderError(f"Gemini model '{model_name}' is not configured. Allowed models: {allowed}.")

        exact_url_called = f"{self.base_url}/models/{model_name}:generateContent"
        system_contract = (
            prompt.system_contract
            if isinstance(prompt, ProviderPrompt)
            else "Return only a valid JSON array. Do not include markdown, prose, or explanations."
        )
        task_payload = prompt.task_payload if isinstance(prompt, ProviderPrompt) else prompt
        generation_config: dict[str, Any] = {
            "temperature": 0.0,
            "maxOutputTokens": 4096,
            "responseMimeType": "application/json",
        }
        if isinstance(prompt, ProviderPrompt) and prompt.response_schema:
            generation_config["responseSchema"] = prompt.response_schema

        request_payload = {
            "systemInstruction": {
                "parts": [
                    {
                        "text": system_contract,
                    }
                ]
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": task_payload,
                        }
                    ]
                }
            ],
            "generationConfig": generation_config,
        }
        request = Request(
            exact_url_called,
            data=json.dumps(request_payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "X-goog-api-key": self.api_key,
            },
            method="POST",
        )

        started = perf_counter()
        try:
            with urlopen(request, timeout=180) as response:
                raw = response.read().decode("utf-8")
                response_status = response.status
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace").strip()
            message = f"Gemini returned HTTP {error.code}"
            if detail:
                message = f"{message}: {self._safe_error_detail(detail)}"
            raise ProviderError(message) from error
        except URLError as error:
            raise ProviderError(f"Gemini unreachable: {error.reason}") from error
        except TimeoutError as error:
            raise ProviderError("Gemini timed out after 180 seconds.") from error

        data = json.loads(raw) if raw else {}
        try:
            content = data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError) as error:
            raise ProviderError("Gemini returned an unexpected response shape.") from error

        if not content:
            raise ProviderError("Gemini returned an empty rubric response.")
        return ProviderResult(
            text=content,
            provider_used=self.name,
            model_used=model_name,
            exact_url_called=exact_url_called,
            response_status=response_status,
            duration_ms=round((perf_counter() - started) * 1000),
        )

    def _safe_error_detail(self, detail: str) -> str:
        try:
            payload = json.loads(detail)
        except json.JSONDecodeError:
            return detail

        error = payload.get("error")
        if isinstance(error, dict):
            return str(error.get("message") or error.get("status") or "Gemini request failed.")
        return str(payload)
