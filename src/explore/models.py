from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any


def stable_item_id(title: str, url: str | None) -> str:
    key = f"{url or ''}\n{title}".strip().encode("utf-8")
    return hashlib.sha256(key).hexdigest()[:16]


@dataclass(frozen=True)
class Item:
    source_type: str
    source_name: str
    title: str
    url: str | None = None
    content: str = ""
    published_at: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def id(self) -> str:
        return stable_item_id(self.title, self.url)

    def to_db_tuple(self) -> tuple[str, str, str, str, str | None, str, str | None, str]:
        return (
            self.id,
            self.source_type,
            self.source_name,
            self.title,
            self.url,
            self.content,
            self.published_at,
            json.dumps(self.raw, ensure_ascii=False, sort_keys=True),
        )
