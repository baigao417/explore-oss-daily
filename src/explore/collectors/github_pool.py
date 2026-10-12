from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import datetime

from explore.http_identity import resolve_user_agent
from explore.oss_models import ProjectCandidate


DEFAULT_OSS_QUERIES = [
    "topic:llm stars:>50",
    "topic:ai-agent stars:>20",
    "topic:rag stars:>20",
    "topic:mcp stars:>10",
    "topic:workflow stars:>20",
    "topic:automation stars:>50",
    "topic:eval stars:>20",
    "topic:agent-framework stars:>10",
    "topic:ai-coding stars:>20",
    "topic:code-review stars:>10",
    "topic:developer-tools stars:>50",
    "topic:knowledge-base stars:>20",
    "topic:note-taking stars:>20",
    "topic:self-hosted stars:>50",
    "topic:tts stars:>10",
    "topic:speech-recognition stars:>10",
    "topic:data-pipeline stars:>20",
    "topic:web-scraping stars:>20",
    "topic:observability stars:>50",
]


def rotate_queries(queries: list[str] | None = None, *, offset: int = 0, budget: int | None = None) -> list[str]:
    """Return a deterministic rotating query window within a per-run budget."""

    values = list(queries or DEFAULT_OSS_QUERIES)
    if not values:
        return []
    start = int(offset) % len(values)
    rotated = values[start:] + values[:start]
    return rotated if budget is None else rotated[: max(0, int(budget))]


def day_of_year_query_offset(when: str, query_count: int) -> int:
    """Return the deterministic production rotation offset for an ISO timestamp."""

    if query_count <= 0:
        return 0
    parsed = datetime.fromisoformat(str(when).replace("Z", "+00:00"))
    return parsed.timetuple().tm_yday % query_count


def _request_json(url: str, *, timeout: int = 30) -> dict:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": resolve_user_agent(),
    }
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def collect_github_project_pool(
    queries: list[str] | None = None,
    *,
    per_query_limit: int = 60,
    timeout: int = 30,
    query_budget: int | None = None,
    query_offset: int = 0,
) -> tuple[list[ProjectCandidate], list[str]]:
    """Collect a broad OSS candidate pool from GitHub Search.

    Uses only public repository metadata and degrades per query. GitHub caps search
    pages at 100 results, so the MVP keeps one request per query to avoid rate
    pressure and secret/token requirements.
    """

    items: dict[str, ProjectCandidate] = {}
    errors: list[str] = []
    limit = max(1, min(int(per_query_limit), 100))

    for query in rotate_queries(queries, offset=query_offset, budget=query_budget):
        encoded = urllib.parse.quote(query)
        url = (
            "https://api.github.com/search/repositories"
            f"?q={encoded}&sort=updated&order=desc&per_page={limit}"
        )
        try:
            payload = _request_json(url, timeout=timeout)
        except Exception as exc:  # noqa: BLE001 - collector should degrade per query
            errors.append(f"github-project-pool: {type(exc).__name__}")
            continue

        for repo in payload.get("items", [])[:limit]:
            html_url = repo.get("html_url") or ""
            full_name = repo.get("full_name") or repo.get("name") or "(unknown repo)"
            if not html_url:
                continue
            candidate = ProjectCandidate(
                full_name=full_name,
                url=html_url,
                description=repo.get("description") or "",
                language=repo.get("language") or "unknown",
                topics=list(repo.get("topics") or []),
                stars=int(repo.get("stargazers_count") or 0),
                forks=int(repo.get("forks_count") or 0),
                open_issues=int(repo.get("open_issues_count") or 0),
                pushed_at=repo.get("pushed_at"),
                updated_at=repo.get("updated_at"),
                default_branch=repo.get("default_branch") or "",
                source_query=query,
                raw={
                    "archived": bool(repo.get("archived")),
                    "disabled": bool(repo.get("disabled")),
                    "license": (repo.get("license") or {}).get("spdx_id"),
                    "size": repo.get("size"),
                },
            )
            # Keep first query as source, but merge topics if duplicated.
            if candidate.id in items:
                merged_topics = sorted(set(items[candidate.id].topics) | set(candidate.topics))
                existing = items[candidate.id]
                items[candidate.id] = ProjectCandidate(
                    full_name=existing.full_name,
                    url=existing.url,
                    description=existing.description,
                    language=existing.language,
                    topics=merged_topics,
                    stars=existing.stars,
                    forks=existing.forks,
                    open_issues=existing.open_issues,
                    pushed_at=existing.pushed_at,
                    updated_at=existing.updated_at,
                    default_branch=existing.default_branch,
                    source_query=existing.source_query,
                    raw=existing.raw,
                )
            else:
                items[candidate.id] = candidate

    return list(items.values()), errors
