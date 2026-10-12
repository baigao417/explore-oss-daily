from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from explore.contracts import compat_score
from explore.feedback import FeedbackSummary
from explore.oss_models import ProjectCandidate

CATEGORY_RULES = [
    ("AI / Agent 赛道", {"agent", "ai-agent", "agents", "llm", "mcp", "tool-use", "workflow"}),
    ("AI 领域实操案例", {"ai", "llm", "automation", "demo", "app", "chatbot"}),
    ("数据与检索", {"rag", "retrieval", "search", "database", "data"}),
    ("开发者工具", {"cli", "sdk", "api", "runtime", "server", "framework"}),
    ("跨领域通用方法论", {"eval", "benchmark", "harness", "workflow", "knowledge", "docs"}),
]

def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _hits(project: ProjectCandidate) -> set[str]:
    text = " ".join([project.full_name, project.description, project.language, " ".join(project.topics)]).lower()
    tokens: set[str] = set()
    for raw in text.replace("/", " ").replace("-", " ").replace("_", " ").split():
        if raw:
            tokens.add(raw.strip())
    tokens.update(topic.lower() for topic in project.topics)
    return tokens


def classify_project(project: ProjectCandidate) -> str:
    hits = _hits(project)
    best_category = "其他 AI 基础设施"
    best_count = 0
    for category, keywords in CATEGORY_RULES:
        count = len(hits & keywords)
        if count > best_count:
            best_category = category
            best_count = count
    return best_category


def _feedback_adjustment(project: ProjectCandidate, category: str, hits: set[str], feedback: FeedbackSummary | None) -> float:
    if feedback is None or feedback.count == 0:
        return 0.0
    project_score = feedback.by_project.get(project.full_name.lower())
    if project_score is not None:
        return round((project_score - 5.5) * 0.35, 2)
    category_score = feedback.by_category.get(category.lower())
    term_scores = [feedback.by_term[term] for term in sorted(hits) if term in feedback.by_term]
    signals: list[float] = []
    if category_score is not None:
        signals.append(category_score)
    signals.extend(term_scores[:5])
    if not signals:
        return 0.0
    return round(((sum(signals) / len(signals)) - 5.5) * 0.18, 2)


def score_project(
    project: ProjectCandidate,
    workstation_terms: set[str] | None = None,
    feedback: FeedbackSummary | None = None,
    *,
    binding_hints: dict[str, str] | None = None,
) -> dict[str, Any]:
    hits = _hits(project)
    workstation_terms = workstation_terms or set()
    binding_hints = binding_hints or {}
    ai_terms = {"ai", "llm", "agent", "agents", "rag", "mcp", "prompt", "workflow", "automation", "eval"}
    production_terms = {"server", "framework", "platform", "sdk", "cli", "api", "runtime", "docs", "examples"}
    noise_terms = {"tutorial", "toy", "demo-only", "awesome", "list", "paper-list"}

    relevance = min(10, 3 + len(hits & ai_terms) * 2)
    production_value = min(10, 4 + len(hits & production_terms) * 2 + (2 if project.stars >= 1000 else 0))

    pushed = _parse_dt(project.pushed_at or project.updated_at)
    if pushed:
        age_days = max(0, (datetime.now(timezone.utc) - pushed).days)
        activity = 10 if age_days <= 14 else 8 if age_days <= 45 else 6 if age_days <= 120 else 3
    else:
        activity = 5

    momentum = 10 if project.stars >= 20_000 else 9 if project.stars >= 5_000 else 8 if project.stars >= 1_000 else 6 if project.stars >= 100 else 4
    readme_quality = 8 if len(project.description) >= 80 else 6 if project.description else 3
    architecture_learnability = min(10, 4 + len(hits & {"framework", "sdk", "runtime", "workflow", "eval", "mcp", "harness"}) * 2)
    workstation_fit = min(10, 4 + len(hits & set(binding_hints)) * 2 + len(hits & workstation_terms))
    noise_penalty = min(5, len(hits & noise_terms) * 2 + (2 if project.raw.get("archived") else 0))

    category = classify_project(project)
    feedback_adjustment = _feedback_adjustment(project, category, hits, feedback)
    total = round(
        relevance * 0.18
        + production_value * 0.16
        + activity * 0.14
        + momentum * 0.12
        + readme_quality * 0.10
        + architecture_learnability * 0.15
        + workstation_fit * 0.15
        - noise_penalty * 0.12
        + feedback_adjustment,
        2,
    )
    total = max(0.0, min(10.0, total))
    grade = "S" if total >= 8.6 else "A" if total >= 7.6 else "B" if total >= 6.4 else "C" if total >= 5.2 else "D"
    return compat_score({
        "category": category,
        "grade": grade,
        "total": total,
        "relevance": relevance,
        "production_value": production_value,
        "activity": activity,
        "momentum": momentum,
        "readme_quality": readme_quality,
        "architecture_learnability": architecture_learnability,
        "workstation_fit": workstation_fit,
        "noise_penalty": noise_penalty,
        "feedback_adjustment": feedback_adjustment,
        "feedback_count": feedback.count if feedback else 0,
        "binding_hints": sorted({label for key, label in binding_hints.items() if key in hits})[:5],
    })


def rank_projects(
    projects: list[ProjectCandidate],
    workstation_terms: set[str] | None = None,
    feedback: FeedbackSummary | None = None,
    *,
    binding_hints: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    ranked = []
    for project in projects:
        ranked.append({"project": project.to_dict(), "score": score_project(
            project, workstation_terms, feedback, binding_hints=binding_hints,
        )})
    return sorted(ranked, key=lambda row: (-row["score"]["total"], row["project"]["full_name"].lower()))
