from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.schemas.experiments import FrozenGenerationConfig


class ChatGenerateRequest(BaseModel):
    messages: list[dict[str, str]]
    generation: FrozenGenerationConfig
    keep_alive: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
