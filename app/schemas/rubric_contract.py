from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


DEFAULT_REQUIRED_RUBRIC_FIELDS = {
    "Rubric_dimensions",
    "Rubric_title",
    "Rubrics_description",
    "Rubrics_weight",
    "is_response_specific",
}

LocalizationCategory = Literal["Writing", "Chitchat", "Knowledge"]
NegativeRubricPolicyMode = Literal["none", "recommended", "required", "template_default"]


class RubricWeightPolicy(BaseModel):
    positive_min: int
    positive_max: int
    negative_min: int
    negative_max: int
    zero_allowed: bool = False
    integer_only: bool = True

    @model_validator(mode="after")
    def validate_ranges(self) -> "RubricWeightPolicy":
        if self.positive_min <= 0 or self.positive_max <= 0:
            raise ValueError("positive weight range must be above zero.")
        if self.positive_min > self.positive_max:
            raise ValueError("positive_min must be less than or equal to positive_max.")
        if self.negative_min >= 0 or self.negative_max >= 0:
            raise ValueError("negative weight range must be below zero.")
        if self.negative_min > self.negative_max:
            raise ValueError("negative_min must be less than or equal to negative_max.")
        return self

    def validate_weight(self, weight: Any, *, label: str = "Rubrics_weight") -> None:
        if isinstance(weight, bool) or not isinstance(weight, (int, float)):
            raise ValueError(f"{label} must be numeric.")
        if self.integer_only and not isinstance(weight, int):
            raise ValueError(f"{label} must be an integer.")
        if weight == 0:
            if not self.zero_allowed:
                raise ValueError(f"{label} cannot be zero.")
            return
        if weight > 0 and not self.positive_min <= weight <= self.positive_max:
            raise ValueError(
                f"{label} positive weight must be between {self.positive_min} and {self.positive_max}."
            )
        if weight < 0 and not self.negative_min <= weight <= self.negative_max:
            raise ValueError(
                f"{label} negative weight must be between {self.negative_min} and {self.negative_max}."
            )


class RubricNegativePolicy(BaseModel):
    mode: NegativeRubricPolicyMode = "recommended"


class RubricContract(BaseModel):
    allowed_dimensions: list[str] = Field(min_length=1)
    weight_policy: RubricWeightPolicy
    expected_rubric_count: int = Field(ge=1)
    negative_rubric_policy: RubricNegativePolicy = Field(default_factory=RubricNegativePolicy)
    requires_response_specific_when_context_exists: bool = True
    quality_review_required: bool = True
    required_fields: set[str] = Field(default_factory=lambda: set(DEFAULT_REQUIRED_RUBRIC_FIELDS))

    @model_validator(mode="after")
    def validate_contract(self) -> "RubricContract":
        if len(set(self.allowed_dimensions)) != len(self.allowed_dimensions):
            raise ValueError("allowed_dimensions must not contain duplicates.")
        missing_required = DEFAULT_REQUIRED_RUBRIC_FIELDS - self.required_fields
        if missing_required:
            raise ValueError(
                "required_fields must include: " + ", ".join(sorted(missing_required)) + "."
            )
        return self

    def validate_rubric(self, rubric: Any, *, index: int | None = None) -> None:
        prefix = f"rubric item {index}" if index is not None else "rubric item"
        if not isinstance(rubric, dict):
            raise ValueError(f"{prefix} must be an object.")

        missing = sorted(self.required_fields - set(rubric.keys()))
        if missing:
            raise ValueError(f"{prefix} is missing required fields: {', '.join(missing)}.")

        dimension = rubric.get("Rubric_dimensions")
        if dimension not in self.allowed_dimensions:
            raise ValueError(
                f"{prefix} has invalid Rubric_dimensions: '{dimension}'. "
                f"Must be one of: {', '.join(sorted(self.allowed_dimensions))}."
            )

        self.weight_policy.validate_weight(
            rubric.get("Rubrics_weight"),
            label=f"{prefix} Rubrics_weight",
        )

    def validate_rubrics(self, rubrics: Any, *, enforce_expected_count: bool = False) -> Any:
        if not isinstance(rubrics, list) or not rubrics:
            raise ValueError("rubrics must be a non-empty JSON array.")

        if enforce_expected_count and len(rubrics) != self.expected_rubric_count:
            raise ValueError(
                "rubrics count must match expected_rubric_count "
                f"({self.expected_rubric_count})."
            )

        for index, item in enumerate(rubrics, start=1):
            self.validate_rubric(item, index=index)

        return rubrics


class TemplateContract(BaseModel):
    template_name: str
    template_version: str
    locale: str
    category: LocalizationCategory
    contract: RubricContract
    rubric_slots: list[dict[str, Any]]

    @model_validator(mode="after")
    def validate_template(self) -> "TemplateContract":
        if len(self.rubric_slots) != self.contract.expected_rubric_count:
            raise ValueError(
                "expected_rubric_count must equal the number of rubric_slots."
            )

        self.contract.validate_rubrics(self.rubric_slots)

        return self


def parse_template_contract(payload: Any) -> TemplateContract:
    if not isinstance(payload, dict) or "contract" not in payload:
        raise ValueError("formal rubric template must declare a contract.")
    return TemplateContract.model_validate(payload)
