from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


REQUIRED_CASE_FIELDS = ("locale", "category", "prompt", "response_raw", "golden_response")


class WorkflowIntent(str, Enum):
    NEW_DRAFT = "new_draft"
    LOAD_TEMPLATE = "load_template"
    SAVE_DRAFT = "save_draft"
    VALIDATE = "validate"
    GENERATE_WITH_AI = "generate_with_ai"
    MARK_REVIEWED = "mark_reviewed"
    APPROVE = "approve"
    EXPORT = "export"


class CaseState(str, Enum):
    EMPTY_DRAFT = "empty_draft"
    CASE_DATA_INCOMPLETE = "case_data_incomplete"
    CASE_DATA_READY = "case_data_ready"


class TemplateState(str, Enum):
    NONE = "none"
    TEMPLATE_SCAFFOLD_LOADED = "template_scaffold_loaded"
    RUBRICS_PRESENT_FROM_TEMPLATE = "rubrics_present_from_template"


class RubricSource(str, Enum):
    NONE = "none"
    TEMPLATE = "template"
    AI = "ai"
    EDITOR_DRAFT = "editor_draft"
    IMPORTED = "imported"
    UNKNOWN = "unknown"


class GenerationState(str, Enum):
    NONE = "none"
    GENERATION_FAILED = "generation_failed"
    GENERATION_SUCCEEDED = "generation_succeeded"
    STALE_GENERATION = "stale_generation"


class ValidationState(str, Enum):
    NONE = "none"
    STRUCTURE_PASS = "structure_pass"
    FORMAT_PASS = "format_pass"
    QUALITY_PENDING = "quality_pending"
    HUMAN_REVIEWED = "human_reviewed"
    APPROVAL_READY = "approval_ready"


class WorkflowDecisionStatus(str, Enum):
    EXECUTE = "execute"
    NOT_READY = "not_ready"
    BLOCKED = "blocked"
    EXECUTE_GENERATION = "execute_generation"
    GENERATION_FAILED = "generation_failed"
    GENERATION_SUCCEEDED = "generation_succeeded"


@dataclass(frozen=True)
class CaseStateSnapshot:
    locale: str | None = None
    category: str | None = None
    prompt: str | None = None
    response_raw: str | None = None
    golden_response: str | None = None
    chat_history: Any = None
    rubrics: list[dict[str, Any]] | None = None
    base_template: list[dict[str, Any]] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    validation_report: dict[str, Any] | None = None
    selected_provider: str | None = None
    selected_model: str | None = None

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "CaseStateSnapshot":
        metadata = payload.get("metadata") or {}
        return cls(
            locale=payload.get("locale"),
            category=payload.get("category"),
            prompt=payload.get("prompt"),
            response_raw=payload.get("response_raw"),
            golden_response=payload.get("golden_response"),
            chat_history=payload.get("chat_history"),
            rubrics=payload.get("rubrics"),
            base_template=payload.get("base_template"),
            metadata=metadata,
            validation_report=payload.get("validation_report") or metadata.get("validation_report"),
            selected_provider=payload.get("provider"),
            selected_model=payload.get("model"),
        )


