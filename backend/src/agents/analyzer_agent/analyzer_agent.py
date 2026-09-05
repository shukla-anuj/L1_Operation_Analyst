# src/agents/analyzer_agent_final.py
"""
Analyzer Agent (final, single-file implementation)

This module implements a production-ready Analyzer Agent that:
- Uses your incident vector search pipeline to find similar incidents
- Uses pgvector doc-chunk search for architecture context
- Optionally fetches logs from a floci mock or real log service
- Calls an LLM to synthesize an evidence-backed RCA in strict JSON
- Validates the LLM output against a JSON schema and retries deterministically
- Attaches provenance and persists the RCA via DB adapter

Assumptions / expected project modules (adapt imports if your layout differs):
- src.db.adapter.DBAdapter  -> provides search_incidents, search_doc_chunks_vector, search_doc_chunks_text, insert_rca
- src.db.search_incidents.IncidentSearchPipeline -> vector incident search pipeline
- src.embeddings.incident_embeddings.IncidentEmbedder -> embed_text / embed_texts
- src.clients.llm_client.LLMClient -> generate(prompt, temperature, max_tokens) -> str
- src.clients.floci_client.FlociClient -> fetch_logs(service, resource, start, end, pattern) -> List[dict]
- src.agents.validator_agent.ValidatorAgent -> validate(rca_dict) -> dict with keys confidence, accepted, justification

This file is intentionally defensive: robust JSON extraction, schema validation, redaction before sending logs/docs to LLM,
and deterministic LLM settings (temperature=0).
"""

from __future__ import annotations

import json
import logging
import re
import math
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from src.agents.analyzer_agent.analyzer_store import AnalyzerStore
from src.scripts.search_incidents import IncidentSearchPipeline
from src.embeddings.incident_embeddings import IncidentEmbedder
from src.utils import handle_errors, log_operation

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


# -------------------------
# JSON schema for Analyzer output
# -------------------------
ANALYZER_JSON_SCHEMA = {
    "type": "object",
    "required": [
        "root_cause",
        "contributing_factors",
        "timeline",
        "resolution",
        "evidence_refs",
        "rca_draft",
        "confidence_hint",
    ],
    "properties": {
        "root_cause": {"type": "string"},
        "contributing_factors": {"type": "array", "items": {"type": "string"}},
        "timeline": {"type": "array", "items": {"type": "string"}},
        "resolution": {
            "type": "object",
            "required": ["immediate", "long_term"],
            "properties": {"immediate": {"type": "string"}, "long_term": {"type": "string"}},
        },
        "evidence_refs": {"type": "array", "items": {"type": "string"}},
        "rca_draft": {"type": "string"},
        "confidence_hint": {"type": "integer", "minimum": 0, "maximum": 100},
    },
    "additionalProperties": True,
}


class AnalyzerValidationError(ValueError):
    """Raised when an analyzer response does not match the RCA contract."""


def validate_analyzer_output(result: Dict[str, Any]) -> None:
    """Validate the required RCA fields without an external schema package."""
    required_fields = (
        "root_cause",
        "contributing_factors",
        "timeline",
        "resolution",
        "evidence_refs",
        "rca_draft",
        "confidence_hint",
    )
    missing = [field for field in required_fields if field not in result]
    if missing:
        raise AnalyzerValidationError(
            f"Missing analyzer fields: {', '.join(missing)}"
        )

    for field in ("root_cause", "rca_draft"):
        if not isinstance(result[field], str):
            raise AnalyzerValidationError(f"{field} must be a string")

    for field in ("contributing_factors", "timeline", "evidence_refs"):
        if not isinstance(result[field], list) or not all(
            isinstance(item, str) for item in result[field]
        ):
            raise AnalyzerValidationError(f"{field} must be a list of strings")

    resolution = result["resolution"]
    if not isinstance(resolution, dict) or not all(
        isinstance(resolution.get(field), str)
        for field in ("immediate", "long_term")
    ):
        raise AnalyzerValidationError(
            "resolution must contain immediate and long_term strings"
        )

    confidence = result["confidence_hint"]
    if (
        isinstance(confidence, bool)
        or not isinstance(confidence, int)
        or not 0 <= confidence <= 100
    ):
        raise AnalyzerValidationError(
            "confidence_hint must be an integer between 0 and 100"
        )


