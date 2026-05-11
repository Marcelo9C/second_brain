from __future__ import annotations

from typing import Any

from app.services.providers.base_provider import BaseProvider, ProviderError, ProviderPrompt, ProviderResult


class OpenAIProvider(BaseProvider):
    name = "openai"
    label = "OpenAI API"
    implemented = False

    def __init__(self, *, api_key: str | None = None) -> None:
        self.api_key = api_key

    def list_models(self) -> list[dict[str, Any]]:
        return []

    def generate(self, *, prompt: ProviderPrompt | str, model: str | None = None) -> ProviderResult:
        raise ProviderError("OpenAI provider is not implemented yet.")
