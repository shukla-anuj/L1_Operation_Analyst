from docx import Document
import fitz
import os
import logging
import psycopg2
from typing import List, Optional
from src.config.db_config import DB_CONFIG
from src.utils import handle_errors, validate_file_type, log_operation

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get the base directory (backend/)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DOCS_DIR = os.path.join(BASE_DIR, "docs")

class DocumentProcessor:
    """Handle document reading and database operations."""
    
    def __init__(self):
        self.conn = None
    
    @handle_errors
    def connect(self):
        """Establish database connection."""
        self.conn = psycopg2.connect(**DB_CONFIG)
        logger.info("Database connection established")
    
    def disconnect(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
            logger.info("Database connection closed")
    
    @staticmethod
    def read_docx(file_path: str) -> str:
        """Extract text from Word document."""
        doc = Document(file_path)
        return "\n".join([para.text for para in doc.paragraphs if para.text.strip()])
    
    @staticmethod
    def read_pdf(file_path: str) -> str:
        """Extract text from PDF file."""
        text = []
        with fitz.open(file_path) as pdf:
            for page in pdf:
                text.append(page.get_text())
        return "\n".join(text)
    
    @validate_file_type
    @handle_errors
    def read_file(self, file_path: str) -> str:
        """Read file based on extension."""
        ext = os.path.splitext(file_path)[1].lower()
        return self.read_docx(file_path) if ext == ".docx" else self.read_pdf(file_path)
    
    @handle_errors
    def insert_document(self, title: str, content: str, image_paths: List[str], 
                       doc_type: str, file_path: str) -> None:
        """Insert document record into architecture_docs table."""
        with self.conn.cursor() as cur:
            sql = """
                INSERT INTO architecture_docs (title, content, image_paths, doc_type, file_path)
                VALUES (%s, %s, %s, %s, %s)
            """
            cur.execute(sql, (title, content, image_paths, doc_type, file_path))
            self.conn.commit()
        logger.info(f"Inserted: {title}")
    
    @log_operation
    @handle_errors
    def process_file(self, file_path: str, title: str, doc_type: str, 
                    image_paths: Optional[List[str]] = None) -> None:
        """Read file and insert into database."""
        content = self.read_file(file_path)
        self.insert_document(title, content, image_paths or [], doc_type, file_path)

class ArchitectureDocLoader:
    """Manage batch loading of architecture documents."""
    
    def __init__(self):
        self.processor = DocumentProcessor()
    
    def load_documents(self) -> None:
        """Load all architecture documents."""
        self.processor.connect()
        try:
            documents = [
                {
                    "path": os.path.join(DOCS_DIR, "Application Support Manual.docx"),
                    "title": "Application Support Manual",
                    "type": "manual",
                    "images": []
                },
                {
                    "path": os.path.join(DOCS_DIR, "Application_Flow_Manual.docx"),
                    "title": "Application Flow Manual",
                    "type": "flow",
                    "images": []
                },
                {
                    "path": os.path.join(DOCS_DIR, "Project_Architecture_Flow_Manual.docx"),
                    "title": "Project Architecture Flow Manual",
                    "type": "architecture",
                    "images": [os.path.join(DOCS_DIR, "DataLake_application_architect.png")]
                }
            ]
            
            for doc in documents:
                self.processor.process_file(
                    doc["path"], doc["title"], doc["type"], doc["images"]
                )
        finally:
            self.processor.disconnect()

if __name__ == "__main__":
    loader = ArchitectureDocLoader()
    loader.load_documents()