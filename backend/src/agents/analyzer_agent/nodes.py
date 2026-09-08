"""LangGraph node functions for incident RCA."""

from __future__ import annotations

import re
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List

from src.utils import handle_errors, log_operation

from .models import AnalyzerState
from .prompts import evidence_prompt, job_extraction_prompt, service_extraction_prompt
from .validation import extract_json_object, validate_candidates, validate_rca

logger = logging.getLogger(__name__)


def _record_incident(item: Any) -> Dict[str, Any]:
    if isinstance(item, dict):
        return dict(item)
    values = list(item)
    keys = ("incident_id", "service", "error_log", "root_cause", "resolution", "distance")
    return {key: values[index] if index < len(values) else None for index, key in enumerate(keys)}


def _score(distance: Any) -> float:
    try:
        return round(max(0.0, min(1.0, 1.0 - float(distance))), 4)
    except (TypeError, ValueError):
        return 0.0


def _fallback_services(query: str) -> List[Dict[str, Any]]:
    known_services = ("glue", "lambda", "emr", "athena", "s3", "sqs", "sns", "iam", "rds", "ecs", "eks")
    return [
        {"service": service, "resource": None, "score": 0.5}
        for service in known_services
        if re.search(rf"\b{re.escape(service)}\b", query, re.IGNORECASE)
    ]


