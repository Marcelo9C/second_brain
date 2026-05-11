from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


LocalizationCategory = Literal["Writing", "Chitchat", "Knowledge"]
RubricCaseStatus = Literal["draft", "reviewed", "approved", "exported"]

REQUIRED_RUBRIC_FIELDS = {
    "Rubric_dimensions",
    "Rubric_title",
    "Rubrics_description",
    "Rubrics_weight",
    "is_response_specific",
}


def validate_rubric_payload(rubrics: Any) -> Any:
    if not isinstance(rubrics, list) or not rubrics:
        raise ValueError("rubrics must be a non-empty JSON array.")

    for index, item in enumerate(rubrics, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"rubric item {index} must be an object.")

        missing = sorted(REQUIRED_RUBRIC_FIELDS - set(item.keys()))
        if missing:
            raise ValueError(
                f"rubric item {index} is missing required fields: {', '.join(missing)}."
            )

    return rubrics


class TemplateSummary(BaseModel):
    locale: str
    category: LocalizationCategory
    template_name: str
    path: str


class LocalizationTemplateResponse(BaseModel):
    locale: str
    category: LocalizationCategory
    template_name: str
    template_version: str = "v1"
    rubrics: list[dict[str, Any]]


class RubricCaseCreate(BaseModel):
    locale: str = "pt-BR"
    category: LocalizationCategory
    chat_history: Any = Field(default_factory=list)
    prompt: str | None = None
    response_raw: str | None = None
    golden_response: str | None = None
    evaluator_notes: str | None = None
    template_name: str
    template_version: str = "v1"
    rubrics: list[dict[str, Any]]
    status: RubricCaseStatus = "draft"
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_rubrics(self) -> "RubricCaseCreate":
        validate_rubric_payload(self.rubrics)
        return self


class RubricCaseUpdate(BaseModel):
    locale: str | None = None
    category: LocalizationCategory | None = None
    chat_history: Any | None = None
    prompt: str | None = None
    response_raw: str | None = None
    golden_response: str | None = None
    evaluator_notes: str | None = None
    template_name: str | None = None
    template_version: str | None = None
    rubrics: list[dict[str, Any]] | None = None
    status: RubricCaseStatus | None = None
    tags: list[str] | None = None
    metadata: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_rubrics(self) -> "RubricCaseUpdate":
        if self.rubrics is not None:
            validate_rubric_payload(self.rubrics)
        return self


class RubricCaseExportRequest(BaseModel):
    locale: str = "pt-BR"
    status: RubricCaseStatus | None = None
    limit: int = Field(default=5000, ge=1, le=50000)
    output_path: str | None = None


class RubricGenerateRequest(BaseModel):
    locale: str = "pt-BR"
    category: LocalizationCategory
    chat_history: Any = Field(default_factory=list)
    prompt: str | None = None
    response_raw: str | None = None
    golden_response: str | None = None
    base_template: list[dict[str, Any]]
    provider: str = "ollama"
    model: str | None = None

    @model_validator(mode="after")
    def validate_base_template(self) -> "RubricGenerateRequest":
        validate_rubric_payload(self.base_template)
        return self
