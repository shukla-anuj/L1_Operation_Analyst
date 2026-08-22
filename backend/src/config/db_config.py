import os
from dotenv import load_dotenv

# Load environment variables from .env file (only in dev)
load_dotenv()

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "dbname": os.getenv("DB_NAME", "kb_db"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASS"),  # must be set in environment
    "port": os.getenv("DB_PORT", "5433") # enforce SSL in finance org
}
