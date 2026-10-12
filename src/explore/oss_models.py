from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from explore.models import stable_item_id


@dataclass(frozen=True)
class ProjectCandidate:
    full_name: str
    url: str
    description: str = ""
    language: str = "unknown"
    topics: list[str] = field(default_factory=list)
    stars: int = 0
    forks: int = 0
    open_issues: int = 0
    pushed_at: str | None = None
    updated_at: str | None = None
    default_branch: str = ""
    source_query: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def id(self) -> str:
        return stable_item_id(self.full_name, self.url)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "full_name": self.full_name,
            "url": self.url,
            "description": self.description,
            "language": self.language,
            "topics": self.topics,
            "stars": self.stars,
            "forks": self.forks,
            "open_issues": self.open_issues,
            "pushed_at": self.pushed_at,
            "updated_at": self.updated_at,
            "default_branch": self.default_branch,
            "source_query": self.source_query,
            "raw": self.raw,
        }
