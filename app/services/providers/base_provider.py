from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


class ProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProviderPrompt:
    system_contract: str
    task_payload: str

    def as_text(self) -> str:
        return f"{self.system_contract}\n\n{self.task_payload}"


@dataclass(frozen=True)
class ProviderResult:
    text: str
    provider_used: str
    model_used: str
    exact_url_called: str
    response_status: int | str
    duration_ms: int


class BaseProvider(ABC):
    name: str
    label: str
    implemented: bool = False

    @abstractmethod
    def list_models(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def generate(self, *, prompt: ProviderPrompt | str, model: str | None = None) -> ProviderResult:
        raise NotImplementedError

    def default_model(self) -> str | None:
        models = self.list_models()
        return str(models[0]["name"]) if models else None

    def summary(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "label": self.label,
            "implemented": self.implemented,
        }
