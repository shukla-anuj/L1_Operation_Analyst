"""Prompts used by the RCA generation nodes."""

import json
from typing import Any, Dict, List


RCA_SCHEMA = {
    "root_cause": "string",
    "contributing_factors": ["string"],
    "timeline": ["string"],
    "resolution": {"immediate": "string", "long_term": "string"},
    "evidence_refs": ["incident:123", "chunk:45", "log:abc"],
    "rca_draft": "string",
    "confidence_hint": 0,
}


def job_extraction_prompt(query: str) -> str:
  return f"""Extract the failed job name from this incident trace.

Return JSON only. Return the exact job name when it is explicitly present.
Do not treat Spark classes, Java classes, stages, task IDs, or exception names
as the job name. Return null when no job name is present.

Incident trace:
{query}

Return exactly:
{{"failed_job_name": "job-name-or-null"}}
"""


def service_extraction_prompt(
    query: str,
    support_manual_entries: List[Dict[str, Any]] | None = None,
) -> str:
    manual_entries = support_manual_entries or []

    return f"""You are an incident service-discovery analyst.

Identify every AWS or application service involved in the incident.

Use both evidence sources:

1. Incident stack trace and error message
2. Application Support Manual job-to-service mappings

The Application Support Manual is authoritative for mapping a failed job name
to its owning primary AWS service. Use stack-trace package names, AWS resource
names, error messages, and framework names to identify additional supporting
services.

Rules:
- Return JSON only.
- Do not invent services, jobs, resources, or mappings.
- Match the failed job name against the Application Support Manual first.
- If the job name maps to a primary AWS service, include that service even if
  the stack trace only contains framework or Java package names.
- Use stack-trace evidence to identify supporting services.
- Include a service only when supported by the incident trace or manual.
- Do not treat a generic technology name as an AWS service unless the evidence
  supports that relationship.
- Preserve the exact failed job name and resource name when available.
- Score each service from 0.0 to 1.0:
  - 1.0: exact job-name match in the manual and direct stack-trace evidence
  - 0.8-0.99: exact job-name match in the manual
  - 0.6-0.79: strong stack-trace or resource evidence
  - 0.3-0.59: indirect but plausible evidence
  - below 0.3: do not include the service
- Mark the evidence source for every service:
  - "manual"
  - "stack_trace"
  - "manual_and_stack_trace"
- If no service can be identified, return an empty services array.
- Do not fail because the service list is empty.

Incident stack trace:
{query}

Application Support Manual job-to-service mappings:
{json.dumps(manual_entries, default=str, indent=2)}

Return exactly this JSON structure:
{{
  "failed_job_name": "job-name-or-null",
  "services": [
    {{
      "service": "glue",
      "resource": "job-name-or-null",
      "score": 0.0,
      "evidence_source": "manual_and_stack_trace",
      "evidence": [
        "Exact job-name mapping from support manual",
        "Relevant stack-trace evidence"
      ]
    }}
  ]
}}
"""


def evidence_prompt(query: str, incidents: List[Dict[str, Any]], chunks: List[Dict[str, Any]], logs: List[Dict[str, Any]], count: int = 1) -> str:
    return f"""You are an evidence-based incident RCA analyst.
Use only the supplied evidence. Never invent services, timestamps, causes, or fixes.
Return JSON only. Every evidence_refs item must identify supplied evidence as incident:<id>, chunk:<id>, or log:<id>.
Produce exactly {count} distinct RCA candidate(s). Candidates must represent materially different hypotheses when evidence permits.
Each confidence_hint must be an integer from 0 to 100 and must reflect evidence strength, not writing quality.

Incident query:
{query}

Similar incidents:
{json.dumps(incidents, default=str)}

Architecture chunks:
{json.dumps(chunks, default=str)}

Service logs:
{json.dumps(logs, default=str)}

JSON shape:
{json.dumps(RCA_SCHEMA)}
For multiple candidates return: {{"candidates": [{json.dumps(RCA_SCHEMA)}]}}
"""
