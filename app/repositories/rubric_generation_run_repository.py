from __future__ import annotations

from typing import Any

from app.repositories.base import BaseRepository


class RubricGenerationRunRepository(BaseRepository):
    run_json_fields = (
        "model_config",
        "input_snapshot",
        "parsed_rubrics",
        "validation_report",
        "heuristic_report",
    )
    artifact_json_fields = (
        "rubrics_snapshot",
        "validation_report",
        "heuristic_report",
    )

    def next_run_number(self, case_id: str) -> int:
        query = f"""
            SELECT COALESCE(MAX(run_number), 0) + 1 AS next_run_number
            FROM {self.schema}.rubric_generation_runs
            WHERE case_id = %(case_id)s
        """
        with self.db.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, {"case_id": case_id})
                row = cursor.fetchone()
        return int((row or {}).get("next_run_number") or 1)

    def create_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        params = self.with_jsonb_fields(payload, self.run_json_fields)
        fields = list(params.keys())
        query = f"""
            INSERT INTO {self.schema}.rubric_generation_runs (
                {", ".join(fields)}
            )
            VALUES (
                {", ".join(f"%({field})s" for field in fields)}
            )
            RETURNING *
        """
        with self.db.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                row = cursor.fetchone()
        return dict(row or {})

    def update_run(self, run_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        if not payload:
            return self.get_run(run_id)

        params = self.with_jsonb_fields(payload, self.run_json_fields)
        params["id"] = run_id
        assignments = [f"{field} = %({field})s" for field in payload.keys()]
        query = f"""
            UPDATE {self.schema}.rubric_generation_runs
            SET {", ".join(assignments)}
            WHERE id = %(id)s
            RETURNING *
        """
        with self.db.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                row = cursor.fetchone()
        return dict(row) if row else None

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        query = f"""
            SELECT *
            FROM {self.schema}.rubric_generation_runs
            WHERE id = %(id)s
        """
        with self.db.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, {"id": run_id})
                row = cursor.fetchone()
        return dict(row) if row else None

    def list_runs_for_case(self, case_id: str) -> list[dict[str, Any]]:
        query = f"""
            SELECT *
            FROM {self.schema}.rubric_generation_runs
            WHERE case_id = %(case_id)s
            ORDER BY run_number DESC
        """
        with self.db.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, {"case_id": case_id})
                rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def create_applied_artifact(self, payload: dict[str, Any]) -> dict[str, Any]:
        params = self.with_jsonb_fields(payload, self.artifact_json_fields)
        fields = list(params.keys())
        query = f"""
            INSERT INTO {self.schema}.rubric_generation_applied_artifacts (
                {", ".join(fields)}
            )
            VALUES (
                {", ".join(f"%({field})s" for field in fields)}
            )
            RETURNING *
        """
        with self.db.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                row = cursor.fetchone()
        return dict(row or {})
