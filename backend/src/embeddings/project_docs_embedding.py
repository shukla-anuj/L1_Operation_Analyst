import logging
from pathlib import Path
from typing import List

from langchain_community.document_loaders import (
    UnstructuredImageLoader,
    UnstructuredWordDocumentLoader,
)
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from psycopg2.extras import Json

from src.config.db_config import DB_CONFIG
from src.utils import DatabaseManager, handle_errors, log_operation

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "sentence-transformers/all-mpnet-base-v2"
EMBEDDING_DIMENSION = 768


class ProjectDocEmbeddingStore(DatabaseManager):
    """Store project document embeddings in PostgreSQL."""

    def __init__(self, db_config=None):
        super().__init__(db_config or DB_CONFIG)

    @handle_errors
    def insert_chunk(
        self,
        doc_id: int,
        chunk_index: int,
        content: str,
        embedding: List[float],
        metadata: dict,
    ) -> None:
        if len(embedding) != EMBEDDING_DIMENSION:
            raise ValueError(
                f"Expected {EMBEDDING_DIMENSION} dimensions, "
                f"got {len(embedding)}"
            )

        sql = """
            INSERT INTO architecture_doc_chunks
                (doc_id, chunk_index, content, embedding, metadata)
            VALUES
                (%s, %s, %s, %s, %s::jsonb)
            ON CONFLICT (doc_id, chunk_index) DO UPDATE
            SET content = EXCLUDED.content,
                embedding = EXCLUDED.embedding,
                metadata = EXCLUDED.metadata;
        """

        self.execute_query(
            sql,
            (
                doc_id,
                chunk_index,
                content,
                embedding,
                Json(metadata),
            ),
        )

        logger.info(
            "Inserted chunk %s for document %s",
            chunk_index,
            doc_id,
        )


class ProjectDocEmbedder:
    """Generate document embeddings using Hugging Face."""

    def __init__(self, model_name: str = EMBEDDING_MODEL):
        self.embedder = HuggingFaceEmbeddings(
            model_name=model_name,
            encode_kwargs={"normalize_embeddings": True},
        )

    @handle_errors
    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []

        return self.embedder.embed_documents(texts)


class ProjectDocPipeline:
    """Load, split, embed, and store project documents."""

    def __init__(self, batch_size: int = 32):
        self.store = ProjectDocEmbeddingStore()
        self.embedder = ProjectDocEmbedder()
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=100,
        )
        self.batch_size = batch_size

    @log_operation
    @handle_errors
    def process_doc(
        self,
        file_path: str,
        doc_id: int,
        service: str,
        author: str,
    ) -> None:
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"Document not found: {path}")

        suffix = path.suffix.lower()

        if suffix == ".docx":
            loader = UnstructuredWordDocumentLoader(str(path))
        elif suffix in {".png", ".jpg", ".jpeg"}:
            loader = UnstructuredImageLoader(str(path))
        else:
            raise ValueError(
                f"Unsupported file type: {suffix}. "
                "Supported types are .docx, .png, .jpg, and .jpeg."
            )

        documents = loader.load()
        chunks = self.splitter.split_documents(documents)
        texts = [chunk.page_content for chunk in chunks]
        embeddings = self.embedder.embed_texts(texts)

        for chunk_index, (chunk, embedding) in enumerate(
            zip(chunks, embeddings)
        ):
            metadata = {
                "service": service,
                "source": path.name,
                "author": author,
                "chunk_length": len(chunk.page_content),
                "embedding_model": EMBEDDING_MODEL,
                "embedding_dimension": EMBEDDING_DIMENSION,
                "source_metadata": chunk.metadata,
            }

            self.store.insert_chunk(
                doc_id=doc_id,
                chunk_index=chunk_index,
                content=chunk.page_content,
                embedding=embedding,
                metadata=metadata,
            )

        logger.info(
            "Processed %s chunks for %s",
            len(chunks),
            path.name,
        )

    def cleanup(self) -> None:
        self.store.close_pool()
        logger.info("Document embedding pipeline cleaned up")


if __name__ == "__main__":
    pipeline = ProjectDocPipeline()

    try:
        pipeline.process_doc("docs/Application Support Manual.docx", doc_id=1, service="Support", author="Anuj Shukla")
        pipeline.process_doc("docs/Application_Flow_Manual.docx", doc_id=2, service="Glue", author="Anuj Shukla")
        pipeline.process_doc("docs/Project_Architecture_Flow_Manual.docx", doc_id=3, service="Architecture", author="Anuj Shukla")
        pipeline.process_doc("docs/DataLake_application_architect.png", doc_id=4, service="DataLake", author="Anuj Shukla")
    finally:
        pipeline.cleanup()