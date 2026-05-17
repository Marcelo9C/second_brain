from __future__ import annotations

import hashlib
import json
from typing import Any

from app.schemas.hermes_advise import (
    HermesAdvisorTrace,
    HermesAdviseRequest,
    HermesAdviseResponse,
    HermesDiagnosis,
    HermesNextAction,
    HermesPlanStep,
    HermesRecommendation,
    HermesTradeoff,
)


class HermesAdvisor:
    """Deterministic contract advisor for Hermes v1.

    This service intentionally does not call an LLM. Its job is to make the
    operational contract testable before any agentic behavior is introduced.
    """

    def advise(self, request: HermesAdviseRequest) -> HermesAdviseResponse:
        response = HermesAdviseResponse(
            interpreted_objective=request.objective.strip(),
        )
        context = request.context or {}
        rules_evaluated: list[str] = []
        rules_triggered: list[str] = []

        self._evaluate_rule(
            "model_independence",
            lambda: self._check_model_independence(context, response),
            response,
            rules_evaluated,
            rules_triggered,
        )
        self._evaluate_rule(
            "rubric_strength",
            lambda: self._check_rubric_strength(context, response),
            response,
            rules_evaluated,
            rules_triggered,
        )
        self._evaluate_rule(
            "preference_margin",
            lambda: self._check_margin(context, response),
            response,
            rules_evaluated,
            rules_triggered,
        )
        self._evaluate_rule(
            "single_turn_overfit",
            lambda: self._check_single_turn_overfit(request, response),
            response,
            rules_evaluated,
            rules_triggered,
        )
        self._evaluate_rule(
            "judge_conflict",
            lambda: self._check_judge_conflict(context, response),
            response,
            rules_evaluated,
            rules_triggered,
        )
        self._evaluate_rule(
            "missing_margin_threshold",
            lambda: self._check_missing_margin_threshold(context, response),
            response,
            rules_evaluated,
            rules_triggered,
        )
        self._evaluate_rule(
            "model_provenance",
            lambda: self._check_model_provenance(context, response),
            response,
            rules_evaluated,
            rules_triggered,
        )
        self._evaluate_rule(
            "local_model_diversity",
            lambda: self._check_local_model_diversity(request, response),
            response,
            rules_evaluated,
            rules_triggered,
        )
        self._build_plan(response)
        self._build_next_actions(response)
        response.advisor_trace = HermesAdvisorTrace(
            request_id=_stable_hash(request.model_dump(mode="json")),
            rules_evaluated=rules_evaluated,
            rules_triggered=rules_triggered,
            response_hash="",
        )
        response.advisor_trace.response_hash = _response_hash(response)
        return response

    def _evaluate_rule(
        self,
        name: str,
        rule,
        response: HermesAdviseResponse,
        rules_evaluated: list[str],
        rules_triggered: list[str],
    ) -> None:
        before = len(response.recommendations)
        rules_evaluated.append(name)
        rule()
        if len(response.recommendations) > before:
            rules_triggered.append(name)

    def _check_model_independence(
        self,
        context: dict[str, Any],
        response: HermesAdviseResponse,
    ) -> None:
        models = _dict(context.get("current_models"))
        generation = models.get("generation") or models.get("assistant")
        judge = models.get("judge") or models.get("scoring")
        if not generation or not judge:
            return
        same_exact = str(generation) == str(judge)
        same_family = _model_family(str(generation)) == _model_family(str(judge))
        if not same_exact and not same_family:
            return

        response.diagnosis.append(
            HermesDiagnosis(
                issue="generation_and_judge_model_coupling",
                severity="high",
                evidence=f"generation={generation}, judge={judge}",
                impact="Shared model families can reduce judgment independence.",
            )
        )
        response.recommendations.append(
            HermesRecommendation(
                action="diversify_model_families",
                reason="shared_family_may_reduce_judgment_independence",
                alternatives_considered=[
                    "keep_current_models",
                    "use_separate_local_judge",
                    "use_cloud_judge_with_confirmation",
                ],
                confidence=0.92,
            )
        )
        response.tradeoffs.append(
            HermesTradeoff(
                option="use_separate_judge_model",
                benefit="Improves independence of preference signals.",
                cost="May increase latency or require another model.",
                risk="Different judge may be stricter or less aligned with target style.",
            )
        )

    def _check_rubric_strength(
        self,
        context: dict[str, Any],
        response: HermesAdviseResponse,
    ) -> None:
        criteria_count = _criteria_count(context)
        if criteria_count is None or criteria_count >= 3:
            return
        response.diagnosis.append(
            HermesDiagnosis(
                issue="weak_rubric",
                severity="medium",
                evidence=f"criteria_count={criteria_count}",
                impact="Low rubric complexity can reduce reward signal quality.",
            )
        )
        response.recommendations.append(
            HermesRecommendation(
                action="increase_rubric_complexity",
                reason="low_criteria_may_reduce_signal_quality",
                alternatives_considered=[
                    "keep_current_rubric",
                    "add_response_specific_criteria",
                    "split_broad_criterion_into_multiple_dimensions",
                ],
                confidence=0.88,
            )
        )

    def _check_margin(
        self,
        context: dict[str, Any],
        response: HermesAdviseResponse,
    ) -> None:
        result = _dict(context.get("result") or context.get("scoring"))
        thresholds = _dict(context.get("current_thresholds"))
        margin = _number(result.get("margin"))
        threshold = _number(thresholds.get("margin"))
        if margin is None or threshold is None or margin >= threshold:
            return
        response.diagnosis.append(
            HermesDiagnosis(
                issue="low_preference_margin",
                severity="high",
                evidence=f"margin={margin}, threshold={threshold}",
                impact="Candidate separation is too weak for a reliable DPO pair.",
            )
        )
        response.recommendations.append(
            HermesRecommendation(
                action="rerun_with_harder_prompt",
                reason="insufficient_separation_between_candidates",
                alternatives_considered=[
                    "discard_pair",
                    "increase_prompt_difficulty",
                    "generate_more_candidates",
                ],
                confidence=0.9,
            )
        )

    def _check_single_turn_overfit(
        self,
        request: HermesAdviseRequest,
        response: HermesAdviseResponse,
    ) -> None:
        context = request.context or {}
        objective = request.objective.lower()
        turns = _number(context.get("num_turns"))
        conversations = _number(context.get("num_conversations"))
        if "dpo" not in objective and "dataset" not in objective:
            return
        if turns != 1 and conversations != 1:
            return
        response.diagnosis.append(
            HermesDiagnosis(
                issue="single_turn_dataset_overfit",
                severity="medium",
                evidence=f"num_conversations={conversations}, num_turns={turns}",
                impact="A tiny run can validate plumbing but not dataset quality.",
            )
        )
        response.recommendations.append(
            HermesRecommendation(
                action="increase_run_depth_before_export",
                reason="single_turn_runs_are_smoke_tests_not_dataset_evidence",
                alternatives_considered=[
                    "keep_smoke_test_only",
                    "increase_conversations",
                    "increase_turns",
                ],
                confidence=0.84,
            )
        )

    def _check_judge_conflict(
        self,
        context: dict[str, Any],
        response: HermesAdviseResponse,
    ) -> None:
        conflict = bool(context.get("judge_conflict"))
        result = _dict(context.get("result") or context.get("scoring"))
        warnings = result.get("warnings") or []
        if not conflict and not warnings:
            return
        evidence = "judge_conflict=true" if conflict else f"warnings={warnings}"
        response.diagnosis.append(
            HermesDiagnosis(
                issue="judge_conflict",
                severity="high",
                evidence=evidence,
                impact="Preference output needs review before it can become training data.",
            )
        )
        response.recommendations.append(
            HermesRecommendation(
                action="send_pair_to_human_review",
                reason="judge_signal_conflict_requires_human_resolution",
                alternatives_considered=[
                    "discard_pair",
                    "rerun_scoring",
                    "request_human_review",
                ],
                confidence=0.86,
            )
        )

    def _check_missing_margin_threshold(
        self,
        context: dict[str, Any],
        response: HermesAdviseResponse,
    ) -> None:
        result = _dict(context.get("result") or context.get("scoring"))
        thresholds = _dict(context.get("current_thresholds"))
        margin = _number(result.get("margin"))
        threshold = _number(thresholds.get("margin"))
        if margin is None or threshold is not None:
            return
        response.diagnosis.append(
            HermesDiagnosis(
                issue="missing_margin_threshold",
                severity="medium",
                evidence=f"margin={margin}, threshold=None",
                impact="Preference acceptance cannot be audited without an explicit threshold.",
            )
        )
        response.recommendations.append(
            HermesRecommendation(
                action="define_margin_threshold",
                reason="preference_margin_without_threshold_blocks_reliable_acceptance",
                alternatives_considered=[
                    "keep_manual_review_only",
                    "define_default_threshold",
                    "calibrate_threshold_from_prior_runs",
                ],
                confidence=0.89,
            )
        )

    def _check_model_provenance(
        self,
        context: dict[str, Any],
        response: HermesAdviseResponse,
    ) -> None:
        if not bool(context.get("model_provenance_required")):
            return
        models = _dict(context.get("current_models"))
        if not models:
            return
        provenance = _dict(
            context.get("model_provenance") or context.get("current_model_provenance")
        )
        missing = [name for name in models if name not in provenance]
        if not missing:
            return
        response.diagnosis.append(
            HermesDiagnosis(
                issue="missing_model_provenance",
                severity="high",
                evidence=f"missing={', '.join(sorted(missing))}",
                impact="Users cannot tell whether model choices came from them, defaults, fallbacks, or recommendations.",
            )
        )
        response.recommendations.append(
            HermesRecommendation(
                action="record_model_selection_provenance",
                reason="model_choices_need_selected_by_reason_and_confirmation_state",
                alternatives_considered=[
                    "mark_all_as_unknown",
                    "require_user_confirmation",
                    "persist_selected_by_for_each_model",
                ],
                confidence=0.91,
            )
        )

    def _check_local_model_diversity(
        self,
        request: HermesAdviseRequest,
        response: HermesAdviseResponse,
    ) -> None:
        constraints = request.constraints or {}
        if not bool(constraints.get("local_only")):
            return
        available_models = _list(request.context.get("available_models"))
        families = {_model_family(str(model)) for model in available_models if model}
        if len(families) >= 2:
            return
        response.diagnosis.append(
            HermesDiagnosis(
                issue="local_model_diversity_gap",
                severity="medium",
                evidence=f"local_only=true, model_families={sorted(families)}",
                impact="Local-only evaluation has weak independence if only one model family is available.",
            )
        )
        response.recommendations.append(
            HermesRecommendation(
                action="add_distinct_local_model_before_judging",
                reason="local_only_constraint_has_insufficient_model_family_diversity",
                alternatives_considered=[
                    "keep_local_smoke_test_only",
                    "install_distinct_local_judge",
                    "relax_local_only_with_confirmation",
                ],
                confidence=0.82,
            )
        )

    def _build_plan(self, response: HermesAdviseResponse) -> None:
        for recommendation in response.recommendations:
            response.proposed_plan.append(
                HermesPlanStep(
                    step=recommendation.action,
                    purpose=recommendation.reason,
                    expected_output="confirmed_or_rejected_recommendation",
                    provenance={
                        "selected_by": recommendation.selected_by,
                        "reason": recommendation.reason,
                        "confidence": recommendation.confidence,
                        "requires_confirmation": recommendation.requires_confirmation,
                    },
                )
            )

    def _build_next_actions(self, response: HermesAdviseResponse) -> None:
        for recommendation in response.recommendations:
            response.next_actions.append(
                HermesNextAction(
                    label=recommendation.action,
                    action_type="propose_config_patch",
                    requires_confirmation=recommendation.requires_confirmation,
                )
            )


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _model_family(model: str) -> str:
    name = model.split("/", 1)[-1].lower()
    return name.split(":", 1)[0]


def _criteria_count(context: dict[str, Any]) -> int | None:
    rubric = _dict(context.get("rubric"))
    explicit = _number(rubric.get("criteria_count") or context.get("criteria_count"))
    if explicit is not None:
        return int(explicit)
    rubrics = rubric.get("criteria") or rubric.get("rubrics") or context.get("rubrics")
    if isinstance(rubrics, list):
        return len(rubrics)
    return None


def _stable_hash(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _response_hash(response: HermesAdviseResponse) -> str:
    payload = response.model_dump(mode="json")
    trace = payload.get("advisor_trace")
    if isinstance(trace, dict):
        trace["response_hash"] = ""
    return _stable_hash(payload)
