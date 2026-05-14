from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.rubric_contract import (
    DEFAULT_REQUIRED_RUBRIC_FIELDS,
    RubricContract,
)


LocalizationCategory = Literal["Writing", "Chitchat", "Knowledge"]
RubricCaseStatus = Literal["draft", "reviewed", "approved", "exported"]
CandidateResponseId = Literal["A", "B", "C", "D"]

REQUIRED_RUBRIC_FIELDS = set(DEFAULT_REQUIRED_RUBRIC_FIELDS)

ACCEPTED_RUBRIC_DIMENSIONS = {
    "Cultural Understanding and Application",
    "Local Facts and Awareness",
    "Logic and Formatting",
    "Natural Language Fluency",
}

MAX_CANDIDATE_RESPONSES = 4
ALLOWED_CANDIDATE_RESPONSE_IDS = {"A", "B", "C", "D"}


class CandidateResponse(BaseModel):
    id: CandidateResponseId
    label: str | None = None
    response_raw: str | None = None
    source: str | None = "manual"
    created_at: str | None = None


def normalize_candidate_response_payload(
    payload: dict[str, Any],
    *,
    require_selection: bool,
) -> dict[str, Any]:
    """Validate candidate responses and resolve the evaluated response when selected."""

    normalized_payload = dict(payload)
    metadata = dict(normalized_payload.get("metadata") or {})

    top_level_candidates_present = "candidate_responses" in normalized_payload
    metadata_candidates_present = "candidate_responses" in metadata
    top_level_candidates = normalized_payload.get("candidate_responses")
    candidates_raw = (
        top_level_candidates
        if top_level_candidates is not None
        else metadata.get("candidate_responses")
    )
    selected_candidate_id = (
        normalized_payload.get("selected_candidate_id")
        or metadata.get("selected_candidate_id")
    )

    if candidates_raw is None:
        normalized_payload["metadata"] = metadata
        return normalized_payload

    candidates = _normalize_candidate_responses(candidates_raw)
    if require_selection and not selected_candidate_id:
        raise ValueError("selected_candidate_id is required when candidate_responses are provided.")

    if selected_candidate_id:
        selected_candidate_id = str(selected_candidate_id).strip()
        if selected_candidate_id not in ALLOWED_CANDIDATE_RESPONSE_IDS:
            raise ValueError(
                "selected_candidate_id must be one of: A, B, C, D."
            )

    selected_candidate = None
    if selected_candidate_id:
        selected_candidate = next(
            (candidate for candidate in candidates if candidate["id"] == selected_candidate_id),
            None,
        )
        if selected_candidate is None:
            raise ValueError("selected_candidate_id does not match any candidate response.")

        evaluated_response_raw = _clean_text(selected_candidate.get("response_raw"))
        if not evaluated_response_raw:
            raise ValueError("selected candidate response_raw cannot be empty.")

        incoming_response_raw = _clean_text(normalized_payload.get("response_raw"))
        response_raw_overridden = bool(
            incoming_response_raw and incoming_response_raw != evaluated_response_raw
        )
        normalized_payload["response_raw"] = evaluated_response_raw
        metadata["selected_candidate_id"] = selected_candidate_id
        metadata["response_raw_resolution"] = {
            "mode": "candidate_selected",
            "candidate_id": selected_candidate_id,
            "input_response_raw_overridden": response_raw_overridden,
        }
    elif require_selection:
        raise ValueError("selected_candidate_id is required when candidate_responses are provided.")

    metadata["candidate_responses"] = candidates
    normalized_payload["metadata"] = metadata
    if top_level_candidates_present or metadata_candidates_present:
        normalized_payload["candidate_responses"] = candidates
    if selected_candidate_id:
        normalized_payload["selected_candidate_id"] = selected_candidate_id

    return normalized_payload


def _normalize_candidate_responses(candidates_raw: Any) -> list[dict[str, Any]]:
    if not isinstance(candidates_raw, list):
        raise ValueError("candidate_responses must be a JSON array.")
    if not candidates_raw:
        raise ValueError("candidate_responses must contain at least one candidate.")
    if len(candidates_raw) > MAX_CANDIDATE_RESPONSES:
        raise ValueError("candidate_responses cannot contain more than 4 candidates.")

    normalized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, raw_candidate in enumerate(candidates_raw, start=1):
        if isinstance(raw_candidate, CandidateResponse):
            candidate = raw_candidate.model_dump(mode="json")
        elif isinstance(raw_candidate, dict):
            candidate = dict(raw_candidate)
        else:
            raise ValueError(f"candidate response {index} must be an object.")

        candidate_id = str(candidate.get("id") or "").strip()
        if candidate_id not in ALLOWED_CANDIDATE_RESPONSE_IDS:
            raise ValueError("candidate response id must be one of: A, B, C, D.")
        if candidate_id in seen_ids:
            raise ValueError(f"duplicate candidate response id: {candidate_id}.")
        seen_ids.add(candidate_id)

        normalized.append(
            {
                "id": candidate_id,
                "label": _clean_text(candidate.get("label")) or f"Candidate {candidate_id}",
                "response_raw": _clean_text(candidate.get("response_raw")),
                "source": _clean_text(candidate.get("source")) or "manual",
                "created_at": _clean_text(candidate.get("created_at")),
            }
        )

    return normalized


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def validate_rubric_payload(rubrics: Any, contract: RubricContract | None = None) -> Any:
    if contract is not None:
        return contract.validate_rubrics(rubrics)

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

        dimension = item.get("Rubric_dimensions")
        if dimension not in ACCEPTED_RUBRIC_DIMENSIONS:
            raise ValueError(
                f"rubric item {index} has invalid Rubric_dimensions: '{dimension}'. "
                f"Must be one of: {', '.join(sorted(ACCEPTED_RUBRIC_DIMENSIONS))}."
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
    artifact_type: str = "template_scaffold"
    rubrics_are_final: bool = False
    message: str | None = None
    contract: dict[str, Any] | None = None
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
    rubrics: list[dict[str, Any]] = Field(default_factory=list)
    status: RubricCaseStatus = "draft"
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    candidate_responses: list[CandidateResponse] | None = None
    selected_candidate_id: CandidateResponseId | None = None

    @model_validator(mode="after")
    def validate_rubrics(self) -> "RubricCaseCreate":
        if self.status != "draft":
            contract_payload = self.metadata.get("template_contract")
            contract = RubricContract.model_validate(contract_payload) if contract_payload else None
            validate_rubric_payload(self.rubrics, contract=contract)
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
    candidate_responses: list[CandidateResponse] | None = None
    selected_candidate_id: CandidateResponseId | None = None


class RubricValidationRequest(BaseModel):
    locale: str = "pt-BR"
    category: LocalizationCategory
    prompt: str | None = None
    response_raw: str | None = None
    golden_response: str | None = None
    rubrics: Any = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    contract: dict[str, Any] | None = None


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
    contract: dict[str, Any] | None = None
    provider: str = "ollama"
    model: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    candidate_responses: list[CandidateResponse] | None = None
    selected_candidate_id: CandidateResponseId | None = None

    @model_validator(mode="after")
    def validate_base_template(self) -> "RubricGenerateRequest":
        if not isinstance(self.base_template, list) or not self.base_template:
            raise ValueError("base_template must be a non-empty JSON array.")
        resolved = normalize_candidate_response_payload(
            self.model_dump(mode="json"),
            require_selection=True,
        )
        self.response_raw = resolved.get("response_raw")
        self.metadata = resolved.get("metadata") or {}
        return self
