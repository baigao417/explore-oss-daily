from __future__ import annotations

from typing import Any, Mapping


SCHEMA_VERSION = "1.0"


def tier_from_legacy_grade(grade: str | None) -> str:
    """Return the documented projection fallback for an old S/A/B/C/D grade."""

    return {
        "S": "T1",
        "A": "T2",
        "B": "T3",
        "C": "T3",
        "D": "T4",
    }.get(str(grade or "").upper(), "Unjudged")


def compat_score(score: Mapping[str, Any]) -> dict[str, Any]:
    """Copy a legacy score and add non-breaking V1 fields.

    A legacy row is not promoted to evidence-backed merely because it has a high
    grade.  The effective tier fallback is kept separate so callers can route old
    rows without mutating their historical meaning.
    """

    result = dict(score)
    result.setdefault("schema_version", SCHEMA_VERSION)
    result.setdefault("evidence_mode", "metadata_only")
    result.setdefault("recommendation_status", "shortlisted")
    result.setdefault("tier", "Unjudged")
    result.setdefault("tier_source", "evidence_gate")
    result.setdefault("legacy_tier_fallback", tier_from_legacy_grade(result.get("grade")))
    return result
