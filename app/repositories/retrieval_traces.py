from __future__ import annotations

from typing import Any

from app.repositories.base import BaseRepository


class RetrievalTraceRepository(BaseRepository):
    def bulk_create(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not rows:
            return []

        query = f"""
            INSERT INTO {self.schema}.retrieval_traces (
                experiment_id,
                document_chunk_id,
                stage,
                trace_rank,
                prompt_rank,
                selected_for_prompt,
                source,
                title,
                section,
                document_date,
                corpus_version,
                similarity_score,
                lexical_score,
                rerank_score,
                chunk_text,
                chunk_token_count,
                chunk_metadata
            )
            VALUES (
                %(experiment_id)s,
                %(document_chunk_id)s,
                %(stage)s,
                %(trace_rank)s,
                %(prompt_rank)s,
                %(selected_for_prompt)s,
                %(source)s,
                %(title)s,
                %(section)s,
                %(document_date)s,
                %(corpus_version)s,
                %(similarity_score)s,
                %(lexical_score)s,
                %(rerank_score)s,
                %(chunk_text)s,
                %(chunk_token_count)s,
                %(chunk_metadata)s
            )
            RETURNING *
        """

        created: list[dict[str, Any]] = []
        with self.db.connection() as conn:
            with conn.cursor() as cursor:
                for row in rows:
                    cursor.execute(query, self.with_jsonb_fields(row, ("chunk_metadata",)))
                    created.append(dict(cursor.fetchone() or {}))
        return created
