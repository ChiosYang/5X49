import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from app.evaluation import factual_explore


class FactualExploreEvaluationTests(unittest.TestCase):
    def test_scale_worker_enforces_four_dimensions_privacy_and_query_bound(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "scale-run"
            run_dir.mkdir()
            report = factual_explore._run_worker(
                run_dir,
                "scale",
                seed=550,
                count=48,
            )

        self.assertEqual(report["status"], "passed")
        self.assertEqual(set(report["coverage"]), set(factual_explore.DIMENSIONS))
        self.assertLessEqual(report["context_statement_count"], 10)
        self.assertTrue(all(item["status"] == "passed" for item in report["checks"]))
        serialized = json.dumps(report, sort_keys=True).casefold()
        for forbidden in factual_explore.FORBIDDEN_PUBLIC_TEXT:
            self.assertNotIn(forbidden, serialized)

    def test_run_evaluation_writes_deterministic_aggregate_and_safe_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            output_root = Path(directory)
            with (
                patch.object(
                    factual_explore,
                    "_run_worker",
                    side_effect=(
                        self._worker_report("behavior", 8),
                        self._worker_report("scale", 48),
                    ),
                ),
                patch.object(factual_explore, "_git_sha", return_value="abc123def456"),
            ):
                report = factual_explore.run_evaluation(
                    run_id="w7-unit-01",
                    seed=549,
                    count=8,
                    scale_count=48,
                    output_root=output_root,
                )

            report_path = output_root / "w7-unit-01" / "report.json"
            summary_path = output_root / "w7-unit-01" / "summary.md"
            self.assertTrue(report_path.is_file())
            self.assertTrue(summary_path.is_file())
            self.assertEqual(report["status"], "passed")
            self.assertEqual(
                report["fixture_contract_hash"],
                factual_explore._fixture_contract_hash(549, 8, 48),
            )
            summary = summary_path.read_text(encoding="utf-8")
            self.assertIn("deterministic engineering fixture", summary)
            self.assertIn("not real-library or Alpha-user evidence", summary)
            self.assertNotIn(str(output_root), summary)
            for forbidden in factual_explore.FORBIDDEN_PUBLIC_TEXT:
                self.assertNotIn(forbidden, summary.casefold())

    def test_main_returns_failed_for_a_failed_gate_and_two_for_invalid_options(self):
        failed_report = {
            "status": "failed",
            "behavior": self._worker_report("behavior", 8),
            "scale": self._worker_report("scale", 48),
            "checks": [{"id": "forced-failure", "status": "failed"}],
            "schema_version": factual_explore.REPORT_SCHEMA_VERSION,
            "summary_schema_version": factual_explore.SUMMARY_SCHEMA_VERSION,
            "run_id": "w7-failed",
            "commit_sha": "abc123def456",
            "seed": 549,
            "count": 8,
            "scale_count": 48,
            "fixture_contract_hash": "0123456789abcdef",
            "dimensions": list(factual_explore.DIMENSIONS),
        }
        with (
            patch.object(factual_explore, "run_evaluation", return_value=failed_report),
            patch.object(factual_explore, "render_git_safe_summary", return_value="failed\n"),
        ):
            with redirect_stdout(io.StringIO()):
                self.assertEqual(factual_explore.main(["--run-id", "w7-failed"]), 1)

        error = io.StringIO()
        with redirect_stderr(error):
            self.assertEqual(
                factual_explore.main(
                    ["--run-id", "../escape", "--count", "8", "--scale-count", "48"]
                ),
                2,
            )
        self.assertIn("bounded portable identifier", error.getvalue())

    @staticmethod
    def _worker_report(mode: str, count: int) -> dict:
        missing = 1
        conflict = 1
        coverage = {
            "genre": factual_explore._coverage(count, count - missing, 0, missing),
            "person": factual_explore._coverage(count, count - missing, 0, missing),
            "country": factual_explore._coverage(
                count,
                count - missing - conflict,
                conflict,
                missing,
            ),
            "decade": factual_explore._coverage(count, count - missing, 0, missing),
        }
        return {
            "mode": mode,
            "seed": 549,
            "count": count,
            "status": "passed",
            "coverage": coverage,
            "context_statement_count": 9,
            "durations_ms": {"overview": 1.0, "context": 2.0, "films": 3.0},
            "projection_rows": {"films": count, "facets": count * 4},
            "checks": [{"id": f"{mode}-gate", "status": "passed"}],
        }


if __name__ == "__main__":
    unittest.main()
