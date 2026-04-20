from __future__ import annotations

from typing import Any
from pathlib import Path

from app.repositories.documents import DocumentChunkRepository
from app.repositories.retrieval_traces import RetrievalTraceRepository
from app.services.llm_orchestrator import LLMOrchestratorService


class RAGPipelineService:
    def __init__(
        self,
        *,
        document_repository: DocumentChunkRepository,
        retrieval_trace_repository: RetrievalTraceRepository,
        llm_service: LLMOrchestratorService,
        models_dir: Path | None = None,
    ) -> None:
        self.document_repository = document_repository
        self.retrieval_trace_repository = retrieval_trace_repository
        self.llm_service = llm_service
        self.models_dir = models_dir

    def ingest_chunks(self, chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return self.document_repository.upsert_chunks(chunks)

    def retrieve(
        self,
        *,
        query_text: str | None = None,
        query_embedding: list[float] | None = None,
        embedding_model: str,
        corpus_version: str,
        limit: int,
        source: str | None = None,
        section: str | None = None,
        title: str | None = None,
        document_date_from: str | None = None,
        document_date_to: str | None = None,
    ) -> list[dict[str, Any]]:
        # Generate embedding if text is provided
        if not query_embedding and query_text:
            query_embedding = self.llm_service.generate_embeddings(
                model=embedding_model,
                prompt=query_text
            )

        if not query_embedding:
            return []

        rows = self.document_repository.retrieve_similar(
            query_embedding=query_embedding,
            embedding_model=embedding_model,
            corpus_version=corpus_version,
            limit=limit,
            source=source,
            section=section,
            title=title,
            document_date_from=document_date_from,
            document_date_to=document_date_to,
        )

        normalized: list[dict[str, Any]] = []
        for index, row in enumerate(rows, start=1):
            distance = row.pop("distance", None)
            similarity_score = None if distance is None else float(1 - distance)
            normalized.append(
                {
                    **row,
                    "trace_rank": index,
                    "similarity_score": similarity_score,
                }
            )
        return normalized

    def persist_retrieval_trace(
        self,
        *,
        experiment_id: str,
        retrieved_chunks: list[dict[str, Any]],
        selected_count: int | None = None,
        stage: str = "retrieve",
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for index, chunk in enumerate(retrieved_chunks, start=1):
            selected_for_prompt = selected_count is not None and index <= selected_count
            rows.append(
                {
                    "experiment_id": experiment_id,
                    "document_chunk_id": chunk.get("id"),
                    "stage": stage,
                    "trace_rank": index,
                    "prompt_rank": index if selected_for_prompt else None,
                    "selected_for_prompt": selected_for_prompt,
                    "source": chunk["source"],
                    "title": chunk["title"],
                    "section": chunk.get("section"),
                    "document_date": chunk.get("document_date"),
                    "corpus_version": chunk["corpus_version"],
                    "similarity_score": chunk.get("similarity_score"),
                    "lexical_score": chunk.get("lexical_score"),
                    "rerank_score": chunk.get("rerank_score"),
                    "chunk_text": chunk["chunk_text"],
                    "chunk_token_count": chunk.get("token_count"),
                    "chunk_metadata": chunk.get("metadata", {}),
                }
            )
        return self.retrieval_trace_repository.bulk_create(rows)

    def list_embedding_models(self) -> list[dict[str, Any]]:
        models = [
            {
                "name": "all-MiniLM-L6-v2",
                "label": "MiniLM L6 (Ollama/Default)",
                "source": "ollama",
            }
        ]
        
        if self.models_dir and self.models_dir.exists():
            for entry in self.models_dir.iterdir():
                if entry.is_dir():
                    # We assume any dir in models/ is a HuggingFace-style model directory
                    models.append({
                        "name": f"local:{entry.name}",
                        "label": f"{entry.name} (Local/CPU)",
                        "source": "local",
                    })
        
        return models
