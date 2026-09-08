"""Common decorators for error handling, logging, and validation."""

import logging
from functools import wraps
from typing import List
import psycopg2
import time
import os

logger = logging.getLogger(__name__)


def log_query(func):
    """Log every database query and its execution time."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        query = kwargs.get("query") or (args[1] if len(args) > 1 else "")
        params = kwargs.get("params") or (args[2] if len(args) > 2 else None)

        started = time.perf_counter()
        logger.info(
            "SQL START | %s | params=%r",
            " ".join(str(query).split()),
            params,
        )

        try:
            result = func(*args, **kwargs)
            elapsed_ms = (time.perf_counter() - started) * 1000
            logger.info("SQL END | %.2f ms", elapsed_ms)
            return result
        except Exception:
            elapsed_ms = (time.perf_counter() - started) * 1000
            logger.exception("SQL FAILED | %.2f ms", elapsed_ms)
            raise

    return wrapper

def log_many_query(func):
    """Log batch database queries."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        query = kwargs.get("query") or (args[1] if len(args) > 1 else "")
        data = kwargs.get("data") or (args[2] if len(args) > 2 else [])

        logger.info(
            "SQL BATCH START | %s | rows=%d",
            " ".join(str(query).split()),
            len(data),
        )

        started = time.perf_counter()
        try:
            result = func(*args, **kwargs)
            elapsed_ms = (time.perf_counter() - started) * 1000
            logger.info("SQL BATCH END | %.2f ms", elapsed_ms)
            return result
        except Exception:
            logger.exception("SQL BATCH FAILED")
            raise

    return wrapper

def handle_errors(func):
    """Decorator to handle database and general errors."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except psycopg2.Error as e:
            logger.error(f"Database error in {func.__name__}: {e}")
            raise
        except FileNotFoundError as e:
            logger.error(f"File not found in {func.__name__}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in {func.__name__}: {e}")
            raise
    return wrapper

def log_operation(func):
    """Decorator to log operation start and completion."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        logger.info(f"Starting: {func.__name__}")
        try:
            result = func(*args, **kwargs)
            logger.info(f"Completed: {func.__name__}")
            return result
        except Exception as e:
            logger.error(f"Failed: {func.__name__} - {str(e)}")
            raise
    return wrapper

def validate_file_type(func):
    """Decorator to validate file extension."""
    @wraps(func)
    def wrapper(self, file_path: str, *args, **kwargs):
        ext = os.path.splitext(file_path)[1].lower()
        if ext not in [".docx", ".pdf"]:
            raise ValueError(f"Unsupported file type: {ext}")
        return func(self, file_path, *args, **kwargs)
    return wrapper

def validate_embedding(embedding_dimension: int):
    """Decorator factory to validate embedding dimensions."""
    def decorator(func):
        @wraps(func)
        def wrapper(self, incident_id: int, embedding: List[float], *args, **kwargs):
            if not isinstance(embedding, list):
                raise ValueError(f"Embedding must be a list, got {type(embedding)}")
            if len(embedding) != embedding_dimension:
                raise ValueError(
                    f"Embedding dimension mismatch. Expected {embedding_dimension}, got {len(embedding)}"
                )
            return func(self, incident_id, embedding, *args, **kwargs)
        return wrapper
    return decorator
