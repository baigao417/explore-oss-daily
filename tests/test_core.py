from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from explore.cli import load_candidates, main, parser
from explore.collectors.github_pool import (
    _request_json, collect_github_project_pool, day_of_year_query_offset, rotate_queries,
)
from explore.config import load_profile, load_queries
from explore.feedback import (
    append_feedback, decision_from_score, feedback_summary, normalize_score,
)
from explore.http_identity import validate_user_agent
from explore.models import stable_item_id
from explore.oss_models import ProjectCandidate
from explore.processors.oss import rank_projects, score_project

ROOT = Path(__file__).resolve().parents[1]


class LocalTest(unittest.TestCase):
    def setUp(self):
        base = Path(os.environ.get("EXPLORE_TEST_TMPDIR", ROOT / "outputs" / "test-tmp"))
        base.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix="case-", dir=base)
        self.addCleanup(self.temporary.cleanup)
        self.output = Path(self.temporary.name)

    def write_json(self, payload, name="input.json"):
        path = self.output / name
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def invoke(self, args):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return main(args)

    def daily_args(self):
        return ["daily", "--profile", str(ROOT / "config/profile.example.json"),
                "--candidates", str(ROOT / "examples/projects.json"),
                "--output", str(self.output), "--date", "2026-01-05"]


class ProfileTests(LocalTest):
    def test_fictional_profile_loads_without_scanning(self):
        profile = load_profile(ROOT / "config/profile.example.json")
        self.assertEqual(len(profile["projects"]), 2)
        self.assertIn("runtime", profile["terms"])

    def test_profile_terms_are_case_insensitive(self):
        path = self.write_json({"schema_version": "1.0", "terms": ["RAG"],
                                "binding_hints": {"RAG": "Search"}})
        self.assertEqual(load_profile(path)["terms"], ["rag"])
        self.assertEqual(load_profile(path)["binding_hints"], {"rag": "Search"})

    def test_rejects_profile_version(self):
        path = self.write_json({"schema_version": "2.0"})
        with self.assertRaises(ValueError):
            load_profile(path)

    def test_rejects_profile_terms_type(self):
        path = self.write_json({"schema_version": "1.0", "terms": "rag"})
        with self.assertRaises(ValueError):
            load_profile(path)

    def test_rejects_missing_project_need(self):
        path = self.write_json({"schema_version": "1.0", "projects": [{"name": "Example"}]})
        with self.assertRaises(ValueError):
            load_profile(path)

    def test_sources_are_example_queries(self):
        self.assertEqual(len(load_queries(ROOT / "config/sources.example.json")), 3)

    def test_sources_reject_empty_and_unbounded_queries(self):
        for queries in ([], ["topic:rag"] * 11):
            with self.subTest(queries=len(queries)), self.assertRaises(ValueError):
                load_queries(self.write_json({"github_queries": queries}))


class RankingTests(LocalTest):
    def project(self, **extra):
        return ProjectCandidate(full_name="fictional/search", url="https://example.invalid/search",
                                topics=["rag", "eval"], **extra)

    def test_stable_id_is_repeatable(self):
        self.assertEqual(stable_item_id("a", "https://example.invalid"),
                         stable_item_id("a", "https://example.invalid"))
        self.assertNotEqual(stable_item_id("a", None), stable_item_id("b", None))

    def test_profile_changes_fit_and_bindings(self):
        project = self.project()
        plain = score_project(project)
        matched = score_project(project, {"rag"}, binding_hints={"rag": "Search"})
        self.assertGreater(matched["workstation_fit"], plain["workstation_fit"])
        self.assertEqual(matched["binding_hints"], ["Search"])

    def test_ranking_keeps_metadata_gate(self):
        result = score_project(self.project(stars=25000))
        self.assertEqual(result["evidence_mode"], "metadata_only")
        self.assertEqual(result["tier"], "Unjudged")
        self.assertEqual(result["recommendation_status"], "shortlisted")

    def test_score_bounds(self):
        value = score_project(self.project())["total"]
        self.assertGreaterEqual(value, 0)
        self.assertLessEqual(value, 10)

    def test_archived_penalty(self):
        current = score_project(self.project())
        archived = score_project(self.project(raw={"archived": True}))
        self.assertGreater(current["total"], archived["total"])

    def test_naive_and_invalid_timestamps_are_safe(self):
        for value in ("2026-01-01", "not-a-date", "2026-01-01T00:00:00Z"):
            with self.subTest(value=value):
                self.assertIsInstance(score_project(self.project(pushed_at=value))["activity"], int)

    def test_tied_ranking_has_stable_order(self):
        projects = [ProjectCandidate(full_name=name, url="https://example.invalid/item")
                    for name in ("fictional/b", "fictional/a")]
        self.assertEqual(rank_projects(projects), rank_projects(list(reversed(projects))))

    def test_feedback_changes_next_score(self):
        project = self.project()
        before = score_project(project)
        append_feedback(project.full_name, 10, root=self.output)
        after = score_project(project, feedback=feedback_summary(self.output))
        self.assertGreater(after["total"], before["total"])
        self.assertGreater(after["feedback_adjustment"], 0)


