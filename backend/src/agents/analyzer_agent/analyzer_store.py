"""Database operations used by the analyzer agent."""

import json
import logging
from typing import Any, Dict, List, Optional

from psycopg2.extras import Json

from src.config.db_config import DB_CONFIG
from src.utils import DatabaseManager, handle_errors

logger = logging.getLogger(__name__)


class AnalyzerStore(DatabaseManager):
    """Search architecture chunks and persist analyzer results."""

    def __init__(
        self,
        db_config: Optional[dict] = None,
        min_connections: int = 2,
        max_connections: int = 10,
    ):
        super().__init__(
            db_config or DB_CONFIG,
            min_connections,
            max_connections,
        )

    @handle_errors
    def search_doc_chunks_vector(
        self,
        query_embedding: List[float],
        top_k: int = 8,
    ) -> List[Dict[str, Any]]:
        """Return architecture chunks ordered by vector distance."""
        if not query_embedding:
            return []
        if top_k < 1:
            raise ValueError("top_k must be greater than zero")

        sql = """
            SELECT chunk_id, doc_id, content, metadata,
                   embedding <#> %s::vector AS score
            FROM architecture_doc_chunks
            ORDER BY score ASC
            LIMIT %s;
        """
        rows = self.execute_query(sql, (query_embedding, top_k), fetch_one=False)
        return [
            {
                "chunk_id": row[0],
                "doc_id": row[1],
                "content": row[2],
                "metadata": row[3] or {},
                "score": row[4],
            }
            for row in rows or []
        ]

    @handle_errors
    def search_doc_chunks_text(
        self,
        query: str,
        top_k: int = 8,
    ) -> List[Dict[str, Any]]:
        """Return architecture chunks matching the query text."""
        if not query or not query.strip():
            return []
        if top_k < 1:
            raise ValueError("top_k must be greater than zero")

        sql = """
            SELECT chunk_id, doc_id, content, metadata, 0.0 AS score
            FROM architecture_doc_chunks
            WHERE content ILIKE %s
            ORDER BY chunk_id
            LIMIT %s;
        """
        rows = self.execute_query(
            sql,
            (f"%{query.strip()}%", top_k),
            fetch_one=False,
        )
        return [
            {
                "chunk_id": row[0],
                "doc_id": row[1],
                "content": row[2],
                "metadata": row[3] or {},
                "score": row[4],
            }
            for row in rows or []
        ]

    @handle_errors
    def insert_rca(
        self,
        incident_query: str,
        rca: Dict[str, Any],
        incident_ids: List[int],
        evidence: Dict[str, Any],
    ) -> None:
        """Persist an RCA together with the evidence used to produce it."""
        sql = """
            INSERT INTO analyzer_rcas
                (incident_query, incident_ids, evidence, rca_json)
            VALUES (%s, %s, %s::jsonb, %s::jsonb);
        """
        self.execute_query(
            sql,
            (
                incident_query,
                incident_ids,
                Json(evidence, dumps=lambda value: json.dumps(value, default=str)),
                Json(rca, dumps=lambda value: json.dumps(value, default=str)),
            ),
        )
        logger.info("Persisted analyzer RCA")