@dataclass(frozen=True)
class SemanticCaseState:
    case_state: str
    template_state: str
    rubric_source: str
    generation_state: str
    validation_state: str
    missing_fields: list[str]
    has_real_case_data: bool
    has_rubrics: bool
    has_template_scaffold: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WorkflowDecision:
    decision: str
    can_execute: bool
    model_call: bool
    reason: str
    message: str
    missing_fields: list[str] = field(default_factory=list)
    side_effects: dict[str, Any] = field(default_factory=dict)
    audit_context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CaseStateEngine:
    def analyze(self, snapshot: CaseStateSnapshot) -> SemanticCaseState:
        missing_fields = [
            field_name
            for field_name in REQUIRED_CASE_FIELDS
            if not self._has_text(getattr(snapshot, field_name))
        ]
        has_real_case_data = not missing_fields
        has_any_case_data = any(
            self._has_text(getattr(snapshot, field_name))
            for field_name in ("prompt", "response_raw", "golden_response")
        )
        rubrics = snapshot.rubrics if isinstance(snapshot.rubrics, list) else []
        has_rubrics = bool(rubrics)
        has_template_scaffold = bool(snapshot.base_template) or bool(
            snapshot.metadata.get("template_scaffold")
        )

        if has_real_case_data:
            case_state = CaseState.CASE_DATA_READY
        elif has_any_case_data or has_rubrics or has_template_scaffold:
            case_state = CaseState.CASE_DATA_INCOMPLETE
        else:
            case_state = CaseState.EMPTY_DRAFT

        rubric_source = self._rubric_source(snapshot, has_rubrics)
        template_state = self._template_state(snapshot, rubric_source, has_template_scaffold)
        generation_state = self._generation_state(snapshot)
        validation_state = self._validation_state(snapshot)

        return SemanticCaseState(
            case_state=case_state.value,
            template_state=template_state.value,
            rubric_source=rubric_source.value,
            generation_state=generation_state.value,
            validation_state=validation_state.value,
            missing_fields=missing_fields,
            has_real_case_data=has_real_case_data,
            has_rubrics=has_rubrics,
            has_template_scaffold=has_template_scaffold,
        )

    def _rubric_source(self, snapshot: CaseStateSnapshot, has_rubrics: bool) -> RubricSource:
        raw_source = str(snapshot.metadata.get("rubric_source") or "").strip()
        if raw_source in {source.value for source in RubricSource}:
            return RubricSource(raw_source)

        if snapshot.metadata.get("rubric_generation"):
            return RubricSource.AI
        if has_rubrics:
            return RubricSource.UNKNOWN
        return RubricSource.NONE

    def _template_state(
        self,
        snapshot: CaseStateSnapshot,
        rubric_source: RubricSource,
        has_template_scaffold: bool,
    ) -> TemplateState:
        if rubric_source == RubricSource.TEMPLATE:
            return TemplateState.RUBRICS_PRESENT_FROM_TEMPLATE
        if has_template_scaffold:
            return TemplateState.TEMPLATE_SCAFFOLD_LOADED
        return TemplateState.NONE

    def _generation_state(self, snapshot: CaseStateSnapshot) -> GenerationState:
        generation = snapshot.metadata.get("rubric_generation") or {}
        status = generation.get("validation_status")
        if status == "failed":
            return GenerationState.GENERATION_FAILED
        if status == "valid":
            return GenerationState.GENERATION_SUCCEEDED
        if generation:
            return GenerationState.STALE_GENERATION
        return GenerationState.NONE

    def _validation_state(self, snapshot: CaseStateSnapshot) -> ValidationState:
        report = snapshot.validation_report or {}
        if report.get("approvalReadiness", {}).get("status") == "pass":
            return ValidationState.APPROVAL_READY
        if snapshot.metadata.get("human_quality_reviewed") is True:
            return ValidationState.HUMAN_REVIEWED
        if report.get("qualityValidation", {}).get("status") == "pending":
            return ValidationState.QUALITY_PENDING
        if report.get("formatValidation", {}).get("status") == "pass":
            return ValidationState.FORMAT_PASS
        if report.get("structureValidation", {}).get("status") == "pass":
            return ValidationState.STRUCTURE_PASS
        return ValidationState.NONE

    def _has_text(self, value: Any) -> bool:
        return isinstance(value, str) and bool(value.strip())