class FeedbackTests(LocalTest):
    def test_valid_score_bounds(self):
        self.assertEqual(normalize_score(1), 1)
        self.assertEqual(normalize_score(10), 10)

    def test_invalid_score_bounds(self):
        for value in (0, 11):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_score(value)

    def test_decision_levels(self):
        self.assertEqual(decision_from_score(10), "poc_or_spec")
        self.assertEqual(decision_from_score(1), "strong_avoid")

    def test_feedback_dry_run_does_not_write(self):
        append_feedback("fictional/search", 8, root=self.output, dry_run=True)
        self.assertFalse((self.output / "feedback").exists())

    def test_malformed_lines_are_ignored(self):
        path = self.output / "feedback/oss_feedback.jsonl"
        path.parent.mkdir()
        path.write_text('not-json\n[]\n{"project":"fictional/search","score":8}\n', encoding="utf-8")
        self.assertEqual(feedback_summary(self.output).by_project, {"fictional/search": 8})

    def test_roundtrip_uses_candidate_snapshot(self):
        self.assertEqual(self.invoke(self.daily_args()), 0)
        append_feedback("fictional-lab/retrieval-kit", 8, root=self.output)
        summary = feedback_summary(self.output)
        self.assertIn("rag", summary.by_term)
        self.assertTrue(summary.by_category)


