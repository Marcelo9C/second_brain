from __future__ import annotations

from typing import Any

from app.repositories.base import BaseRepository


class DocumentChunkRepository(BaseRepository):
    def upsert_chunks(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not rows:
            return []

        query = f"""
            INSERT INTO {self.schema}.documents_chunks (
                document_id,
                chunk_index,
                title,
                section,
                source,
                document_date,
                corpus_version,
                embedding_model,
                token_count,
                char_count,
                language_code,
                content_hash,
                chunk_text,
                metadata,
                embedding
            )
            VALUES (
                %(document_id)s,
                %(chunk_index)s,
                %(title)s,
                %(section)s,
                %(source)s,
                %(document_date)s,
                %(corpus_version)s,
                %(embedding_model)s,
                %(token_count)s,
                %(char_count)s,
                %(language_code)s,
                %(content_hash)s,
                %(chunk_text)s,
                %(metadata)s,
                %(embedding)s
            )
            ON CONFLICT (document_id, corpus_version, chunk_index, embedding_model)
            DO UPDATE SET
                title = EXCLUDED.title,
                section = EXCLUDED.section,
                source = EXCLUDED.source,
                document_date = EXCLUDED.document_date,
                token_count = EXCLUDED.token_count,
                char_count = EXCLUDED.char_count,
                language_code = EXCLUDED.language_code,
                content_hash = EXCLUDED.content_hash,
                chunk_text = EXCLUDED.chunk_text,
                metadata = EXCLUDED.metadata,
                embedding = EXCLUDED.embedding,
                updated_at = NOW()
            RETURNING *
        """

        created: list[dict[str, Any]] = []
        with self.db.connection() as conn:
            with conn.cursor() as cursor:
                for row in rows:
                    cursor.execute(query, self.with_jsonb_fields(row, ("metadata",)))
                    created.append(dict(cursor.fetchone() or {}))
        return created

    def retrieve_similar(
        self,
        *,
        query_embedding: list[float],
        embedding_model: str,
        corpus_version: str,
        limit: int = 5,
        source: str | None = None,
        section: str | None = None,
        title: str | None = None,
        document_date_from: str | None = None,
        document_date_to: str | None = None,
    ) -> list[dict[str, Any]]:
        query = f"""
            SELECT
                id,
                document_id,
                chunk_index,
                title,
                section,
                source,
                document_date,
                corpus_version,
                embedding_model,
                token_count,
                char_count,
                language_code,
                content_hash,
                chunk_text,
                metadata,
                embedding <=> %(query_embedding)s AS distance
            FROM {self.schema}.documents_chunks
            WHERE embedding_model = %(embedding_model)s
              AND corpus_version = %(corpus_version)s
              AND (%(source)s IS NULL OR source = %(source)s)
              AND (%(section)s IS NULL OR section = %(section)s)
              AND (%(title)s IS NULL OR title = %(title)s)
              AND (%(document_date_from)s IS NULL OR document_date >= %(document_date_from)s::date)
              AND (%(document_date_to)s IS NULL OR document_date <= %(document_date_to)s::date)
            ORDER BY
                distance ASC,
                source ASC,
                title ASC,
                section ASC NULLS FIRST,
                chunk_index ASC,
                id ASC
            LIMIT %(limit)s
        """
        params = {
            "query_embedding": query_embedding,
            "embedding_model": embedding_model,
            "corpus_version": corpus_version,
            "limit": limit,
            "source": source,
            "section": section,
            "title": title,
            "document_date_from": document_date_from,
            "document_date_to": document_date_to,
        }
        with self.db.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                rows = cursor.fetchall()
        return [dict(row) for row in rows]
