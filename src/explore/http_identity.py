from __future__ import annotations

import os
from collections.abc import Mapping


HTTP_USER_AGENT_ENV = "EXPLORE_HTTP_USER_AGENT"
DEFAULT_HTTP_USER_AGENT = "Explore/0.1 (local evidence collector; non-browser client)"

_BROWSER_MARKERS = (
    "mozilla/",
    "chrome/",
    "chromium/",
    "headlesschrome",
    "safari/",
    "edg/",
    "firefox/",
)
_SAMPLE_MARKERS = (
    "your-app/",
    "you@example.com",
)


def validate_user_agent(value: str) -> str:
    user_agent = str(value or "").strip()
    if not user_agent:
        raise ValueError("HTTP User-Agent must be non-empty")
    lowered = user_agent.lower()
    if any(marker in lowered for marker in _BROWSER_MARKERS):
        raise ValueError("HTTP User-Agent must identify Explore as a non-browser client")
    if any(marker in lowered for marker in _SAMPLE_MARKERS):
        raise ValueError("HTTP User-Agent must not keep example application or contact values")
    return user_agent


def resolve_user_agent(
    configured: str | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> str:
    environment = environ if environ is not None else os.environ
    candidate = configured or environment.get(HTTP_USER_AGENT_ENV) or DEFAULT_HTTP_USER_AGENT
    return validate_user_agent(candidate)
