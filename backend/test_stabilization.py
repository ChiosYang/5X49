import shutil
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from app.evaluation import stabilization


class FreshCanonicalStabilizationTests(unittest.TestCase):
    def setUp(self):
        self.run_id = f"unit-{uuid4().hex}"
        self.run_dir = stabilization._backend_root() / "data" / "stabilization" / "runs" / self.run_id

    def tearDown(self):
        if self.run_dir.is_dir():
            shutil.rmtree(self.run_dir)

    def _run_report(self, *, backend_status: str = "passed") -> dict:
        return {
            "schema_version": stabilization.REPORT_SCHEMA_VERSION,
            "run_id": self.run_id,
            "commit_sha": "a" * 40,
            "fixture_hash": "b" * 64,
            "checks": [{"id": "backend", "status": backend_status}],
            "phases": {"backend": backend_status},
            "backend_status": backend_status,
            "browser_status": "blocked",
            "live_external_status": "not_run",
            "docker_status": "not_available",
            "overall_status": "blocked" if backend_status == "passed" else backend_status,
        }

    def test_run_directory_must_be_new_and_inside_the_isolated_root(self):
        self.assertEqual(stabilization._validate_new_run_dir(self.run_dir), self.run_dir.resolve())
        self.run_dir.mkdir(parents=True)
        with self.assertRaises(stabilization.StabilizationError):
            stabilization._validate_new_run_dir(self.run_dir)
        with self.assertRaises(stabilization.StabilizationError):
            stabilization._validate_new_run_dir(stabilization._backend_root() / "data" / "outside")

    def test_missing_ffmpeg_blocks_before_creating_run_artifacts(self):
        with patch.object(stabilization.shutil, "which", return_value=None):
            with self.assertRaises(stabilization.StabilizationBlocked):
                stabilization.run_rehearsal(self.run_dir)
        self.assertFalse(self.run_dir.exists())

    def test_browser_template_is_complete_and_conclusion_requires_all_passed(self):
        self.run_dir.mkdir(parents=True)
        run_report = self.run_dir / "run-report.json"
        browser_report = self.run_dir / "browser-report.json"
        stabilization._write_json(run_report, self._run_report())
        template = stabilization.create_browser_template(run_report, browser_report)
        self.assertEqual(
            tuple(item["id"] for item in template["checks"]),
            stabilization.REQUIRED_BROWSER_CHECKS,
        )
        self.assertEqual(stabilization.conclude(run_report, browser_report)["overall_status"], "blocked")

        template["checks"] = [
            {"id": check_id, "status": "passed"}
            for check_id in stabilization.REQUIRED_BROWSER_CHECKS
        ]
        template["browser_status"] = "passed"
        stabilization._write_json(browser_report, template)
        conclusion = stabilization.conclude(run_report, browser_report)
        self.assertEqual(conclusion["backend_status"], "passed")
        self.assertEqual(conclusion["browser_status"], "passed")
        self.assertEqual(conclusion["overall_status"], "passed")

    def test_browser_report_rejects_missing_checks_and_wrong_fixture(self):
        self.run_dir.mkdir(parents=True)
        run_report = self.run_dir / "run-report.json"
        browser_report = self.run_dir / "browser-report.json"
        stabilization._write_json(run_report, self._run_report())
        template = stabilization.create_browser_template(run_report, browser_report)
        template["checks"].pop()
        stabilization._write_json(browser_report, template)
        with self.assertRaises(stabilization.StabilizationError):
            stabilization.conclude(run_report, browser_report)

        template = stabilization.create_browser_template(run_report, browser_report)
        template["fixture_hash"] = "c" * 64
        stabilization._write_json(browser_report, template)
        with self.assertRaises(stabilization.StabilizationError):
            stabilization.conclude(run_report, browser_report)

    def test_privacy_scan_detects_credentials_and_user_paths(self):
        self.assertTrue(stabilization._privacy_leaks({"error": "sk-stabilization-private-canary"}))
        self.assertTrue(stabilization._privacy_leaks({"path": "C:\\Users\\someone\\movie.mkv"}))
        self.assertFalse(stabilization._privacy_leaks({"status": "passed", "digest": "abc123"}))


if __name__ == "__main__":
    unittest.main()
