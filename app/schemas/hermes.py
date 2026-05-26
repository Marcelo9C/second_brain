from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class PersonaConfig(BaseModel):
    """Configuração de uma persona para geração de cenários de estresse."""

    name: str = Field(..., description="Nome da persona. Ex: 'Chef Irritado'")
    context: str = Field(
        ..., description="Contexto de negócio. Ex: 'Restaurante', 'Clínica'"
    )
    profile: str = Field(
        ...,
        description="Perfil comportamental. Ex: 'Usuário irritado', 'Cliente corporativo'",
    )


class AutomationManifest(BaseModel):
    """
    Manifesto de automação para o Hermes Orquestrador.

    Rígido nas restrições de hardware: max_parallel=1 por padrão
    para preservar CPU/RAM em máquinas com 16GB.
    """

    personas: list[PersonaConfig] = Field(..., min_length=1)
    stress_model: str = Field(
        ...,
        description=(
            "Modelo para gerar cenários de estresse. Prefixo 'gemini/' roteia "
            "via API cloud; sem prefixo usa Ollama local."
        ),
    )
    response_models: list[str] = Field(
        ...,
        min_length=1,
        description=(
            "Modelo assistant para gerar respostas candidatas. "
            "A primeira entrada e usada com duas temperaturas."
        ),
    )
    candidates_per_prompt: int = Field(default=4, ge=1, le=6)
    num_conversations: int = Field(default=1, ge=1, le=100)
    num_turns: int = Field(default=1, ge=1, le=10)
    max_history_turns: int = Field(default=1, ge=0, le=10)
    temperature_low: float = Field(default=0.2, ge=0, le=2)
    temperature_high: float = Field(default=0.8, ge=0, le=2)
    scoring_model: str
    scoring_provider: str = Field(default="ollama")
    max_parallel: int = Field(
        default=1,
        ge=1,
        le=1,
        description="Forçado a 1 para preservação de CPU/RAM em 16GB.",
    )
    rubric_set_id: str = Field(
        ..., description="ID do caso de rubricas existente para avaliação."
    )
    locale: str = Field(default="pt-BR")
    category: str | None = Field(default=None)


class HermesRunStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELED = "canceled"


class HermesRunCreate(BaseModel):
    """Payload para iniciar uma run de automação."""

    manifest: AutomationManifest


class HermesRunSummary(BaseModel):
    run_id: str
    status: HermesRunStatus
    created_at: str
    completed_at: str | None = None
    persona_count: int = 0
    results_count: int = 0
    error: str | None = None


class HermesRunDetail(HermesRunSummary):
    manifest: AutomationManifest
    results: list[dict[str, Any]] = []
    progress: dict[str, Any] = {}


# --- RLHF Schemas (Cenário 2 — placeholder para próxima fase) ---


class RlhfPersonaProfile(BaseModel):
    role: str = Field(..., description="Ex: 'user' ou 'assistant'")
    model: str = Field(..., description="Modelo Ollama para esta persona.")
    system_prompt: str = Field(..., description="System prompt para esta persona.")


class RlhfRunConfig(BaseModel):
    user_persona: RlhfPersonaProfile
    assistant_persona: RlhfPersonaProfile
    turns_per_conversation: int = Field(default=3, ge=1, le=10)
    conversations_count: int = Field(default=10, ge=1, le=100)
    rubric_set_id: str
    # TECH DEBT / PLACEHOLDER: Este default poderá ser parametrizado dinamicamente no futuro
    # para respeitar a variável global DEFAULT_JUDGE_MODEL ou DEFAULT_SCORING_MODEL do backend.
    scoring_model: str = Field(default="llama3.2:3b")
    scoring_provider: str = Field(default="ollama")