class AnalyzerNodes:
    def __init__(self, db: Any, incident_search: Any, incident_embedder: Any, doc_embedder: Any, llm: Any, log_provider: Any = None, threshold: int = 95, log_window_minutes: int = 30):
        self.db = db
        self.incident_search = incident_search
        self.incident_embedder = incident_embedder
        self.doc_embedder = doc_embedder
        self.llm = llm
        self.log_provider = log_provider
        self.threshold = threshold
        self.log_window_minutes = log_window_minutes

    @log_operation
    @handle_errors
    def extract_job_name(self, state: AnalyzerState) -> AnalyzerState:
        """Extract the failed job name before searching the support manual."""
        query = state["incident_query"]
        match = re.search(r"\bJob\s+(?:ERROR\s*:\s*)?([A-Za-z0-9][A-Za-z0-9_.-]*)", query, re.IGNORECASE)
        job_name = match.group(1) if match else None

        if not job_name:
            try:
                response = extract_json_object(
                    self.llm.generate(
                        prompt=job_extraction_prompt(query),
                        temperature=0.0,
                        max_tokens=200,
                    )
                )
                candidate = response.get("failed_job_name")
                job_name = candidate if isinstance(candidate, str) and candidate.strip() else None
            except Exception:
                logger.warning("Failed to extract a job name from incident trace")

        state["failed_job_name"] = job_name or ""
        state.setdefault("evidence", {})["failed_job_name"] = state["failed_job_name"]
        return state

    @log_operation
    @handle_errors
    def retrieve_support_manual(self, state: AnalyzerState) -> AnalyzerState:
        """Retrieve manual chunks matching the exact failed job name."""
        job_name = state.get("failed_job_name", "")
        if job_name and hasattr(self.db, "search_support_manual_by_job"):
            entries = self.db.search_support_manual_by_job(job_name=job_name, top_k=5)
        else:
            entries = []
        state["support_manual_entries"] = entries
        state.setdefault("evidence", {})["support_manual_entries"] = entries
        return state

    @log_operation
    @handle_errors
    def extract_services(self, state: AnalyzerState) -> AnalyzerState:
        """Identify services and resources directly from the incoming incident trace."""
        services: List[Dict[str, Any]] = []
        try:
            response = extract_json_object(
                self.llm.generate(
                    prompt=service_extraction_prompt(
                        query=state["incident_query"],
                        support_manual_entries=state.get("support_manual_entries", []),
                    ),
                    temperature=0.0,
                    max_tokens=800,
                )
            )
            print("Service extraction response:", response)
            raw_services = response.get("services", [])
            for item in raw_services:
                if not isinstance(item, dict) or not item.get("service"):
                    continue
                try:
                    score = max(0.0, min(1.0, float(item.get("score", 0.0))))
                except (TypeError, ValueError):
                    score = 0.0
                services.append({
                    "service": str(item["service"]).lower(),
                    "resource": item.get("resource") or state.get("failed_job_name"),
                    "score": score,
                })
        except Exception:
            logger.exception(
                "Service extraction failed. Failed job=%s, manual_entries=%d",
                state.get("failed_job_name"),
                len(state.get("support_manual_entries", [])),
            )

        state["services"] = services or _fallback_services(state["incident_query"])
        state.setdefault("evidence", {})["identified_services"] = state["services"]
        return state

    @log_operation
    @handle_errors
    def register_incident(self, state: AnalyzerState) -> AnalyzerState:
        """Persist the incoming incident before searching historical incidents."""
        if hasattr(self.db, "insert_incident"):
            identified_services = state.get("services") or []
            primary_service = identified_services[0].get("service", "unknown") if identified_services else "unknown"
            incident_id = self.db.insert_incident(
                service=primary_service,
                error_log=state["incident_query"],
            )
            state["incident_id"] = incident_id
            if hasattr(self.db, "insert_incident_embedding"):
                embedding = self.incident_embedder.embed_text(state["incident_query"])
                self.db.insert_incident_embedding(incident_id, embedding)
        return state

    @log_operation
    @handle_errors
    def retrieve_incidents(self, state: AnalyzerState) -> AnalyzerState:
        matches = self.incident_search.search(state["incident_query"], top_k=5)
        records = [_record_incident(match) for match in matches]
        for record in records:
            record["similarity_score"] = _score(record.get("distance"))
        state["similar_incidents"] = records
        state["evidence"] = {"incidents": records}
        return state

    @log_operation
    @handle_errors
    def generate_initial_rca(self, state: AnalyzerState) -> AnalyzerState:
        prompt = evidence_prompt(state["incident_query"], state.get("similar_incidents", []), [], [], 1)
        result = validate_rca(extract_json_object(self.llm.generate(prompt=prompt, temperature=0.0, max_tokens=1400)))
        state["initial_rca"] = result
        state["confidence"] = result["confidence_hint"]
        return state

    def route_after_initial(self, state: AnalyzerState) -> str:
        return "finalize" if state.get("confidence", 0) >= self.threshold else "deep_analysis"

    @log_operation
    @handle_errors
    def retrieve_architecture(self, state: AnalyzerState) -> AnalyzerState:
        if not self.doc_embedder:
            chunks = self.db.search_doc_chunks_text(state["incident_query"], top_k=8)
        else:
            embedding = self.doc_embedder.embed_text(state["incident_query"])
            chunks = self.db.search_doc_chunks_vector(query_embedding=embedding, top_k=8)
        state["architecture_chunks"] = chunks or []
        services: Dict[str, float] = {}
        resources: Dict[str, Any] = {}
        for item in state.get("services", []):
            service = str(item.get("service") or "").lower()
            if service:
                services[service] = float(item.get("score", 0.0))
                resources[service] = item.get("resource")
        for item in state["similar_incidents"]:
            service = str(item.get("service") or "").lower()
            if service:
                services[service] = services.get(service, 0.0) + item.get("similarity_score", 0.0)
        for chunk in state["architecture_chunks"]:
            service = str((chunk.get("metadata") or {}).get("service") or "").lower()
            if service:
                services[service] = services.get(service, 0.0) + 0.5
        state["services"] = [{"service": name, "resource": resources.get(name), "score": round(score, 4)} for name, score in sorted(services.items(), key=lambda pair: pair[1], reverse=True)]
        state.setdefault("evidence", {})["architecture_chunks"] = state["architecture_chunks"]
        return state

    @log_operation
    @handle_errors
    def retrieve_logs(self, state: AnalyzerState) -> AnalyzerState:
        logs: List[Dict[str, Any]] = []
        if self.log_provider:
            end = datetime.utcnow() + timedelta(minutes=self.log_window_minutes)
            start = datetime.utcnow() - timedelta(minutes=self.log_window_minutes)
            combined = state["incident_query"] + " " + " ".join(str(item.get("content", "")) for item in state.get("architecture_chunks", []))
            resource_match = re.search(r"(?:arn:aws:[\w:/-]+|requestId[:=]\s*[\w-]+|job[_ -]?id[:=]\s*[\w-]+|function[:=]\s*[\w-]+)", combined, re.I)
            resource = resource_match.group(0) if resource_match else None
            for service in state.get("services", [])[:3]:
                try:
                    events = self.log_provider.fetch_logs(service["service"], service.get("resource") or resource, start, end, "ERROR")
                except Exception:
                    events = []
                for event in events:
                    logs.append({"log_id": event.get("id") or event.get("eventId"), "timestamp": event.get("timestamp"), "service": service["service"], "snippet": str(event.get("message") or event.get("msg") or "")[:4000], "relevance_score": service["score"]})
        state["logs"] = logs
        state.setdefault("evidence", {})["logs"] = logs
        return state

    @log_operation
    @handle_errors
    def generate_deep_rcas(self, state: AnalyzerState) -> AnalyzerState:
        prompt = evidence_prompt(state["incident_query"], state.get("similar_incidents", []), state.get("architecture_chunks", []), state.get("logs", []), 3)
        response = extract_json_object(self.llm.generate(prompt=prompt, temperature=0.0, max_tokens=3600))
        candidates = response.get("candidates") if isinstance(response.get("candidates"), list) else []
        state["rca_candidates"] = validate_candidates(candidates, expected=3)
        state["selected_rca"] = max(state["rca_candidates"], key=lambda item: item["confidence_hint"])
        state["confidence"] = state["selected_rca"]["confidence_hint"]
        return state

    @log_operation
    @handle_errors
    def finalize(self, state: AnalyzerState) -> AnalyzerState:
        selected = state.get("selected_rca") or state.get("initial_rca")
        state["selected_rca"] = selected
        self.db.insert_rca(
            incident_query=state["incident_query"],
            rca={"candidates": state.get("rca_candidates", [selected]), "selected": selected},
            incident_ids=[item["incident_id"] for item in state.get("similar_incidents", []) if isinstance(item.get("incident_id"), int)],
            evidence=state.get("evidence", {}),
        )
        return state
