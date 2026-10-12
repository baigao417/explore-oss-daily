from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from explore.config import PROJECT_ROOT


def decision_from_score(score: int) -> str:
    if score >= 9:
        return "poc_or_spec"
    if score >= 7:
        return "watch_or_backlog"
    if score >= 5:
        return "downrank_similar"
    if score >= 3:
        return "avoid_similar"
    return "strong_avoid"


def normalize_score(score: int) -> int:
    value = int(score)
    if value < 1 or value > 10:
        raise ValueError("score must be between 1 and 10")
    return value


def _load_pool_project(project: str, root: Path = PROJECT_ROOT / "outputs") -> dict[str, Any]:
    pool_path = root / "data" / "project_pool.json"
    if not pool_path.exists():
        return {}
    try:
        payload = json.loads(pool_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    needle = project.lower()
    for row in payload.get("items", []):
        item = row.get("project", {})
        full_name = str(item.get("full_name", ""))
        url = str(item.get("url", ""))
        if needle in {full_name.lower(), url.lower()}:
            return {"project": item, "score_snapshot": row.get("score", {})}
    return {}


def append_feedback(
    project: str,
    score: int,
    *,
    note: str = "",
    root: Path = PROJECT_ROOT / "outputs",
    dry_run: bool = False,
) -> dict[str, Any]:
    normalized = normalize_score(score)
    matched = _load_pool_project(project, root=root)
    project_payload = matched.get("project", {})
    full_name = project_payload.get("full_name") or project
    entry = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "project": full_name,
        "input_project": project,
        "score": normalized,
        "decision": decision_from_score(normalized),
        "note": note,
        "project_snapshot": project_payload,
        "score_snapshot": matched.get("score_snapshot", {}),
    }
    if dry_run:
        entry["dry_run"] = True
        return entry
    path = root / "feedback" / "oss_feedback.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
    return entry


def load_feedback_entries(root: Path = PROJECT_ROOT / "outputs") -> list[dict[str, Any]]:
    path = root / "feedback" / "oss_feedback.jsonl"
    if not path.exists():
        return []
    entries: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
            if isinstance(entry, dict):
                entries.append(entry)
        except json.JSONDecodeError:
            continue
    return entries


@dataclass(frozen=True)
class FeedbackSummary:
    by_project: dict[str, float]
    by_category: dict[str, float]
    by_term: dict[str, float]
    count: int


def _avg(values: list[int]) -> float:
    return sum(values) / len(values) if values else 0.0


def feedback_summary(root: Path = PROJECT_ROOT / "outputs") -> FeedbackSummary:
    entries = load_feedback_entries(root)
    project_scores: dict[str, list[int]] = {}
    category_scores: dict[str, list[int]] = {}
    term_scores: dict[str, list[int]] = {}

    for entry in entries:
        try:
            score = normalize_score(int(entry.get("score")))
        except (TypeError, ValueError):
            continue
        project = str(entry.get("project") or "").lower()
        if project:
            project_scores.setdefault(project, []).append(score)
        snapshot = entry.get("score_snapshot") or {}
        category = str(snapshot.get("category") or "").lower()
        if category:
            category_scores.setdefault(category, []).append(score)
        project_snapshot = entry.get("project_snapshot") or {}
        terms = set(str(t).lower() for t in project_snapshot.get("topics", []) if t)
        source_query = str(project_snapshot.get("source_query") or "").lower()
        for raw in source_query.replace(":", " ").replace(">", " ").split():
            if raw and not raw.isdigit() and raw != "stars":
                terms.add(raw)
        for term in terms:
            term_scores.setdefault(term, []).append(score)

    return FeedbackSummary(
        by_project={key: _avg(values) for key, values in project_scores.items()},
        by_category={key: _avg(values) for key, values in category_scores.items()},
        by_term={key: _avg(values) for key, values in term_scores.items()},
        count=len(entries),
    )
