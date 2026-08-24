import logging
from pathlib import Path
from typing import List, Optional, Tuple
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_text_splitters import CharacterTextSplitter

from src.config.db_config import DB_CONFIG
from src.utils import (
    DatabaseManager,
    handle_errors,
    log_operation,
    validate_embedding,
)


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIMENSION = 384


class EmbeddingStore(DatabaseManager):
    """Manage incident embeddings in PostgreSQL."""

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
    def fetch_incidents(
        self,
        limit: Optional[int] = None,
    ) -> List[Tuple[int, str]]:
        """Fetch incidents from the database."""
        query = "SELECT incident_id, error_log FROM incidents"

        if limit is not None:
            query += " LIMIT %s"
            rows = self.execute_query(query, (limit,), fetch_one=False)
        else:
            rows = self.execute_query(query, fetch_one=False)

        logger.info("Fetched %s incidents", len(rows) if rows else 0)
        return rows or []

    @validate_embedding(EMBEDDING_DIMENSION)
    @handle_errors
    def insert_embedding(
        self,
        incident_id: int,
        embedding: List[float],
    ) -> None:
        """Insert or update one incident embedding."""
        sql = """
            INSERT INTO incident_embeddings (incident_id, embedding)
            VALUES (%s, %s)
            ON CONFLICT (incident_id) DO UPDATE
            SET embedding = EXCLUDED.embedding;
        """

        self.execute_query(sql, (incident_id, embedding))
        logger.info("Inserted embedding for incident %s", incident_id)

    @handle_errors
    def batch_insert_embeddings(
        self,
        embeddings_data: List[Tuple[int, List[float]]],
    ) -> None:
        """Insert or update multiple incident embeddings."""
        if not embeddings_data:
            logger.warning("No embeddings to insert")
            return

        sql = """
            INSERT INTO incident_embeddings (incident_id, embedding)
            VALUES (%s, %s)
            ON CONFLICT (incident_id) DO UPDATE
            SET embedding = EXCLUDED.embedding;
        """

        self.execute_many(sql, embeddings_data)

    @handle_errors
    def get_embedded_count(self) -> int:
        """Return the number of stored incident embeddings."""
        result = self.execute_query(
            "SELECT COUNT(*) FROM incident_embeddings;",
            fetch_one=True,
        )
        return result[0] if result else 0


class IncidentEmbedder:
    """Generate embeddings using Sentence Transformers."""

    def __init__(
        self,
        model_name: str = EMBEDDING_MODEL,
        batch_size: int = 32,
    ):
        logger.info("Loading embedding model: %s", model_name)

        self.embeddings = HuggingFaceEmbeddings(
            model_name=model_name,
        )
        self.batch_size = batch_size

        logger.info("Embedding model loaded")

    @handle_errors
    def embed_text(self, text: str) -> List[float]:
        """Generate an embedding for one text value."""
        if not text or not isinstance(text, str):
            raise ValueError("Text must be a non-empty string")

        return self.embeddings.embed_query(text)

    @handle_errors
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple text values."""
        if not texts:
            return []

        return self.embeddings.embed_documents(texts)


class IncidentEmbeddingPipeline:
    """Generate and store incident and document embeddings."""

    def __init__(self, batch_size: int = 32):
        self.store = EmbeddingStore()
        self.embedder = IncidentEmbedder(batch_size=batch_size)
        self.batch_size = batch_size

    @log_operation
    @handle_errors
    def process_incidents(self, limit: Optional[int] = None) -> None:
        """Generate and store embeddings for incidents."""
        incidents = self.store.fetch_incidents(limit=limit)

        if not incidents:
            logger.warning("No incidents to process")
            return

        for start in range(0, len(incidents), self.batch_size):
            batch = incidents[start : start + self.batch_size]

            incident_ids = [incident[0] for incident in batch]
            error_logs = [incident[1] for incident in batch]

            embeddings = self.embedder.embed_batch(error_logs)
            embeddings_data = list(zip(incident_ids, embeddings))

            self.store.batch_insert_embeddings(embeddings_data)

            batch_number = start // self.batch_size + 1
            total_batches = (
                len(incidents) + self.batch_size - 1
            ) // self.batch_size

            logger.info(
                "Processed incident batch %s/%s",
                batch_number,
                total_batches,
            )

        embedded_count = self.store.get_embedded_count()
        logger.info("Total embedded incidents: %s", embedded_count)


    def cleanup(self) -> None:
        """Release database resources."""
        self.store.close_pool()
        logger.info("Pipeline cleanup completed")


if __name__ == "__main__":
    pipeline = IncidentEmbeddingPipeline(batch_size=32)

    try:
        # Process incident records from PostgreSQL.
        pipeline.process_incidents()

    except Exception as error:
        logger.error("Pipeline failed: %s", error)
        raise
    finally:
        pipeline.cleanup()