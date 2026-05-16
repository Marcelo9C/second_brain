from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.smfp_actor import SmfpActor


class SmfpBaselineTrainRequest(BaseModel):
    """Request payload for baseline model training."""

    min_samples_per_label: int = Field(
        default=3,
        ge=1,
        description="Minimum labeled samples required per label before training is allowed.",
    )
    algorithm: Literal["random_forest", "logistic_regression"] = Field(
        default="random_forest",
        description="Classifier algorithm to use for the baseline model.",
    )


class SmfpBaselineTrainResult(BaseModel):
    """Result returned after successful baseline training."""

    model_id: str
    algorithm: str
    accuracy: float
    macro_f1: float
    per_label_counts: dict[str, int]
    confusion_matrix: list[list[int]]
    confusion_matrix_labels: list[str]
    feature_schema_version: str
    feature_columns: list[str]
    trained_at: str
    status: Literal["baseline"] = "baseline"
    model_path: str
    metadata_path: str
    training_samples_used: int
    labels_used: int
    split_distribution: dict[str, int]
    limitations: list[str] = Field(default_factory=lambda: [
        "Baseline model — NOT approved for production inference",
        "active_model remains null until explicit promotion",
        "ml_classifier_status remains disabled",
        "ML probability MUST NOT be mixed with heuristic confidence",
        "Model requires independent audit before any promotion",
    ])


class SmfpPromoteRequest(BaseModel):
    """Request payload for model promotion gate."""

    min_macro_f1: float = Field(
        default=0.6,
        ge=0.0,
        le=1.0,
        description="Minimum macro F1 score required for promotion.",
    )
    min_accuracy: float = Field(
        default=0.6,
        ge=0.0,
        le=1.0,
        description="Minimum accuracy required for promotion.",
    )
    min_labels: int = Field(
        default=2,
        ge=2,
        description="Minimum number of distinct labels the model must have been trained on.",
    )


class SmfpPromoteResult(BaseModel):
    """Result returned after successful model promotion."""

    model_id: str
    status: Literal["active"] = "active"
    promoted_at: str
    promoted_by: dict[str, str]  # SmfpActor serialized
    previous_active_model: str | None = None
    previous_active_retired: bool = False
    ml_classifier_status: Literal["active"] = "active"
    accuracy: float
    macro_f1: float
    labels_used: int
    feature_schema_version: str
    feature_columns: list[str]
