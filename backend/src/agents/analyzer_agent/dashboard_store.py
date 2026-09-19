"""Read-only database queries for the incident dashboard."""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional

from src.config.db_config import DB_CONFIG
from src.utils import DatabaseManager, handle_errors


class DashboardStore(DatabaseManager):
    """Fetch dashboard incidents and RCA details from PostgreSQL."""

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
    def get_todays_incidents(
        self,
        incident_date: Optional[date] = None,
    ) -> List[Dict[str, Any]]:
        """Return today's incidents with their latest related RCA."""
        selected_date = incident_date or date.today()

        sql = """
            SELECT
                i.incident_id,
                i.service,
                i.error_log,
                i.root_cause,
                i.resolution,
                i.validated,
                i.created_at,
                r.rca_id,
                r.rca_json,
                r.evidence,
                r.created_at AS rca_created_at
            FROM incidents AS i
            LEFT JOIN LATERAL (
                SELECT
                    rca_id,
                    rca_json,
                    evidence,
                    created_at
                FROM analyzer_rcas
                WHERE i.incident_id = ANY(incident_ids)
                ORDER BY created_at DESC
                LIMIT 1
            ) AS r ON TRUE
            WHERE i.created_at >= %s
              AND i.created_at < %s + INTERVAL '1 day'
            ORDER BY i.created_at DESC;
        """

        rows = self.execute_query(
            sql,
            (selected_date, selected_date),
            fetch_one=False,
        )

        return [
            {
                "incident_id": row[0],
                "service": row[1],
                "error_log": row[2],
                "root_cause": row[3],
                "resolution": row[4],
                "validated": row[5],
                "created_at": row[6],
                "rca_id": row[7],
                "rca_json": row[8] or {},
                "evidence": row[9] or {},
                "rca_created_at": row[10],
            }
            for row in rows or []
        ]

    @handle_errors
    def get_incident_details(
        self,
        incident_id: int,
    ) -> Optional[Dict[str, Any]]:
        """Return one incident with its latest related RCA."""
        sql = """
            SELECT
                i.incident_id,
                i.service,
                i.error_log,
                i.root_cause,
                i.resolution,
                i.validated,
                i.created_at,
                r.rca_id,
                r.rca_json,
                r.evidence,
                r.created_at AS rca_created_at
            FROM incidents AS i
            LEFT JOIN LATERAL (
                SELECT
                    rca_id,
                    rca_json,
                    evidence,
                    created_at
                FROM analyzer_rcas
                WHERE i.incident_id = ANY(incident_ids)
                ORDER BY created_at DESC
                LIMIT 1
            ) AS r ON TRUE
            WHERE i.incident_id = %s;
        """

        row = self.execute_query(
            sql,
            (incident_id,),
            fetch_one=True,
        )

        if not row:
            return None

        return {
            "incident_id": row[0],
            "service": row[1],
            "error_log": row[2],
            "root_cause": row[3],
            "resolution": row[4],
            "validated": row[5],
            "created_at": row[6],
            "rca_id": row[7],
            "rca_json": row[8] or {},
            "evidence": row[9] or {},
            "rca_created_at": row[10],
        }