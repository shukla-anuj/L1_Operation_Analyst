import logging
from typing import List, Optional, Tuple
import psycopg2

from src.config.db_config import DB_CONFIG
from src.utils import (
    DatabaseManager,
    handle_errors,
    log_operation,
    validate_embedding,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)



class IncidentSearchStore(DatabaseManager):
    """Database manager for incident similarity search."""

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
    def search_similar_incidents(
        self,
        query_embedding: List[float],
        top_k: int = 5,
    ) -> List[Tuple]:
        """
        Search for similar incidents using pgvector distance.
        Returns a list of tuples with incident details and distance score.
        """
        sql = """
            SELECT i.incident_id,
                   i.service,
                   i.error_log,
                   i.root_cause,
                   i.resolution,
                   e.embedding <#> %s::vector AS distance
            FROM incidents i
            JOIN incident_embeddings_768 e
              ON i.incident_id = e.incident_id
            ORDER BY distance ASC
            LIMIT %s;
        """

        results = self.execute_query(sql, (query_embedding, top_k), fetch_one=False)
        logger.info("Retrieved %s similar incidents", len(results) if results else 0)
        return results or []


class IncidentSearchPipeline:
    """Pipeline for embedding query text and searching similar incidents."""

    def __init__(self, embedder, batch_size: int = 32):
        self.store = IncidentSearchStore()
        self.embedder = embedder
        self.batch_size = batch_size

    @log_operation
    @handle_errors
    def search(self, query_text: str, top_k: int = 5) -> List[Tuple]:
        """Embed query text and search for similar incidents."""
        if not query_text or not isinstance(query_text, str):
            raise ValueError("Query text must be a non-empty string")

        query_embedding = self.embedder.embed_text(query_text)
        return self.store.search_similar_incidents(query_embedding, top_k)

    def cleanup(self) -> None:
        """Release database resources."""
        self.store.close_pool()
        logger.info("Search pipeline cleanup completed")


if __name__ == "__main__":
    from src.embeddings.incident_embeddings import IncidentEmbedder

    #EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
    # EMBEDDING_DIMENSION = 384
    pipeline = IncidentSearchPipeline(embedder=IncidentEmbedder())

    try:
        query = "Policy process job terminated: \n    at java.io.ByteArrayOutputStream.hugeCapacity(Unknown Source)"
        logger.info("Searching for incidents similar to: '%s'", query)
        matches = pipeline.search(query, top_k=5)

        for match in matches:
            incident_id, service, error_log, root_cause, resolution, distance = match
            logger.info(
                "Incident %s | Service: %s | Distance: %.4f\nRoot Cause: %s\nError Log: %s",
                incident_id,
                service,
                distance,
                root_cause,
                error_log,
            )

    except Exception as error:
        logger.error("Search pipeline failed: %s", error)
        raise
    finally:
        pipeline.cleanup()
