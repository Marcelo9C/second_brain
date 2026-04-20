from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class FrozenGenerationConfig(BaseModel):
    model_name: str
    embedding_model: str | None = None
    seed: int
    temperature: float
    top_p: float
    top_k: int
    repeat_penalty: float | None = None
    max_tokens: int | None = None
    chunk_size: int
    chunk_overlap: int = 0
    corpus_version: str
    prompt_template_version: str = "v1"
    retrieval_strategy: str = "none"
    retrieved_top_k: int = 0


class RetrievalTraceCreate(BaseModel):
    document_chunk_id: str | None = None
    stage: Literal["retrieve", "rerank", "prompt_context"] = "retrieve"
    trace_rank: int = Field(ge=1)
    prompt_rank: int | None = Field(default=None, ge=1)
    selected_for_prompt: bool = False
    source: str
    title: str
    section: str | None = None
    document_date: str | None = None
    corpus_version: str
    similarity_score: float | None = None
    lexical_score: float | None = None
    rerank_score: float | None = None
    chunk_text: str
    chunk_token_count: int | None = Field(default=None, ge=0)
    chunk_metadata: dict[str, Any] = Field(default_factory=dict)


class ExperimentCreate(BaseModel):
    experiment_kind: Literal["chat", "rag", "embedding", "evaluation"]
    title: str | None = None
    study_label: str | None = None
    status: Literal["pending", "running", "completed", "failed"] = "completed"
    generation: FrozenGenerationConfig
    prompt_messages: list[dict[str, str]] = Field(default_factory=list)
    request_payload: dict[str, Any] = Field(default_factory=dict)
    response_payload: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    notes: str | None = None
    retrieval_traces: list[RetrievalTraceCreate] = Field(default_factory=list)