class CLITests(LocalTest):
    def test_daily_is_offline_without_network(self):
        with patch("urllib.request.urlopen", side_effect=AssertionError("network forbidden")) as urlopen:
            self.assertEqual(self.invoke(self.daily_args()), 0)
            urlopen.assert_not_called()
        path = self.output / "daily/2026-01-05-oss-daily.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload["recommendation_count"], 1)
        self.assertTrue(payload["synthetic"])
        self.assertEqual(payload["evidence_mode"], "metadata_only")
        self.assertEqual(len(payload["matched_needs"]), 2)

    def test_same_day_replaces_one_issue(self):
        self.assertEqual(self.invoke(self.daily_args()), 0)
        self.assertEqual(self.invoke(self.daily_args()), 0)
        self.assertEqual(len(list((self.output / "daily").glob("*.md"))), 1)

    def test_empty_pool_fails_without_report(self):
        args = self.daily_args()
        args[args.index("--candidates") + 1] = str(self.write_json({"projects": []}))
        self.assertEqual(self.invoke(args), 1)
        self.assertFalse((self.output / "daily").exists())

    def test_bad_input_is_not_echoed(self):
        args = self.daily_args()
        args[args.index("--candidates") + 1] = str(self.write_json({"projects": [{"private-field": "marker"}]}))
        captured = io.StringIO()
        with contextlib.redirect_stderr(captured):
            self.assertEqual(main(args), 2)
        self.assertNotIn("marker", captured.getvalue())

    def test_invalid_date_fails_without_output(self):
        args = self.daily_args()
        args[-1] = "not-a-date"
        self.assertEqual(self.invoke(args), 2)
        self.assertFalse((self.output / "daily").exists())

    def test_candidate_deduplication_and_raw_allowlist(self):
        row = {"full_name": "fictional/item", "url": "https://example.invalid/item",
               "raw": {"archived": False, "unused": "value"}}
        candidates = load_candidates(self.write_json({"projects": [row, row]}))
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].raw, {"archived": False})

    def test_rejects_invalid_candidate_fields(self):
        for extra in ({"stars": -1}, {"stars": True}, {"topics": "rag"},
                      {"url": "http://example.invalid"}, {"raw": []}, {"unknown": 1}):
            row = {"full_name": "fictional/item", "url": "https://example.invalid/item", **extra}
            with self.subTest(extra=extra), self.assertRaises((ValueError, TypeError)):
                load_candidates(self.write_json({"projects": [row]}))

    def test_normal_offline_data_is_not_marked_synthetic(self):
        args = self.daily_args()
        args[args.index("--candidates") + 1] = str(self.write_json({"projects": [
            {"full_name": "fictional/item", "url": "https://example.invalid/item"}]}))
        self.assertEqual(self.invoke(args), 0)
        payload = json.loads((self.output / "daily/2026-01-05-oss-daily.json").read_text())
        self.assertFalse(payload["synthetic"])

    def test_online_requires_explicit_mode(self):
        self.assertFalse(parser().parse_args(["daily"]).online)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            parser().parse_args(["daily", "--online", "--candidates", "file.json"])

    def test_online_all_failed_has_no_recommendation(self):
        args = ["daily", "--online", "--output", str(self.output),
                "--profile", str(ROOT / "config/profile.example.json"),
                "--sources", str(ROOT / "config/sources.example.json")]
        with patch("explore.cli.collect_github_project_pool", return_value=([], ["error"])):
            self.assertEqual(self.invoke(args), 1)
        self.assertFalse((self.output / "daily").exists())


class CollectorTests(LocalTest):
    def test_query_rotation(self):
        self.assertEqual(rotate_queries(["a", "b", "c"], offset=1, budget=2), ["b", "c"])
        self.assertEqual(rotate_queries(["a"], budget=0), [])

    def test_day_rotation_changes_next_day(self):
        first = day_of_year_query_offset("2026-01-05T00:00:00Z", 10)
        next_day = day_of_year_query_offset("2026-01-06T00:00:00Z", 10)
        self.assertEqual(next_day, (first + 1) % 10)

    def test_request_is_anonymous(self):
        reply = unittest.mock.MagicMock()
        reply.__enter__.return_value.read.return_value = b'{"items": []}'
        with patch("urllib.request.urlopen", return_value=reply) as urlopen:
            self.assertEqual(_request_json("https://api.github.com/search/repositories"), {"items": []})
        request = urlopen.call_args.args[0]
        self.assertFalse(request.has_header("Authorization"))

    def test_collector_deduplicates_topics(self):
        repo = {"full_name": "fictional/item", "html_url": "https://example.invalid/item",
                "topics": ["rag"], "stargazers_count": 50}
        other = {**repo, "topics": ["eval"]}
        with patch("explore.collectors.github_pool._request_json", side_effect=[{"items": [repo]}, {"items": [other]}]):
            projects, errors = collect_github_project_pool(["one", "two"], per_query_limit=1)
        self.assertEqual(len(projects), 1)
        self.assertEqual(projects[0].topics, ["eval", "rag"])
        self.assertFalse(errors)

    def test_partial_failure_is_redacted(self):
        repo = {"full_name": "fictional/item", "html_url": "https://example.invalid/item"}
        with patch("explore.collectors.github_pool._request_json", side_effect=[RuntimeError("private marker"), {"items": [repo]}]):
            projects, errors = collect_github_project_pool(["one", "two"])
        self.assertEqual(len(projects), 1)
        self.assertEqual(len(errors), 1)
        self.assertNotIn("private marker", errors[0])

    def test_user_agent_does_not_impersonate_browser(self):
        self.assertEqual(validate_user_agent("Explore/0.1"), "Explore/0.1")
        for value in ("", "Mozilla/5.0", "you@example.com"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_user_agent(value)


if __name__ == "__main__":
    unittest.main()
