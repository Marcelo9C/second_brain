from __future__ import annotations

from typing import Any

from app.repositories.base import BaseRepository


class ExperimentRepository(BaseRepository):
    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        params = self.with_jsonb_fields(
            payload,
            ("prompt_messages", "request_payload", "response_payload", "metrics"),
        )
        query = f"""
            INSERT INTO {self.schema}.experiments (
                experiment_kind,
                title,
                study_label,
                status,
                model_name,
                embedding_model,
                seed,
                temperature,
                top_p,
                top_k,
                repeat_penalty,
                max_tokens,
                chunk_size,
                chunk_overlap,
                corpus_version,
                prompt_template_version,
                retrieval_strategy,
                retrieved_top_k,
                prompt_messages,
                request_payload,
                response_payload,
                metrics,
                tags,
                notes
            )
            VALUES (
                %(experiment_kind)s,
                %(title)s,
                %(study_label)s,
                %(status)s,
                %(model_name)s,
                %(embedding_model)s,
                %(seed)s,
                %(temperature)s,
                %(top_p)s,
                %(top_k)s,
                %(repeat_penalty)s,
                %(max_tokens)s,
                %(chunk_size)s,
                %(chunk_overlap)s,
                %(corpus_version)s,
                %(prompt_template_version)s,
                %(retrieval_strategy)s,
                %(retrieved_top_k)s,
                %(prompt_messages)s,
                %(request_payload)s,
                %(response_payload)s,
                %(metrics)s,
                %(tags)s,
                %(notes)s
            )
            RETURNING *
        """
        with self.db.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                row = cursor.fetchone()
        return dict(row or {})

    def list_recent(self, limit: int = 50) -> list[dict[str, Any]]:
        query = f"""
            SELECT *
            FROM {self.schema}.experiments
            ORDER BY created_at DESC, id DESC
            LIMIT %(limit)s
        """
        with self.db.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, {"limit": limit})
                rows = cursor.fetchall()
        return [dict(row) for row in rows]
