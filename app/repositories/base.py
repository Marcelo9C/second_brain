from typing import Any, Iterable

from psycopg.types.json import Jsonb

from app.db import Database


class BaseRepository:
    def __init__(self, db: Database, schema: str) -> None:
        self.db = db
        self.schema = schema

    def with_jsonb_fields(
        self,
        payload: dict[str, Any],
        json_fields: Iterable[str],
    ) -> dict[str, Any]:
        prepared = dict(payload)
        for field in json_fields:
            if field in prepared:
                prepared[field] = Jsonb(prepared[field])
        return prepared
