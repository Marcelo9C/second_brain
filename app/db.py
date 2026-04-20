from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator


class Database:
    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    @contextmanager
    def connection(self) -> Iterator[object]:
        try:
            from pgvector.psycopg import register_vector
            from psycopg import connect
            from psycopg.rows import dict_row
        except ImportError as error:
            raise RuntimeError(
                "Missing database dependencies. Install psycopg and pgvector."
            ) from error

        with connect(self.dsn, row_factory=dict_row) as conn:
            register_vector(conn)
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def ping(self) -> bool:
        with self.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        return True
