"""HTTP API for the RCA L1 CoPilot dashboard."""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.agents.analyzer_agent import AnalyzerStore, RCAAnalyzerAgent
from src.agents.analyzer_agent.dashboard_store import DashboardStore
from src.agents.analyzer_agent.log_providers import FlociLogProvider


app = FastAPI(
    title="RCA L1 CoPilot API",
    version="0.1.0",
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


dashboard_store = DashboardStore()
analyzer_agent: RCAAnalyzerAgent | None = None


class AnalyzeIncidentRequest(BaseModel):
    incident_query: str


class FlociClient:
    def fetch_logs(self, service, resource, start, end, pattern=None):
        """Return no logs until the production Floci client is configured."""
        return []


def get_analyzer_agent() -> RCAAnalyzerAgent:
    """Create the analyzer lazily so dashboard health checks stay lightweight."""
    global analyzer_agent

    if analyzer_agent is None:
        analyzer_store = AnalyzerStore()
        analyzer_agent = RCAAnalyzerAgent(
            db=analyzer_store,
            log_provider=FlociLogProvider(FlociClient()),
        )

    return analyzer_agent


@app.get("/health")
def health_check() -> Dict[str, str]:
    """Confirm that the API process is running."""
    return {"status": "ok"}


@app.get("/api/dashboard/today")
def get_today_dashboard() -> Dict[str, Any]:
    """Return today's incidents for the dashboard sidebar."""
    try:
        incidents = dashboard_store.get_todays_incidents()

        return {
            "incidents": incidents,
            "count": len(incidents),
        }

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Failed to load today's incidents.",
        ) from exc


@app.get("/api/incidents/{incident_id}")
def get_incident(incident_id: int) -> Dict[str, Any]:
    """Return complete details for one incident."""
    try:
        incident = dashboard_store.get_incident_details(incident_id)

        if incident is None:
            raise HTTPException(
                status_code=404,
                detail=f"Incident {incident_id} was not found.",
            )

        return incident

    except HTTPException:
        raise

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Failed to load incident details.",
        ) from exc


@app.post("/api/incidents/analyze")
def analyze_incident(request: AnalyzeIncidentRequest) -> Dict[str, Any]:
    """Analyze a new incident, persist it, and return its stored details."""
    if not request.incident_query.strip():
        raise HTTPException(
            status_code=400,
            detail="incident_query must not be empty.",
        )

    try:
        state = get_analyzer_agent().analyze(request.incident_query)
        incident_id = state.get("incident_id")

        if not isinstance(incident_id, int):
            raise RuntimeError("Analyzer did not return a valid incident_id")

        incident = dashboard_store.get_incident_details(incident_id)

        if incident is None:
            raise RuntimeError(
                f"Analyzed incident {incident_id} was not found after persistence"
            )

        return incident

    except HTTPException:
        raise

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Failed to analyze incident.",
        ) from exc