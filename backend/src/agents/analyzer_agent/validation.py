"""Validation and JSON extraction for analyzer LLM responses."""

from __future__ import annotations

import json
from typing import Any, Dict, List

from .models import REQUIRED_RCA_FIELDS


class AnalyzerValidationError(ValueError):
    """Raised when an LLM response does not match the RCA contract."""


def extract_json_object(text: str) -> Dict[str, Any]:
    """Extract the first balanced JSON object from an LLM response."""
    if not text or "{" not in text:
        raise AnalyzerValidationError(
            "LLM response does not contain a JSON object"
        )

    start = text.find("{")
    depth = 0

    for index in range(start, len(text)):
        character = text[index]

        if character == "{":
            depth += 1
        elif character == "}":
            depth -= 1

            if depth == 0:
                try:
                    result = json.loads(text[start:index + 1])
                except json.JSONDecodeError as exc:
                    raise AnalyzerValidationError(
                        "LLM returned invalid JSON"
                    ) from exc

                if not isinstance(result, dict):
                    raise AnalyzerValidationError(
                        "LLM JSON response must be an object"
                    )

                return result

    raise AnalyzerValidationError(
        "LLM response contains an incomplete JSON object"
    )


def _unwrap_single_candidate(result: Dict[str, Any]) -> Dict[str, Any]:
    """Return the first RCA candidate from a wrapped response."""
    if "candidates" not in result:
        return result

    candidates = result["candidates"]

    if not isinstance(candidates, list) or not candidates:
        raise AnalyzerValidationError(
            "candidates must be a non-empty list"
        )

    first_candidate = candidates[0]

    if not isinstance(first_candidate, dict):
        raise AnalyzerValidationError(
            "The first RCA candidate must be a JSON object"
        )

    return first_candidate


def validate_rca(result: Dict[str, Any]) -> Dict[str, Any]:
    """Validate one RCA object."""
    result = _unwrap_single_candidate(result)

    # print(
    #     "Validating RCA result:\n",
    #     json.dumps(result, indent=2, ensure_ascii=False, default=str),
    # )

    missing = [field for field in REQUIRED_RCA_FIELDS if field not in result]

    if missing:
        raise AnalyzerValidationError(
            f"Missing RCA fields: {', '.join(missing)}"
        )

    for field in ("root_cause", "rca_draft"):
        if not isinstance(result[field], str):
            raise AnalyzerValidationError(f"{field} must be a string")

    for field in ("contributing_factors", "timeline", "evidence_refs"):
        if not isinstance(result[field], list) or not all(
            isinstance(item, str) for item in result[field]
        ):
            raise AnalyzerValidationError(
                f"{field} must be a list of strings"
            )

    resolution = result["resolution"]

    if not isinstance(resolution, dict) or any(
        not isinstance(resolution.get(field), str)
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

    return result


def validate_candidates(
    candidates: List[Dict[str, Any]] | Dict[str, Any],
    expected: int = 2,
) -> List[Dict[str, Any]]:
    """Validate every RCA candidate."""
    if isinstance(candidates, dict):
        candidates = candidates.get("candidates")

    if not isinstance(candidates, list):
        raise AnalyzerValidationError(
            "candidates must be a list"
        )

    if len(candidates) != expected:
        raise AnalyzerValidationError(
            f"Expected exactly {expected} RCA candidates, "
            f"received {len(candidates)}"
        )

    validated_candidates: List[Dict[str, Any]] = []

    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            raise AnalyzerValidationError(
                f"Candidate {index} must be a JSON object"
            )

        validated_candidates.append(validate_rca(candidate))

    return validated_candidates