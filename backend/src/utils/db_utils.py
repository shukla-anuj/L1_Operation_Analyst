"""Database utilities and connection management."""

import psycopg2
from psycopg2 import pool
import logging
from typing import Optional, List, Tuple
from src.utils.decorators import log_query, log_many_query

logger = logging.getLogger(__name__)

class DatabaseManager:
    """Base class for database operations with connection pooling."""
    
    def __init__(self, db_config: dict, min_connections: int = 2, max_connections: int = 10):
        """
        Initialize database manager with connection pool.
        
        Args:
            db_config: Database configuration dictionary (host, user, password, database, port)
            min_connections: Minimum connections in pool
            max_connections: Maximum connections in pool
        """
        try:
            self.pool = psycopg2.pool.SimpleConnectionPool(
                min_connections,
                max_connections,
                **db_config
            )
            logger.info("Connection pool initialized")
        except Exception as e:
            logger.error(f"Failed to initialize connection pool: {e}")
            raise
    
    def get_connection(self):
        """Get connection from pool."""
        return self.pool.getconn()
    
    def release_connection(self, conn):
        """Return connection to pool."""
        self.pool.putconn(conn)
    
    def close_pool(self):
        """Close all connections in pool."""
        self.pool.closeall()
        logger.info("Connection pool closed")
    
    # def execute_query(self, query: str, params: tuple = None, fetch_one: bool = False):
    #     """
    #     Execute a query and optionally fetch results.
        
    #     Args:
    #         query: SQL query string
    #         params: Query parameters
    #         fetch_one: If True, fetch one row; if False, fetch all
            
    #     Returns:
    #         Query result or None
    #     """
    #     conn = self.get_connection()
    #     try:
    #         with conn.cursor() as cur:
    #             cur.execute(query, params or ())
    #             if query.strip().upper().startswith("SELECT"):
    #                 return cur.fetchone() if fetch_one else cur.fetchall()
    #             else:
    #                 conn.commit()
    #                 return None
    #     finally:
    #         self.release_connection(conn)

    @log_query
    def execute_query(
        self,
        query: str,
        params: tuple = None,
        fetch_one: bool = False,
    ):
        conn = self.get_connection()

        try:
            with conn.cursor() as cur:
                cur.execute(query, params or ())

                result = None
                if cur.description is not None:
                    result = (
                        cur.fetchone()
                        if fetch_one
                        else cur.fetchall()
                    )

                conn.commit()
                return result

        except Exception:
            conn.rollback()
            raise

        finally:
            self.release_connection(conn)

    
    @log_many_query
    def execute_many(self, query: str, data: List[Tuple]):
        """
        Execute query with multiple parameter sets (batch operation).
        
        Args:
            query: SQL query string
            data: List of parameter tuples
        """
        if not data:
            logger.warning("No data to insert")
            return
        
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.executemany(query, data)
                conn.commit()
            logger.info(f"Batch executed for {len(data)} records")
        finally:
            self.release_connection(conn)
