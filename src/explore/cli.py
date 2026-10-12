from __future__ import annotations

import argparse
import json
import sys
from dataclasses import fields
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

from explore.collectors.github_pool import collect_github_project_pool
from explore.config import load_object, load_profile, load_queries
from explore.feedback import append_feedback, feedback_summary
from explore.oss_models import ProjectCandidate
from explore.processors.oss import rank_projects
from explore.reports.oss_daily import write_oss_daily_report


def load_candidates(path: Path) -> list[ProjectCandidate]:
    payload = load_object(path)
    rows = payload.get("projects")
    if not isinstance(rows, list):
        raise ValueError("candidate file must contain a projects list")
    accepted = {}
    known = {field.name for field in fields(ProjectCandidate)}
    for row in rows:
        if not isinstance(row, dict) or set(row) - known:
            raise ValueError("candidate has unknown fields or is not an object")
        project = ProjectCandidate(**row)
        if not isinstance(project.full_name, str) or not project.full_name.strip():
            raise ValueError("candidate full_name must be non-empty")
        if not isinstance(project.url, str):
            raise ValueError("candidate url must be a string")
        parsed = urlparse(project.url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("candidate URLs must use HTTPS without credentials")
        for key in ("description", "language", "default_branch", "source_query"):
            if not isinstance(getattr(project, key), str):
                raise ValueError(f"candidate {key} must be a string")
        if not isinstance(project.topics, list) or not all(isinstance(x, str) for x in project.topics):
            raise ValueError("candidate topics must be a list of strings")
        for key in ("stars", "forks", "open_issues"):
            value = getattr(project, key)
            if type(value) is not int or value < 0:
                raise ValueError(f"candidate {key} must be a non-negative integer")
        for key in ("pushed_at", "updated_at"):
            value = getattr(project, key)
            if value is not None and not isinstance(value, str):
                raise ValueError(f"candidate {key} must be an ISO date string")
        if not isinstance(project.raw, dict):
            raise ValueError("candidate raw must be an object")
        # Keep only metadata used by the ranker, not arbitrary imported payloads.
        safe = dict(row)
        safe["raw"] = {key: project.raw[key] for key in ("archived", "disabled", "license", "size")
                       if key in project.raw}
        accepted.setdefault(project.full_name.lower(), ProjectCandidate(**safe))
    return list(accepted.values())


def run_daily(args: argparse.Namespace) -> int:
    issue_date = date.fromisoformat(args.date).isoformat()
    profile = load_profile(Path(args.profile))
    errors = []
    if args.online:
        projects, errors = collect_github_project_pool(
            load_queries(Path(args.sources)), per_query_limit=args.per_query_limit,
        )
    else:
        projects = load_candidates(Path(args.candidates))
    synthetic = not args.online and load_object(Path(args.candidates)).get("synthetic") is True
    if not projects:
        print("No recommendation: candidate pool is empty", file=sys.stderr)
        return 1
    output = Path(args.output)
    ranked = rank_projects(projects, set(profile["terms"]), feedback_summary(output),
                           binding_hints=profile["binding_hints"])
    report = write_oss_daily_report(ranked, profile=profile, errors=errors,
                                    root=output, issue_date=issue_date,
                                    synthetic=synthetic, online=args.online)
    pool = output / "data" / "project_pool.json"
    pool.parent.mkdir(parents=True, exist_ok=True)
    pool.write_text(json.dumps({"schema_version": "1.0", "items": ranked},
                               ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"recommended={ranked[0]['project']['full_name']} candidates={len(ranked)}")
    print(f"report={report}")
    if errors:
        print(f"collection_warnings={len(errors)}", file=sys.stderr)
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="explore", description="One daily OSS recommendation")
    commands = result.add_subparsers(dest="command", required=True)
    daily = commands.add_parser("daily", help="Rank offline metadata or explicitly collect public metadata")
    mode = daily.add_mutually_exclusive_group()
    mode.add_argument("--online", action="store_true", help="Enable anonymous GitHub public API requests")
    mode.add_argument("--candidates", default="examples/projects.json", help="Local candidate JSON")
    daily.add_argument("--profile", default="config/profile.example.json")
    daily.add_argument("--sources", default="config/sources.example.json")
    daily.add_argument("--per-query-limit", type=int, choices=range(1, 101), default=10, metavar="1..100")
    daily.add_argument("--date", default=date.today().isoformat())
    daily.add_argument("--output", default="outputs", help="Private state root; ignored by Git")
    feedback = commands.add_parser("feedback", help="Record a local 1-10 score")
    feedback.add_argument("--project", required=True)
    feedback.add_argument("--score", type=int, choices=range(1, 11), required=True)
    feedback.add_argument("--output", default="outputs")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "daily":
            return run_daily(args)
        entry = append_feedback(args.project, args.score, root=Path(args.output))
        print(f"feedback_recorded score={entry['score']}")
        return 0
    except (OSError, ValueError, TypeError, OverflowError) as exc:
        # Input/config exceptions may contain sensitive values; do not echo them.
        print(f"Invalid input or file access failure ({type(exc).__name__})", file=sys.stderr)
        return 2
