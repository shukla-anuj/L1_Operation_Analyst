import psycopg2
from docx import Document
import fitz  # PyMuPDF for PDF
import os
from src.config.db_config import DB_CONFIG

def read_docx(file_path):
    """Extract text from a Word document."""
    doc = Document(file_path)
    return "\n".join([para.text for para in doc.paragraphs if para.text.strip()])

def read_pdf(file_path):
    """Extract text from a PDF file."""
    text = []
    with fitz.open(file_path) as pdf:
        for page in pdf:
            text.append(page.get_text())
    return "\n".join(text)

def insert_document(title, content, image_paths, doc_type, file_path):
    """Insert document record into architecture_docs table securely."""
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        with conn:
            with conn.cursor() as cur:
                sql = """
                    INSERT INTO architecture_docs (title, content, image_paths, doc_type, file_path)
                    VALUES (%s, %s, %s, %s, %s)
                """
                cur.execute(sql, (title, content, image_paths, doc_type, file_path))
        print(f"✅ Inserted: {title}")
    finally:
        conn.close()

def process_file(file_path, title, doc_type, image_paths=None):
    """Read file and insert into DB."""
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".docx":
        content = read_docx(file_path)
    elif ext == ".pdf":
        content = read_pdf(file_path)
    else:
        raise ValueError("Unsupported file type")

    insert_document(title, content, image_paths or [], doc_type, file_path)

if __name__ == "__main__":
    process_file(
        "/app/docs/Application_Support_Manual.docx",
        "Application Support Manual",
        "manual",
        ["/app/docs/images/support_flow.png"]
    )
    process_file(
        "/app/docs/Application_Flow_Manual.docx",
        "Application Flow Manual",
        "flow",
        ["/app/docs/images/app_flow.png"]
    )
    process_file(
        "/app/docs/Project_Architecture_Flow_Manual.docx",
        "Project Architecture Flow Manual",
        "architecture",
        ["/app/docs/images/overview.png","/app/docs/images/processing.png"]
    )
