from __future__ import annotations

from typing import Any

from app.repositories.base import BaseRepository


class LocalizationRubricCaseRepository(BaseRepository):
    json_fields = ("chat_history", "rubrics", "metadata")

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        params = self.with_jsonb_fields(payload, self.json_fields)
        query = f"""
            INSERT INTO {self.schema}.localization_rubric_cases (
                locale,
                category,
                chat_history,
                prompt,
                response_raw,
                golden_response,
                evaluator_notes,
                template_name,
                template_version,
                rubrics,
                status,
                tags,
                metadata
            )
            VALUES (
                %(locale)s,
                %(category)s,
                %(chat_history)s,
                %(prompt)s,
                %(response_raw)s,
                %(golden_response)s,
                %(evaluator_notes)s,
                %(template_name)s,
                %(template_version)s,
                %(rubrics)s,
                %(status)s,
                %(tags)s,
                %(metadata)s
            )
            RETURNING *
        """
        with self.db.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                row = cursor.fetchone()
        return dict(row or {})

    def list_recent(
        self,
        *,
        locale: str | None = None,
        category: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        query = f"""
            SELECT *
            FROM {self.schema}.localization_rubric_cases
            WHERE (%(locale)s::text IS NULL OR locale = %(locale)s::text)
              AND (%(category)s::text IS NULL OR category = %(category)s::text)
              AND (%(status)s::text IS NULL OR status = %(status)s::text)
            ORDER BY updated_at DESC, created_at DESC, id DESC
            LIMIT %(limit)s
        """
        params = {
            "locale": locale,
            "category": category,
            "status": status,
            "limit": limit,
        }
        with self.db.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def get_by_id(self, case_id: str) -> dict[str, Any] | None:
        query = f"""
            SELECT *
            FROM {self.schema}.localization_rubric_cases
            WHERE id = %(id)s
        """
        with self.db.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, {"id": case_id})
                row = cursor.fetchone()
        return dict(row) if row else None

    def update(self, case_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        if not payload:
            return self.get_by_id(case_id)

        params = self.with_jsonb_fields(payload, self.json_fields)
        params["id"] = case_id

        assignments = [f"{field} = %({field})s" for field in payload.keys()]
        assignments.append("updated_at = NOW()")

        query = f"""
            UPDATE {self.schema}.localization_rubric_cases
            SET {", ".join(assignments)}
            WHERE id = %(id)s
            RETURNING *
        """
        with self.db.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                row = cursor.fetchone()
        return dict(row) if row else None
