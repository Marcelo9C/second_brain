from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class SmfpDependencyStatus(BaseModel):
    status: Literal["ok", "missing"]
    version: str | None = None


class SmfpHealthStatus(BaseModel):
    status: Literal["healthy", "degraded"]
    python_version: str
    dependencies: dict[str, SmfpDependencyStatus]
    key_registry: str
    dataset_registry: str
    model_registry: str
    serialization: str
    path_handling: str = "ok"
    model_artifacts: str = "ok"
    details: dict[str, Any] = Field(default_factory=dict)
