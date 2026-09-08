"""Typed state and evidence models for the RCA graph."""

from __future__ import annotations

from typing import Any, Dict, List, TypedDict


class AnalyzerState(TypedDict, total=False):
    incident_query: str
    failed_job_name: str
    support_manual_entries: List[Dict[str, Any]]
    incident_id: int
    similar_incidents: List[Dict[str, Any]]
    architecture_chunks: List[Dict[str, Any]]
    services: List[Dict[str, Any]]
    logs: List[Dict[str, Any]]
    initial_rca: Dict[str, Any]
    rca_candidates: List[Dict[str, Any]]
    selected_rca: Dict[str, Any]
    confidence: int
    evidence: Dict[str, Any]
    error: str


REQUIRED_RCA_FIELDS = (
    "root_cause",
    "contributing_factors",
    "timeline",
    "resolution",
    "evidence_refs",
    "rca_draft",
    "confidence_hint",
)