# -------------------------
# Prompt template
# -------------------------
ANALYZER_PROMPT_TEMPLATE = """You are the Analyzer Agent. Produce a concise, evidence-backed Root Cause Analysis in strict JSON.

Inputs
Incident Query:
{incident_query}

Top Incidents (ordered by similarity)
{similar_incidents}

Top Doc Chunks (ordered by similarity)
{doc_chunks}

Relevant Logs
{logs}

Rules
1. Use only the provided evidence. Do not invent facts.
2. Cite evidence inline using the format evidence:<type>:<id> where type is incident, chunk, or log.
3. Keep Root Cause to 1-2 sentences.
4. Provide Contributing Factors as an array of short strings.
5. Provide a Timeline as an ordered array of events with timestamps or relative order.
6. Provide Resolution with immediate steps and long_term steps.
7. Provide Evidence Refs as an array of evidence identifiers.
8. Provide a confidence_hint integer 0-100 estimating how well evidence supports the RCA.
9. Output must be valid JSON matching the schema.

Output JSON
{{
  "root_cause": "<string>",
  "contributing_factors": ["<string>", "..."],
  "timeline": ["<string>", "..."],
  "resolution": {{"immediate": "<string>", "long_term": "<string>"}},
  "evidence_refs": ["incident:123", "chunk:45", "log:requestId-abc"],
  "rca_draft": "<full narrative text>",
  "confidence_hint": 0
}}
"""


