from pathlib import Path
from typing import List, Optional

from docx import Document
import fitz
import logging
import mimetypes
import os
import psycopg2

from src.config.db_config import DB_CONFIG
from src.utils import handle_errors, validate_file_type, log_operation


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
DOCS_DIR = os.path.join(BASE_DIR, "docs")


class DocumentProcessor:
    """Read documents and store them in PostgreSQL."""

    def __init__(self):
        self.conn = None

    @handle_errors
    def connect(self):
        self.conn = psycopg2.connect(**DB_CONFIG)
        logger.info("Database connection established")

    def disconnect(self):
        if self.conn:
            self.conn.close()
            logger.info("Database connection closed")

    @staticmethod
    def read_docx(file_path: str) -> str:
        doc = Document(file_path)
        return "\n".join(
            paragraph.text
            for paragraph in doc.paragraphs
            if paragraph.text.strip()
        )

    @staticmethod
    def read_pdf(file_path: str) -> str:
        text = []

        with fitz.open(file_path) as pdf:
            for page in pdf:
                text.append(page.get_text())

        return "\n".join(text)

    @validate_file_type
    @handle_errors
    def read_file(self, file_path: str) -> str:
        extension = Path(file_path).suffix.lower()

        if extension == ".docx":
            return self.read_docx(file_path)

        return self.read_pdf(file_path)

    @handle_errors
    def insert_document(
        self,
        title: str,
        content: Optional[str],
        image_paths: List[str],
        doc_type: str,
        file_path: str,
        image_data=None,
    ) -> int:
        """Insert a document or image and return its database ID."""
        sql = """
            INSERT INTO architecture_docs
                (title, content, image_paths, doc_type, file_path, image_data)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING doc_id;
        """

        with self.conn.cursor() as cursor:
            cursor.execute(
                sql,
                (
                    title,
                    content,
                    image_paths,
                    doc_type,
                    file_path,
                    image_data,
                ),
            )
            doc_id = cursor.fetchone()[0]
            self.conn.commit()

        logger.info("Inserted %s with ID %s", title, doc_id)
        return doc_id

    @log_operation
    @handle_errors
    def process_file(
        self,
        file_path: str,
        title: str,
        doc_type: str,
        image_paths: Optional[List[str]] = None,
    ) -> None:
        content = self.read_file(file_path)

        self.insert_document(
            title=title,
            content=content,
            image_paths=image_paths or [],
            doc_type=doc_type,
            file_path=file_path,
        )

    @log_operation
    @handle_errors
    def process_image(
        self,
        file_path: str,
        title: str,
        doc_type: str = "architecture_diagram",
    ) -> None:
        """Read a PNG/JPEG file and store its bytes in architecture_docs."""
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"Image not found: {path}")

        mime_type, _ = mimetypes.guess_type(path.name)

        if mime_type not in {"image/png", "image/jpeg"}:
            raise ValueError(f"Unsupported image type: {path.suffix}")

        with path.open("rb") as image_file:
            image_data = psycopg2.Binary(image_file.read())

        self.insert_document(
            title=title,
            content=None,
            image_paths=[str(path)],
            doc_type=doc_type,
            file_path=str(path),
            image_data=image_data,
        )


class ArchitectureDocLoader:
    """Load architecture documents and image files."""

    def __init__(self):
        self.processor = DocumentProcessor()

    def load_documents(self) -> None:
        self.processor.connect()

        try:
            self.processor.process_file(
                os.path.join(DOCS_DIR, "Application Support Manual.docx"),
                "Application Support Manual",
                "manual",
            )

            # self.processor.process_file(
            #     os.path.join(DOCS_DIR, "Application_Flow_Manual.docx"),
            #     "Application Flow Manual",
            #     "flow",
            # )

            # self.processor.process_file(
            #     os.path.join(DOCS_DIR, "Project_Architecture_Flow_Manual.docx"),
            #     "Project Architecture Flow Manual",
            #     "architecture",
            # )

            # self.processor.process_image(
            #     os.path.join(DOCS_DIR, "DataLake_application_architect.png"),
            #     "DataLake Application Architecture",
            # )

        finally:
            self.processor.disconnect()


if __name__ == "__main__":
    ArchitectureDocLoader().load_documents()