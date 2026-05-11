from __future__ import annotations

import json
from time import perf_counter
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.services.providers.base_provider import BaseProvider, ProviderError, ProviderPrompt, ProviderResult


class OllamaProvider(BaseProvider):
    name = "ollama"
    label = "Ollama Local"
    implemented = True

    def __init__(self, *, base_url: str, fallback_model: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.fallback_model = fallback_model

    def list_models(self) -> list[dict[str, Any]]:
        request = Request(f"{self.base_url}/api/tags", method="GET")
        try:
            with urlopen(request, timeout=10) as response:
                raw = response.read().decode("utf-8")
                data = json.loads(raw) if raw else {}
        except Exception:
            return []

        models = []
        for model in data.get("models", []):
            name = model.get("name")
            if name:
                models.append(
                    {
                        "name": name,
                        "label": name,
                        "provider": self.name,
                        "details": model.get("details", {}),
                    }
                )
        return models

    def default_model(self) -> str | None:
        return self.fallback_model

    def generate(self, *, prompt: ProviderPrompt | str, model: str | None = None) -> ProviderResult:
        model_name = model or self.fallback_model
        exact_url_called = f"{self.base_url}/api/chat"
        system_content = (
            prompt.system_contract
            if isinstance(prompt, ProviderPrompt)
            else "Return only valid JSON. Do not include markdown fences."
        )
        user_content = prompt.task_payload if isinstance(prompt, ProviderPrompt) else prompt
        request_payload = {
            "model": model_name,
            "messages": [
                {
                    "role": "system",
                    "content": system_content,
                },
                {"role": "user", "content": user_content},
            ],
            "stream": False,
            "options": {
                "temperature": 0.1,
                "top_p": 0.9,
                "top_k": 40,
                "num_predict": 1200,
            },
        }
        request = Request(
            exact_url_called,
            data=json.dumps(request_payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        started = perf_counter()
        try:
            with urlopen(request, timeout=180) as response:
                raw = response.read().decode("utf-8")
                response_status = response.status
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace").strip()
            try:
                detail_payload = json.loads(detail) if detail else {}
                detail = detail_payload.get("error") or detail
            except json.JSONDecodeError:
                pass
            message = f"Ollama returned HTTP {error.code}"
            if detail:
                message = f"{message}: {detail}"
            raise ProviderError(message) from error
        except URLError as error:
            raise ProviderError(f"Ollama unreachable: {error.reason}") from error

        data = json.loads(raw) if raw else {}
        content = data.get("message", {}).get("content")
        if not content:
            raise ProviderError("Ollama returned an empty rubric response.")
        return ProviderResult(
            text=content,
            provider_used=self.name,
            model_used=model_name,
            exact_url_called=exact_url_called,
            response_status=response_status,
            duration_ms=round((perf_counter() - started) * 1000),
        )
