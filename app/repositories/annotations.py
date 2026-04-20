from __future__ import annotations

from typing import Any

from app.repositories.base import BaseRepository


class AnnotationSxSRepository(BaseRepository):
    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        params = self.with_jsonb_fields(
            payload,
            ("candidate_a_params", "candidate_b_params", "metadata"),
        )
        query = f"""
            INSERT INTO {self.schema}.annotations_sxs (
                experiment_id,
                study_label,
                annotator,
                prompt_original,
                system_prompt,
                prompt_original_a,
                prompt_original_b,
                system_prompt_a,
                system_prompt_b,
                output_a,
                output_b,
                candidate_a_label,
                candidate_b_label,
                candidate_a_params,
                candidate_b_params,
                factuality_a,
                factuality_b,
                helpfulness_a,
                helpfulness_b,
                grounding_a,
                grounding_b,
                chosen,
                rejected,
                rationale,
                metadata,
                tags
            )
            VALUES (
                %(experiment_id)s,
                %(study_label)s,
                %(annotator)s,
                %(prompt_original)s,
                %(system_prompt)s,
                %(prompt_original_a)s,
                %(prompt_original_b)s,
                %(system_prompt_a)s,
                %(system_prompt_b)s,
                %(output_a)s,
                %(output_b)s,
                %(candidate_a_label)s,
                %(candidate_b_label)s,
                %(candidate_a_params)s,
                %(candidate_b_params)s,
                %(factuality_a)s,
                %(factuality_b)s,
                %(helpfulness_a)s,
                %(helpfulness_b)s,
                %(grounding_a)s,
                %(grounding_b)s,
                %(chosen)s,
                %(rejected)s,
                %(rationale)s,
                %(metadata)s,
                %(tags)s
            )
            RETURNING *
        """
        with self.db.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                row = cursor.fetchone()
        return dict(row or {})

    def list_for_sft_export(self, limit: int = 1000) -> list[dict[str, Any]]:
        query = f"""
            SELECT *
            FROM {self.schema}.annotations_sxs
            ORDER BY created_at ASC, id ASC
            LIMIT %(limit)s
        """
        with self.db.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, {"limit": limit})
                rows = cursor.fetchall()
        return [dict(row) for row in rows]
