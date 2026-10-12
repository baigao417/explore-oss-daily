from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("configuration must be a JSON object")
    return payload


def _strings(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(x, str) and x.strip() for x in value):
        raise ValueError(f"{field} must be a list of non-empty strings")
    return [x.strip() for x in value]


def load_profile(path: Path) -> dict[str, Any]:
    payload = load_object(path)
    if payload.get("schema_version") != "1.0":
        raise ValueError("profile schema_version must be 1.0")
    terms = {x.lower() for x in _strings(payload.get("terms", []), "terms")}
    hints = payload.get("binding_hints", {})
    if not isinstance(hints, dict) or not all(
        isinstance(k, str) and k.strip() and isinstance(v, str) and v.strip()
        for k, v in hints.items()
    ):
        raise ValueError("binding_hints must map non-empty terms to labels")
    projects = payload.get("projects", [])
    if not isinstance(projects, list):
        raise ValueError("projects must be a list")
    normalized = []
    for project in projects:
        if not isinstance(project, dict):
            raise ValueError("profile projects must be objects")
        for key in ("name", "need"):
            if not isinstance(project.get(key), str) or not project[key].strip():
                raise ValueError(f"profile project {key} must be non-empty")
        project_terms = _strings(project.get("terms", []), "project terms")
        normalized.append({"name": project["name"], "need": project["need"],
                           "terms": [x.lower() for x in project_terms]})
        terms.update(x.lower() for x in project_terms)
    return {"schema_version": "1.0", "terms": sorted(terms),
            "binding_hints": {k.lower(): v for k, v in hints.items()},
            "projects": normalized}


def load_queries(path: Path) -> list[str]:
    payload = load_object(path)
    queries = _strings(payload.get("github_queries", []), "github_queries")
    if not queries or len(queries) > 10:
        raise ValueError("github_queries must contain between 1 and 10 queries")
    return queries