# -------------------------
# Helpers
# -------------------------
def redact_text(text: str) -> str:
    """
    Basic redaction to remove obvious PII before sending to external LLMs.
    Extend this function to meet your security/compliance needs.
    """
    if not text:
        return text
    # emails
    text = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "[REDACTED_EMAIL]", text)
    # AWS keys (simple pattern)
    text = re.sub(r"\bAKIA[0-9A-Z]{16}\b", "[REDACTED_AWS_KEY]", text)
    # IP addresses
    text = re.sub(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", "[REDACTED_IP]", text)
    # long hex tokens
    text = re.sub(r"\b[A-Fa-f0-9]{32,}\b", "[REDACTED_TOKEN]", text)
    return text


def extract_json_object(text: str) -> Optional[Dict[str, Any]]:
    """
    Robustly extract the first balanced JSON object from text.
    Returns parsed dict or None.
    """
    if not text or "{" not in text:
        return None
    start = text.find("{")
    stack = []
    for i in range(start, len(text)):
        ch = text[i]
        if ch == "{":
            stack.append(i)
        elif ch == "}":
            if stack:
                stack.pop()
                if not stack:
                    candidate = text[start : i + 1]
                    try:
                        return json.loads(candidate)
                    except Exception:
                        # try to clean trailing commas
                        cleaned = re.sub(r",\s*}", "}", candidate)
                        try:
                            return json.loads(cleaned)
                        except Exception:
                            return None
    return None


def safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return default


def serialize_incidents(incidents: List[Any]) -> List[Dict[str, Any]]:
    """Convert incident search tuples into JSON-safe evidence records."""
    records = []
    for incident in incidents:
        if isinstance(incident, dict):
            records.append(incident)
            continue

        values = list(incident) if isinstance(incident, (tuple, list)) else [incident]
        records.append(
            {
                "incident_id": values[0] if len(values) > 0 else None,
                "service": values[1] if len(values) > 1 else None,
                "error_log": values[2] if len(values) > 2 else None,
                "root_cause": values[3] if len(values) > 3 else None,
                "resolution": values[4] if len(values) > 4 else None,
                "distance": values[5] if len(values) > 5 else None,
            }
        )
    return records


# -------------------------
# AnalyzerAgent
# -------------------------
class AnalyzerAgent:
    """
    Analyzer Agent orchestrator.

    Instantiate with:
      - llm_client: object implementing generate(prompt, temperature, max_tokens) -> str
      - db_adapter: DBAdapter instance (provides search_incidents, search_doc_chunks_vector, search_doc_chunks_text, insert_rca)
      - floci_client: optional FlociClient instance (provides fetch_logs)
      - incident_search_pipeline: optional IncidentSearchPipeline instance (vector incident search)
    - incident_embedder: optional incident embedder instance (384 dimensions)
    - doc_embedder: optional document embedder instance (768 dimensions)
      - validator: optional ValidatorAgent instance (validate)
    """

    def __init__(
        self,
        llm_client: Any,
        db_adapter: Any,
        floci_client: Optional[Any] = None,
        incident_search_pipeline: Optional[Any] = None,
        incident_embedder: Optional[Any] = None,
        doc_embedder: Optional[Any] = None,
        validator: Optional[Any] = None,
        *,
        llm_temperature: float = 0.0,
        llm_max_tokens: int = 1400,
        log_window_minutes: int = 30,
        validator_threshold: int = 90,
    ):
        if llm_client is None:
            raise ValueError("llm_client is required")
        if db_adapter is None:
            raise ValueError("db_adapter is required")

        self.llm = llm_client
        self.db = db_adapter
        self.floci = floci_client
        self.incident_search = incident_search_pipeline
        self.incident_embedder = incident_embedder
        self.doc_embedder = doc_embedder
        self.validator = validator
        self.llm_temperature = llm_temperature
        self.llm_max_tokens = llm_max_tokens
        self.log_window_minutes = log_window_minutes
        self.validator_threshold = validator_threshold

    # -------------------------
    # Formatting helpers
    # -------------------------
    def _format_incidents(self, incidents: List[Any]) -> str:
        lines = []
        for i, inc in enumerate(incidents, start=1):
            if isinstance(inc, (tuple, list)):
                # expected tuple: incident_id, service, error_log, root_cause, resolution, distance
                try:
                    incident_id, service, error_log, root_cause, resolution, distance = inc
                except Exception:
                    # fallback mapping
                    incident_id = inc[0] if len(inc) > 0 else None
                    service = inc[1] if len(inc) > 1 else None
                    error_log = inc[2] if len(inc) > 2 else ""
                    distance = inc[-1] if len(inc) > 0 else None
                lines.append(f"Incident {i} | id:{incident_id} | service:{service} | score:{distance}\n{error_log}")
            elif isinstance(inc, dict):
                lines.append(f"Incident {i} | id:{inc.get('incident_id')} | service:{inc.get('service')} | score:{inc.get('score')}\n{inc.get('error_log')}")
            else:
                lines.append(f"Incident {i} | {str(inc)}")
        return "\n\n".join(lines)

    def _format_chunks(self, chunks: List[Dict[str, Any]]) -> str:
        lines = []
        for i, c in enumerate(chunks, start=1):
            meta = c.get("metadata") or {}
            lines.append(f"Chunk {i} | id:{c.get('chunk_id')} | service:{meta.get('service')} | score:{c.get('score')}\n{c.get('content')}")
        return "\n\n".join(lines)

    def _format_logs(self, logs: List[Dict[str, Any]]) -> str:
        lines = []
        for i, l in enumerate(logs, start=1):
            lines.append(f"Log {i} | id:{l.get('log_id')} | service:{l.get('service')} | score:{l.get('relevance_score')}\n{l.get('snippet')}")
        return "\n\n".join(lines)

    # -------------------------
    # Service selection and log fetching
    # -------------------------
    def _choose_services(self, incidents: List[Any], chunks: List[Dict[str, Any]], query: str) -> List[str]:
        scores: Dict[str, float] = {}
        # incidents
        for inc in incidents:
            svc = ""
            if isinstance(inc, (tuple, list)):
                svc = (inc[1] or "").lower() if len(inc) > 1 else ""
            elif isinstance(inc, dict):
                svc = (inc.get("service") or "").lower()
            if svc:
                scores[svc] = scores.get(svc, 0.0) + 1.0
        # chunks
        for c in chunks:
            svc = ((c.get("metadata") or {}).get("service") or "").lower()
            if svc:
                scores[svc] = scores.get(svc, 0.0) + 0.5
        # keyword boost
        for svc in ["glue", "lambda", "emr", "athena", "s3", "sqs", "sns", "iam"]:
            if re.search(r"\b" + re.escape(svc) + r"\b", query, re.I):
                scores[svc] = scores.get(svc, 0.0) + 0.3
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [r[0] for r in ranked[:3]]

    def _fetch_and_rank_logs(self, services: List[str], resource_hint: Optional[str], query: str, max_per_service: int = 10) -> List[Dict[str, Any]]:
        """
        Fetch logs from floci (or other client) and rank them by simple heuristics and optional semantic similarity.
        Returns list of snippets with fields: log_id, timestamp, snippet, service, relevance_score
        """
        snippets: List[Dict[str, Any]] = []
        if not self.floci:
            logger.debug("No floci client configured; skipping log fetch")
            return snippets

        now = datetime.utcnow()
        start = now - timedelta(minutes=self.log_window_minutes)
        end = now + timedelta(minutes=self.log_window_minutes)

        for svc in services:
            try:
                events = self.floci.fetch_logs(service=svc, resource=resource_hint, start=start, end=end, pattern="ERROR")
            except Exception as e:
                logger.warning("floci.fetch_logs failed for %s: %s", svc, e)
                events = []
            for ev in events:
                msg = ev.get("message") or ev.get("msg") or ""
                msg = redact_text(msg)
                snippets.append({
                    "log_id": ev.get("id") or ev.get("eventId"),
                    "timestamp": ev.get("timestamp"),
                    "snippet": msg[:4000],
                    "service": svc,
                    "relevance_score": 0.0,
                })

        # heuristic scoring: keyword matches + recency
        for s in snippets:
            text = s.get("snippet", "")
            kw_score = len(re.findall(r"\b(ERROR|Exception|Traceback|ImportError|ModuleNotFoundError)\b", text))
            recency_score = 0.0
            ts = s.get("timestamp")
            if ts:
                try:
                    if isinstance(ts, (int, float)):
                        dt = datetime.fromtimestamp(ts / 1000.0)
                    else:
                        dt = datetime.fromisoformat(ts)
                    age_seconds = (datetime.utcnow() - dt).total_seconds()
                    recency_score = max(0.0, 1.0 - (age_seconds / (60 * 60 * 24)))
                except Exception:
                    recency_score = 0.0
            s["relevance_score"] = float(kw_score) + recency_score

        # optional semantic boost if embedder available
        if self.incident_embedder and hasattr(self.incident_embedder, "embed_text"):
            try:
                q_emb = self.incident_embedder.embed_text(query)
                texts = [s["snippet"] for s in snippets]
                if texts:
                    # some embedder implementations return numpy arrays; ensure lists
                    txt_embs = self.incident_embedder.model.encode(texts, convert_to_numpy=True).tolist() if hasattr(self.incident_embedder, "model") else None
                    if txt_embs:
                        def cos(a, b):
                            dot = sum(x * y for x, y in zip(a, b))
                            na = math.sqrt(sum(x * x for x in a))
                            nb = math.sqrt(sum(y * y for y in b))
                            return dot / (na * nb + 1e-9)
                        for s, emb in zip(snippets, txt_embs):
                            s["relevance_score"] += float(cos(q_emb, emb)) * 2.0
            except Exception:
                logger.debug("Semantic ranking failed; continuing with heuristic scores")

        ranked = sorted(snippets, key=lambda x: x.get("relevance_score", 0.0), reverse=True)
        # limit results
        return ranked[: max_per_service * len(services) if services else 0]

    # -------------------------
    # LLM call + parsing + validation
    # -------------------------
    def _call_analyzer_llm(self, incident_query: str, incidents_text: str, chunks_text: str, logs_text: str, strict_json_only: bool = False) -> Optional[Dict[str, Any]]:
        prompt = ANALYZER_PROMPT_TEMPLATE.format(
            incident_query=incident_query,
            similar_incidents=incidents_text,
            doc_chunks=chunks_text,
            logs=logs_text,
        )
        if strict_json_only:
            prompt = prompt + "\n\nSTRICT_JSON_ONLY: Return only JSON matching the schema exactly."

        raw = self.llm.generate(prompt=prompt, temperature=self.llm_temperature, max_tokens=self.llm_max_tokens)
        parsed = extract_json_object(raw)
        return parsed

    # -------------------------
    # Public API
    # -------------------------
    @log_operation
    @handle_errors
    def generate_rca(
        self,
        incident_query: str,
        top_k_incidents: int = 5,
        top_k_chunks: int = 8,
        include_logs_on_low_confidence: bool = True,
    ) -> Dict[str, Any]:
        """
        Main entrypoint. Returns parsed RCA dict (validated where possible) and persists it.
        Steps:
          1. Incident vector search (preferred) with fallback to text search
          2. Doc chunk vector search (preferred) with fallback to text search
          3. Call LLM to generate RCA JSON
          4. Validate JSON against schema; retry once if needed
          5. If confidence low and floci available, fetch logs and re-run LLM
          6. Persist RCA via db_adapter.insert_rca
        """
        # 1) incident search
        incidents = []
        try:
            if self.incident_search:
                incidents = self.incident_search.search(incident_query, top_k=top_k_incidents)
            else:
                incidents = self.db.search_incidents(incident_query, top_k=top_k_incidents)
        except Exception as e:
            logger.warning("Incident vector search failed: %s; falling back to DB text search", e)
            incidents = self.db.search_incidents(incident_query, top_k=top_k_incidents)

        # 2) doc chunk search (vector preferred)
        chunks: List[Dict[str, Any]] = []
        try:
            if self.doc_embedder and hasattr(self.doc_embedder, "embed_text"):
                q_emb = self.doc_embedder.embed_text(incident_query)
                chunks = self.db.search_doc_chunks_vector(query_embedding=q_emb, top_k=top_k_chunks)
            else:
                chunks = self.db.search_doc_chunks_text(incident_query, top_k=top_k_chunks)
            if not chunks:
                # fallback to text search
                chunks = self.db.search_doc_chunks_text(incident_query, top_k=top_k_chunks)
        except Exception as e:
            logger.warning("Doc chunk vector search failed: %s; falling back to text search", e)
            chunks = self.db.search_doc_chunks_text(incident_query, top_k=top_k_chunks)

        # redact doc chunk content before sending to LLM
        for c in chunks:
            c["content"] = redact_text(c.get("content", ""))

        incidents_text = self._format_incidents(incidents)
        chunks_text = self._format_chunks(chunks)

        # 3) initial LLM call
        parsed = self._call_analyzer_llm(incident_query, incidents_text, chunks_text, logs_text="")
        if parsed is None:
            # retry strict JSON only once
            parsed = self._call_analyzer_llm(incident_query, incidents_text, chunks_text, logs_text="", strict_json_only=True)
            if parsed is None:
                raise RuntimeError("Analyzer LLM did not return valid JSON after retries")

        # 4) schema validation
        try:
            validate_analyzer_output(parsed)
        except AnalyzerValidationError as e:
            logger.warning("Initial Analyzer output failed schema validation: %s", e)
            # attempt one more strict retry with example schema
            example = {
                "root_cause": "string",
                "contributing_factors": ["string"],
                "timeline": ["string"],
                "resolution": {"immediate": "string", "long_term": "string"},
                "evidence_refs": ["incident:123"],
                "rca_draft": "string",
                "confidence_hint": 0,
            }
            strict_prompt = (
                ANALYZER_PROMPT_TEMPLATE
                + "\n\nSTRICT_JSON_ONLY: Return only JSON matching the schema exactly. Example output:\n"
                + json.dumps(example)
            )
            raw = self.llm.generate(prompt=strict_prompt, temperature=self.llm_temperature, max_tokens=self.llm_max_tokens)
            parsed2 = extract_json_object(raw)
            if parsed2:
                try:
                    validate_analyzer_output(parsed2)
                    parsed = parsed2
                except AnalyzerValidationError:
                    logger.warning("Strict retry also failed schema validation; keeping initial parsed output")
            else:
                logger.warning("Strict retry did not return JSON; keeping initial parsed output")

        # ensure confidence_hint exists and is int
        parsed["confidence_hint"] = safe_int(parsed.get("confidence_hint", 0), 0)

        # attach provenance
        parsed.setdefault("_provenance", {})
        parsed["_provenance"].update(
            {
                "model": getattr(self.llm, "provider", getattr(self.llm, "__class__", "unknown")),
                "timestamp": datetime.utcnow().isoformat(),
                "evidence_counts": {"incidents": len(incidents), "chunks": len(chunks), "logs": 0},
            }
        )

        # 5) if low confidence, fetch logs and re-run
        top_logs: List[Dict[str, Any]] = []
        if include_logs_on_low_confidence and parsed.get("confidence_hint", 0) < self.validator_threshold and self.floci:
            services = self._choose_services(incidents, chunks, incident_query)
            # try to extract resource hint (request id, job id, function name)
            combined_text = ""
            for inc in incidents:
                if isinstance(inc, (tuple, list)):
                    combined_text += "\n" + (inc[2] if len(inc) > 2 else "")
                elif isinstance(inc, dict):
                    combined_text += "\n" + (inc.get("error_log", "") or "")
            for c in chunks:
                combined_text += "\n" + (c.get("content", "") or "")
            m = re.search(r"(arn:aws:[\w-:\/]+|requestId[:=]\s*([A-Za-z0-9\-]+)|job[_\- ]?id[:=]\s*([A-Za-z0-9\-]+)|function[:=]\s*([A-Za-z0-9_\-]+))", combined_text, re.I)
            resource_hint = m.group(0) if m else None

            snippets = self._fetch_and_rank_logs(services, resource_hint, incident_query)
            # limit and format logs
            top_logs = snippets[:20]
            logs_text = self._format_logs(top_logs)

            # re-run LLM with logs appended
            parsed_with_logs = self._call_analyzer_llm(incident_query, incidents_text, chunks_text, logs_text, strict_json_only=True)
            if parsed_with_logs:
                try:
                    validate_analyzer_output(parsed_with_logs)
                    parsed = parsed_with_logs
                    parsed["_provenance"]["reanalysis_with_logs"] = True
                    parsed["_provenance"]["evidence_counts"]["logs"] = len(top_logs)
                except AnalyzerValidationError:
                    logger.warning("Reanalysis with logs failed schema validation; keeping previous parsed result")

        # 6) validator scoring (optional)
        if self.validator:
            try:
                v = self.validator.validate(parsed)
                parsed["_validator"] = v
            except Exception as e:
                logger.warning("Validator failed: %s", e)

        # 7) persist RCA and the evidence snapshot used by the LLM
        try:
            incident_records = serialize_incidents(incidents)
            incident_ids = [
                record["incident_id"]
                for record in incident_records
                if isinstance(record.get("incident_id"), int)
            ]
            self.db.insert_rca(
                incident_query=incident_query,
                rca=parsed,
                incident_ids=incident_ids,
                evidence={
                    "incidents": incident_records,
                    "architecture_chunks": chunks,
                    "logs": top_logs,
                },
            )
        except Exception as e:
            logger.warning("Failed to persist RCA: %s", e)

        return parsed


# -------------------------
# Example usage (for local dev)
# -------------------------
if __name__ == "__main__":
    # Local smoke test. Database and embedding services must be configured.
    class MockLLM:
        provider = "mock"

        def generate(self, prompt: str, temperature: float = 0.0, max_tokens: int = 1200) -> str:
            return json.dumps({
                "root_cause": "Missing pyarrow dependency in Glue job runtime causing parquet serialization failure.",
                "contributing_factors": ["bootstrap script not updated", "dependency pin mismatch"],
                "timeline": ["Job started", "ImportError at T+12s", "Job failed and retried"],
                "resolution": {"immediate": "Add pyarrow to job dependencies and re-run job.", "long_term": "Add dependency checks in CI and preflight for Glue jobs."},
                "evidence_refs": ["incident:101", "chunk:11"],
                "rca_draft": "The Glue job failed due to ModuleNotFoundError for pyarrow. Evidence: incident:101 shows the ImportError; chunk:11 documents that Glue jobs require pyarrow for parquet.",
                "confidence_hint": 95
            })

    class MockFloci:
        def fetch_logs(self, service, resource, start, end, pattern):
            return [{"id": "log-1", "timestamp": datetime.utcnow().isoformat(), "message": "ImportError: No module named pyarrow at line 23"}]

    llm = MockLLM()
    floci = MockFloci()
    db_adapter = AnalyzerStore()
    incident_embedder = IncidentEmbedder()
    incident_search = IncidentSearchPipeline(embedder=incident_embedder)

    agent = AnalyzerAgent(
        llm_client=llm,
        db_adapter=db_adapter,
        floci_client=floci,
        incident_search_pipeline=incident_search,
        incident_embedder=incident_embedder,
    )

    # Example query
    try:
        rca = agent.generate_rca("Glue job failing with ModuleNotFoundError pyarrow")
        print(json.dumps(rca, indent=2))
    except Exception as e:
        logger.error("Example run failed: %s", e)
    finally:
        incident_search.cleanup()
        db_adapter.close_pool()
