from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


DecisionProvenance = Literal["user", "default", "recommendation", "fallback", "retry"]


class HermesAdviseRequest(BaseModel):
    objective: str
    context: dict[str, Any] = Field(default_factory=dict)
    constraints: dict[str, Any] = Field(default_factory=dict)
    user_preferences: dict[str, Any] = Field(default_factory=dict)


class HermesDiagnosis(BaseModel):
    issue: str
    severity: Literal["low", "medium", "high"]
    evidence: str
    impact: str


class HermesRecommendation(BaseModel):
    action: str
    reason: str
    selected_by: DecisionProvenance = "recommendation"
    alternatives_considered: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    requires_confirmation: bool = True


class HermesTradeoff(BaseModel):
    option: str
    benefit: str
    cost: str
    risk: str


class HermesPlanStep(BaseModel):
    step: str
    purpose: str
    expected_output: str
    provenance: dict[str, Any]


class HermesNextAction(BaseModel):
    label: str
    action_type: str
    requires_confirmation: bool = True


class HermesAdvisorTrace(BaseModel):
    request_id: str
    rules_evaluated: list[str] = Field(default_factory=list)
    rules_triggered: list[str] = Field(default_factory=list)
    response_hash: str


class HermesAdviseResponse(BaseModel):
    mode: Literal["advise"] = "advise"
    interpreted_objective: str
    diagnosis: list[HermesDiagnosis] = Field(default_factory=list)
    recommendations: list[HermesRecommendation] = Field(default_factory=list)
    tradeoffs: list[HermesTradeoff] = Field(default_factory=list)
    proposed_plan: list[HermesPlanStep] = Field(default_factory=list)
    next_actions: list[HermesNextAction] = Field(default_factory=list)
    advisor_trace: HermesAdvisorTrace | None = None
