"""Public facade for the LangGraph RCA analyzer."""

from __future__ import annotations

from typing import Any, Dict

from src.embeddings.incident_embeddings import IncidentEmbedder
from src.scripts.search_incidents import IncidentSearchPipeline

from .graph import build_analyzer_graph
from .llm_client import HuggingFaceLLM
from .models import AnalyzerState
from .nodes import AnalyzerNodes


class RCAAnalyzerAgent:
    def __init__(self, db: Any, doc_embedder: Any = None, log_provider: Any = None, llm: Any = None, incident_search: Any = None, confidence_threshold: int = 95):
        self.db = db
        self.incident_embedder = IncidentEmbedder()
        self.incident_search = incident_search or IncidentSearchPipeline(embedder=self.incident_embedder)
        self.llm = llm or HuggingFaceLLM()
        self.nodes = AnalyzerNodes(db, self.incident_search, self.incident_embedder, doc_embedder, self.llm, log_provider, confidence_threshold)
        self.graph = build_analyzer_graph(self.nodes)

    def analyze(self, incident_query: str) -> Dict[str, Any]:
        state: AnalyzerState = {"incident_query": incident_query}
        return dict(self.graph.invoke(state))

    def close(self) -> None:
        if hasattr(self.incident_search, "cleanup"):
            self.incident_search.cleanup()
        if hasattr(self.db, "close_pool"):
            self.db.close_pool()
