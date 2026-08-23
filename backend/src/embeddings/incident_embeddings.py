from langchain.embeddings import HuggingFaceEmbeddings
import logging
from typing import List, Tuple, Optional
from src.config.db_config import DB_CONFIG
from src.utils import handle_errors, log_operation, validate_embedding, DatabaseManager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize embedding model (industry standard: sentence-transformers)
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIMENSION = 384  # MiniLM-L6-v2 dimension


class EmbeddingStore(DatabaseManager):
    """Manage embeddings with connection pooling (extends DatabaseManager)."""
    
    def __init__(self, db_config: dict = None, min_connections: int = 2, max_connections: int = 10):
        """Initialize embedding store with database config."""
        super().__init__(db_config or DB_CONFIG, min_connections, max_connections)
    
    @handle_errors
    def fetch_incidents(self, limit: Optional[int] = None) -> List[Tuple[int, str]]:
        """Fetch incidents from database."""
        query = "SELECT incident_id, error_log FROM incidents"
        if limit:
            query += f" LIMIT {limit}"
        query += ";"
        
        rows = self.execute_query(query, fetch_one=False)
        logger.info(f"Fetched {len(rows) if rows else 0} incidents")
        return rows or []
    
    @validate_embedding(EMBEDDING_DIMENSION)
    @handle_errors
    def insert_embedding(self, incident_id: int, embedding: List[float]) -> None:
        """Insert single embedding into database."""
        sql = """
            INSERT INTO incident_embeddings (incident_id, embedding) 
            VALUES (%s, %s)
            ON CONFLICT (incident_id) DO UPDATE 
            SET embedding = EXCLUDED.embedding;
        """
        self.execute_query(sql, (incident_id, embedding))
        logger.info(f"Inserted embedding for incident {incident_id}")
    
    @handle_errors
    def batch_insert_embeddings(self, embeddings_data: List[Tuple[int, List[float]]]) -> None:
        """Insert multiple embeddings in batch (more efficient)."""
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
        """Get count of embedded incidents."""
        result = self.execute_query("SELECT COUNT(*) FROM incident_embeddings;", fetch_one=True)
        return result[0] if result else 0


class IncidentEmbedder:
    """Generate embeddings for incidents."""
    
    def __init__(self, model_name: str = EMBEDDING_MODEL, batch_size: int = 32):
        """Initialize embedder with model."""
        logger.info(f"Loading embedding model: {model_name}")
        try:
            self.embeddings = HuggingFaceEmbeddings(model_name=model_name)
            self.batch_size = batch_size
            logger.info("Embedding model loaded")
        except Exception as e:
            logger.error(f"Failed to load embedding model: {e}")
            raise
    
    @handle_errors
    def embed_text(self, text: str) -> List[float]:
        """Generate embedding for single text."""
        if not text or not isinstance(text, str):
            raise ValueError("Text must be a non-empty string")
        return self.embeddings.embed_query(text)
    
    @handle_errors
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for batch of texts."""
        if not texts:
            return []
        return self.embeddings.embed_documents(texts)

class IncidentEmbeddingPipeline:
    """Orchestrate incident embedding generation and storage."""
    
    def __init__(self, batch_size: int = 32):
        """Initialize pipeline components."""
        self.store = EmbeddingStore()
        self.embedder = IncidentEmbedder(batch_size=batch_size)
        self.batch_size = batch_size
    
    @log_operation
    @handle_errors
    def process_incidents(self, limit: Optional[int] = None) -> None:
        """Fetch incidents and generate embeddings."""
        incidents = self.store.fetch_incidents(limit=limit)
        
        if not incidents:
            logger.warning("No incidents to process")
            return
        
        # Process in batches
        for i in range(0, len(incidents), self.batch_size):
            batch = incidents[i : i + self.batch_size]
            incident_ids = [row[0] for row in batch]
            error_logs = [row[1] for row in batch]
            
            # Generate embeddings
            embeddings = self.embedder.embed_batch(error_logs)
            
            # Prepare data for batch insert
            embeddings_data = list(zip(incident_ids, embeddings))
            
            # Store embeddings
            self.store.batch_insert_embeddings(embeddings_data)
            logger.info(f"Processed batch {i // self.batch_size + 1}/{(len(incidents) + self.batch_size - 1) // self.batch_size}")
        
        # Summary
        embedded_count = self.store.get_embedded_count()
        logger.info(f"Total embedded incidents: {embedded_count}")
    
    def cleanup(self) -> None:
        """Clean up resources."""
        self.store.close_pool()
        logger.info("🧹 Pipeline cleanup completed")

if __name__ == "__main__":
    pipeline = IncidentEmbeddingPipeline(batch_size=32)
    try:
        pipeline.process_incidents()  # Process all incidents
        # pipeline.process_incidents(limit=10)  # Or limit to specific count
    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        raise
    finally:
        pipeline.cleanup()