from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class DocumentChunkCreate(BaseModel):
    document_id: str
    chunk_index: int = Field(ge=0)
    title: str
    section: str | None = None
    source: str
    document_date: str | None = None
    corpus_version: str
    embedding_model: str
    token_count: int = Field(default=0, ge=0)
    char_count: int = Field(default=0, ge=0)
    language_code: str | None = None
    content_hash: str
    chunk_text: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    embedding: list[float]


class RetrieveRequest(BaseModel):
    query_text: str | None = None
    query_embedding: list[float] | None = None
    embedding_model: str
    corpus_version: str
    limit: int = Field(default=5, ge=1, le=50)
    source: str | None = None
    section: str | None = None
    title: str | None = None
    document_date_from: str | None = None
    document_date_to: str | None = None