class ActionRouter:
    def resolve(
        self,
        intent: WorkflowIntent | str,
        state: SemanticCaseState,
    ) -> WorkflowDecision:
        workflow_intent = WorkflowIntent(intent)
        if workflow_intent == WorkflowIntent.GENERATE_WITH_AI:
            return self._resolve_generation(state)
        if workflow_intent == WorkflowIntent.MARK_REVIEWED:
            return self._resolve_mark_reviewed(state)
        if workflow_intent == WorkflowIntent.APPROVE:
            return self._resolve_approval(state)
        return self._execute(
            reason=f"{workflow_intent.value}_allowed",
            message="Workflow action can execute.",
            state=state,
        )

    def _resolve_generation(self, state: SemanticCaseState) -> WorkflowDecision:
        if state.case_state == CaseState.CASE_DATA_READY.value:
            return WorkflowDecision(
                decision=WorkflowDecisionStatus.EXECUTE_GENERATION.value,
                can_execute=True,
                model_call=True,
                reason="case_data_ready",
                message="Case data is ready for AI rubric generation.",
                missing_fields=[],
                side_effects={"generation_executed": True},
                audit_context={"semantic_state": state.to_dict()},
            )

        reason = "case_data_incomplete"
        message = "Draft does not contain enough real case data for AI rubric generation."
        if state.case_state == CaseState.EMPTY_DRAFT.value:
            reason = "empty_draft"
            message = "Empty draft does not contain real case data for AI rubric generation."
        elif state.template_state == TemplateState.TEMPLATE_SCAFFOLD_LOADED.value:
            reason = "template_scaffold_without_real_case_data"
            message = "Template scaffold is not a real case and cannot be generated from by itself."

        return WorkflowDecision(
            decision=WorkflowDecisionStatus.NOT_READY.value,
            can_execute=False,
            model_call=False,
            reason=reason,
            message=message,
            missing_fields=state.missing_fields,
            side_effects={"generation_executed": False, "preserve_existing_rubrics": True},
            audit_context={"semantic_state": state.to_dict()},
        )

    def _resolve_mark_reviewed(self, state: SemanticCaseState) -> WorkflowDecision:
        if state.validation_state in {
            ValidationState.FORMAT_PASS.value,
            ValidationState.QUALITY_PENDING.value,
            ValidationState.HUMAN_REVIEWED.value,
            ValidationState.APPROVAL_READY.value,
        }:
            return self._execute(
                reason="human_review_action_allowed",
                message="Human reviewer can explicitly mark the case as reviewed.",
                state=state,
            )
        return WorkflowDecision(
            decision=WorkflowDecisionStatus.NOT_READY.value,
            can_execute=False,
            model_call=False,
            reason="structure_or_format_not_ready",
            message="Structure and format must pass before human review can be marked.",
            missing_fields=state.missing_fields,
            side_effects={},
            audit_context={"semantic_state": state.to_dict()},
        )

    def _resolve_approval(self, state: SemanticCaseState) -> WorkflowDecision:
        if state.validation_state == ValidationState.APPROVAL_READY.value:
            return self._execute(
                reason="approval_ready",
                message="Case is ready for approval.",
                state=state,
            )
        return WorkflowDecision(
            decision=WorkflowDecisionStatus.NOT_READY.value,
            can_execute=False,
            model_call=False,
            reason="approval_readiness_not_pass",
            message="Approval readiness must pass before approval.",
            missing_fields=state.missing_fields,
            side_effects={},
            audit_context={"semantic_state": state.to_dict()},
        )

    def _execute(
        self,
        *,
        reason: str,
        message: str,
        state: SemanticCaseState,
    ) -> WorkflowDecision:
        return WorkflowDecision(
            decision=WorkflowDecisionStatus.EXECUTE.value,
            can_execute=True,
            model_call=False,
            reason=reason,
            message=message,
            missing_fields=state.missing_fields,
            side_effects={},
            audit_context={"semantic_state": state.to_dict()},
        )


class WorkflowDecisionEngine:
    def __init__(
        self,
        *,
        case_state_engine: CaseStateEngine | None = None,
        action_router: ActionRouter | None = None,
    ) -> None:
        self.case_state_engine = case_state_engine or CaseStateEngine()
        self.action_router = action_router or ActionRouter()

    def resolve(
        self,
        intent: WorkflowIntent | str,
        snapshot: CaseStateSnapshot,
    ) -> WorkflowDecision:
        state = self.case_state_engine.analyze(snapshot)
        return self.action_router.resolve(intent, state)
