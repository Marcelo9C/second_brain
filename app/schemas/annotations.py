from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class CandidateScorePair(BaseModel):
    a: int | None = Field(default=None, ge=1, le=5)
    b: int | None = Field(default=None, ge=1, le=5)


class AnnotationSxSCreate(BaseModel):
    experiment_id: str | None = None
    study_label: str | None = None
    annotator: str = "human"
    prompt_original: str | None = None
    system_prompt: str | None = None
    prompt_original_a: str | None = None
    prompt_original_b: str | None = None
    system_prompt_a: str | None = None
    system_prompt_b: str | None = None
    output_a: str
    output_b: str
    candidate_a_label: str = "A"
    candidate_b_label: str = "B"
    candidate_a_params: dict[str, Any] = Field(default_factory=dict)
    candidate_b_params: dict[str, Any] = Field(default_factory=dict)
    factuality: CandidateScorePair = Field(default_factory=CandidateScorePair)
    helpfulness: CandidateScorePair = Field(default_factory=CandidateScorePair)
    grounding: CandidateScorePair = Field(default_factory=CandidateScorePair)
    chosen: Literal["A", "B"]
    rejected: Literal["A", "B"]
    rationale: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_labels(self) -> "AnnotationSxSCreate":
        if self.chosen == self.rejected:
            raise ValueError("chosen and rejected must be different.")
        return self


class AnnotationExportRequest(BaseModel):
    limit: int = Field(default=1000, ge=1, le=50000)
    output_path: str | None = None
