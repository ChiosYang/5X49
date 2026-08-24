import io
import hashlib
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing, redirect_stderr, redirect_stdout
from pathlib import Path

from sqlalchemy import create_engine, text


class GateACliTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_conclude_blocks_a_strict_gate_without_docker_evidence(self):
        from app.migrations.gate_a import main

        local_report = self.root / "local-report.json"
        local_report.write_text(
            json.dumps({
                "schema_version": 1,
                "run_id": "gate-test",
                "source_fingerprint": "0123456789abcdef",
                "checks": [
                    {"id": check_id, "status": "passed", "details": {}}
                    for check_id in (
                        "real-library-input",
                        "real-media-input-available",
                        "source-database-unchanged",
                    )
                ],
                "phases": {
                    phase: "passed"
                    for phase in (
                        "preflight",
                        "upgrade",
                        "idempotence",
                        "consistency",
                        "runtime",
                        "restore",
                        "privacy",
                    )
                },
                "local_status": "passed",
                "docker_status": "blocked",
                "overall_status": "blocked",
            }),
            encoding="utf-8",
        )
        stdout = io.StringIO()
        stderr = io.StringIO()

        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = main(["conclude", "--local-report", str(local_report)])

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 3)
        self.assertEqual(payload["local_status"], "passed")
        self.assertEqual(payload["docker_status"], "blocked")
        self.assertEqual(payload["overall_status"], "blocked")
        self.assertEqual(payload["source_fingerprint"], "0123456789abcdef")
        self.assertEqual(stderr.getvalue(), "")

    def test_conclude_rejects_incomplete_pass_claims_from_both_evidence_sources(self):
        from app.migrations.gate_a import main

        local_report = self.root / "local-report.json"
        docker_report = self.root / "docker-report.json"
        base = {
            "schema_version": 1,
            "run_id": "incomplete",
            "source_fingerprint": "0123456789abcdef",
            "checks": [],
            "phases": {},
            "local_status": "passed",
            "docker_status": "passed",
            "overall_status": "passed",
        }
        local_report.write_text(json.dumps(base), encoding="utf-8")
        docker_report.write_text(json.dumps(base), encoding="utf-8")
        stdout = io.StringIO()

        with redirect_stdout(stdout):
            exit_code = main([
                "conclude",
                "--local-report",
                str(local_report),
                "--docker-report",
                str(docker_report),
            ])

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 3)
        self.assertEqual(payload["local_status"], "blocked")
        self.assertEqual(payload["docker_status"], "blocked")
        self.assertEqual(payload["overall_status"], "blocked")

    def test_conclude_passes_only_a_complete_local_and_docker_matrix(self):
        from app.migrations.gate_a import main

        local_report = self.root / "local-report.json"
        docker_report = self.root / "docker-report.json"
        local_report.write_text(json.dumps({
            "schema_version": 1,
            "run_id": "complete",
            "source_fingerprint": "0123456789abcdef",
            "checks": [
                {"id": check_id, "status": "passed", "details": {}}
                for check_id in (
                    "real-library-input",
                    "real-media-input-available",
                    "source-database-unchanged",
                )
            ],
            "phases": {
                phase: "passed"
                for phase in (
                    "preflight",
                    "upgrade",
                    "idempotence",
                    "consistency",
                    "runtime",
                    "restore",
                    "privacy",
                )
            },
            "local_status": "passed",
            "docker_status": "blocked",
            "overall_status": "blocked",
        }), encoding="utf-8")
        docker_report.write_text(json.dumps({
            "schema_version": 1,
            "run_id": "complete",
            "source_fingerprint": "0123456789abcdef",
            "checks": [
                {"id": check_id, "status": "passed", "details": {}}
                for check_id in (
                    "docker-isolated-resources",
                    "docker-input-unchanged",
                )
            ],
            "phases": {
                phase: "passed"
                for phase in (
                    "compose_config",
                    "image_build",
                    "upgrade",
                    "read_sources",
                    "fresh_install",
                    "restore",
                    "browser_smoke",
                )
            },
            "local_status": "blocked",
            "docker_status": "passed",
            "overall_status": "blocked",
        }), encoding="utf-8")
        stdout = io.StringIO()

        with redirect_stdout(stdout):
            exit_code = main([
                "conclude",
                "--local-report",
                str(local_report),
                "--docker-report",
                str(docker_report),
            ])

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["local_status"], "passed")
        self.assertEqual(payload["docker_status"], "passed")
        self.assertEqual(payload["overall_status"], "passed")

    def test_rehearse_refuses_an_offline_input_with_sqlite_sidecars(self):
        from app.migrations.gate_a import main

        gate_root = self.root / "gate-a"
        input_dir = gate_root / "input"
        run_dir = gate_root / "runs" / "sidecar"
        media_root = self.root / "media"
        input_dir.mkdir(parents=True)
        media_root.mkdir()
        database_path = input_dir / "library.db"
        with closing(sqlite3.connect(database_path)) as connection:
            connection.execute("CREATE TABLE movie (id TEXT PRIMARY KEY, title TEXT NOT NULL)")
            connection.commit()
        (input_dir / "media-root.txt").write_text(str(media_root.resolve()), encoding="utf-8")
        Path(f"{database_path}-wal").write_bytes(b"active-sidecar")
        stdout = io.StringIO()
        stderr = io.StringIO()

        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = main([
                "rehearse",
                "--input-dir",
                str(input_dir),
                "--run-dir",
                str(run_dir),
            ])

        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("offline", stderr.getvalue().casefold())
        self.assertNotIn(str(database_path), stderr.getvalue())
        self.assertFalse(run_dir.exists())

    def test_rehearse_refuses_broken_foreign_keys_before_creating_a_run(self):
        from app.migrations.gate_a import main

        gate_root = self.root / "gate-a"
        input_dir = gate_root / "input"
        run_dir = gate_root / "runs" / "broken-fk"
        media_root = self.root / "media"
        input_dir.mkdir(parents=True)
        media_root.mkdir()
        database_path = input_dir / "library.db"
        with closing(sqlite3.connect(database_path)) as connection:
            connection.executescript(
                "CREATE TABLE parent (id TEXT PRIMARY KEY);"
                "CREATE TABLE child (parent_id TEXT REFERENCES parent(id));"
                "INSERT INTO child (parent_id) VALUES ('missing');"
            )
            connection.commit()
        (input_dir / "media-root.txt").write_text(str(media_root.resolve()), encoding="utf-8")
        stdout = io.StringIO()
        stderr = io.StringIO()

        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = main([
                "rehearse",
                "--input-dir",
                str(input_dir),
                "--run-dir",
                str(run_dir),
            ])

        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("foreign-key", stderr.getvalue())
        self.assertFalse(run_dir.exists())

    def test_rehearse_upgrades_a_fixture_copy_without_mutating_the_source(self):
        from app.migrations.gate_a import main

        gate_root = self.root / "gate-a"
        input_dir = gate_root / "input"
        run_dir = gate_root / "runs" / "fixture-smoke"
        media_root = self.root / "empty-media"
        input_dir.mkdir(parents=True)
        media_root.mkdir()
        database_path = input_dir / "library.db"
        fixture = Path(__file__).parent / "fixtures" / "database" / "current-unversioned"
        with closing(sqlite3.connect(database_path)) as connection:
            connection.executescript((fixture / "schema.sql").read_text(encoding="utf-8"))
            connection.commit()
        (input_dir / "media-root.txt").write_text(str(media_root.resolve()), encoding="utf-8")
        source_hash = hashlib.sha256(database_path.read_bytes()).hexdigest()
        stdout = io.StringIO()
        stderr = io.StringIO()

        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = main([
                "rehearse",
                "--input-dir",
                str(input_dir),
                "--run-dir",
                str(run_dir),
            ])

        payload = json.loads(stdout.getvalue())
        stored = json.loads((run_dir / "local-report.json").read_text(encoding="utf-8"))
        self.assertEqual(exit_code, 3)
        self.assertEqual(payload, stored)
        self.assertEqual(payload["phases"]["preflight"], "passed")
        self.assertEqual(payload["phases"]["upgrade"], "passed")
        self.assertEqual(payload["phases"]["idempotence"], "passed")
        self.assertEqual(payload["phases"]["consistency"], "passed")
        self.assertEqual(payload["phases"]["runtime"], "blocked")
        self.assertEqual(payload["phases"]["restore"], "passed")
        self.assertEqual(payload["local_status"], "blocked")
        self.assertEqual(payload["docker_status"], "blocked")
        self.assertEqual(payload["overall_status"], "blocked")
        self.assertEqual(hashlib.sha256(database_path.read_bytes()).hexdigest(), source_hash)
        serialized = json.dumps(payload)
        self.assertNotIn("Current Sentinel", serialized)
        self.assertNotIn(str(media_root.resolve()), serialized)
        self.assertEqual(stderr.getvalue(), "")
        checks = {check["id"]: check for check in payload["checks"]}
        self.assertEqual(checks["backup-restored-byte-for-byte"]["status"], "passed")
        self.assertEqual(checks["restored-database-remigrates-cleanly"]["status"], "passed")

    def test_rehearse_fails_when_a_legacy_movie_has_no_canonical_alias(self):
        from app.database import configure_sqlite_engine
        from app.migrations.gate_a import main
        from app.migrations.runner import run_migrations

        gate_root = self.root / "gate-a"
        input_dir = gate_root / "input"
        run_dir = gate_root / "runs" / "missing-alias"
        media_root = self.root / "empty-media"
        input_dir.mkdir(parents=True)
        media_root.mkdir()
        database_path = input_dir / "library.db"
        fixture = Path(__file__).parent / "fixtures" / "database" / "current-unversioned"
        with closing(sqlite3.connect(database_path)) as connection:
            connection.executescript((fixture / "schema.sql").read_text(encoding="utf-8"))
            connection.commit()
        engine = create_engine(f"sqlite:///{database_path}")
        configure_sqlite_engine(engine)
        try:
            run_migrations(engine, database_path, app_version="test", backup_required=False)
            with engine.begin() as connection:
                connection.execute(text("DELETE FROM legacy_movie_alias"))
        finally:
            engine.dispose()
        (input_dir / "media-root.txt").write_text(str(media_root.resolve()), encoding="utf-8")
        stdout = io.StringIO()
        stderr = io.StringIO()

        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = main([
                "rehearse",
                "--input-dir",
                str(input_dir),
                "--run-dir",
                str(run_dir),
            ])

        payload = json.loads(stdout.getvalue())
        checks = {check["id"]: check for check in payload["checks"]}
        self.assertEqual(exit_code, 2)
        self.assertEqual(payload["phases"]["consistency"], "failed")
        self.assertEqual(checks["legacy-movies-have-aliases"]["status"], "failed")
        self.assertEqual(payload["local_status"], "failed")
        self.assertEqual(payload["overall_status"], "failed")
        self.assertEqual(stderr.getvalue(), "")

    def test_rehearse_runs_repeatable_reconcile_clear_restore_and_privacy_checks(self):
        from app.migrations.gate_a import main
        from scripts.generate_test_data import generate_dataset

        gate_root = self.root / "gate-a"
        input_dir = gate_root / "input"
        run_dir = gate_root / "runs" / "runtime-smoke"
        generated = self.root / "generated"
        input_dir.mkdir(parents=True)
        generate_dataset(generated, count=2, seed=549, profile="normal")
        media_root = generated / "media"
        database_path = input_dir / "library.db"
        fixture = Path(__file__).parent / "fixtures" / "database" / "current-unversioned"
        with closing(sqlite3.connect(database_path)) as connection:
            connection.executescript((fixture / "schema.sql").read_text(encoding="utf-8"))
            connection.commit()
        (input_dir / "media-root.txt").write_text(str(media_root.resolve()), encoding="utf-8")
        media_hashes_before = self._tree_hashes(media_root)
        stdout = io.StringIO()
        stderr = io.StringIO()

        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = main([
                "rehearse",
                "--input-dir",
                str(input_dir),
                "--run-dir",
                str(run_dir),
            ])

        payload = json.loads(stdout.getvalue())
        checks = {check["id"]: check for check in payload["checks"]}
        self.assertEqual(exit_code, 3)
        self.assertEqual(payload["phases"]["runtime"], "passed")
        self.assertEqual(payload["phases"]["privacy"], "passed")
        self.assertEqual(payload["local_status"], "passed")
        self.assertEqual(payload["docker_status"], "blocked")
        self.assertEqual(payload["overall_status"], "blocked")
        self.assertEqual(checks["second-full-reconcile-is-idempotent"]["status"], "passed")
        self.assertEqual(
            checks["ordinary-clear-restores-aliases-and-personal-state"]["status"],
            "passed",
        )
        self.assertEqual(
            checks["destructive-clear-is-confined-to-extra-copy"]["status"],
            "passed",
        )
        self.assertEqual(checks["large-file-foreground-budget-enforced"]["status"], "passed")
        self.assertEqual(
            checks["mini-platform-id-relink-preserves-alias"]["status"],
            "passed",
        )
        self.assertEqual(
            checks["mini-missing-restore-preserves-alias"]["status"],
            "passed",
        )
        self.assertEqual(
            checks["mini-multiple-items-share-one-film"]["status"],
            "passed",
        )
        self.assertEqual(
            checks["mini-full-hash-disambiguates-collision"]["status"],
            "passed",
        )
        self.assertEqual(checks["sensitive-canaries-not-exposed"]["status"], "passed")
        self.assertEqual(self._tree_hashes(media_root), media_hashes_before)
        self.assertNotIn(str(media_root.resolve()), stdout.getvalue())
        self.assertNotIn("The Quiet Signal", stdout.getvalue())
        self.assertEqual(stderr.getvalue(), "")

    def test_rehearse_fails_when_a_stable_event_exposes_a_path_canary(self):
        from sqlmodel import Session

        from app.database import configure_sqlite_engine
        from app.migrations.gate_a import main
        from app.migrations.runner import run_migrations
        from app.models import EventRecord

        gate_root = self.root / "gate-a"
        input_dir = gate_root / "input"
        run_dir = gate_root / "runs" / "event-leak"
        media_root = self.root / "empty-media"
        input_dir.mkdir(parents=True)
        media_root.mkdir()
        database_path = input_dir / "library.db"
        fixture = Path(__file__).parent / "fixtures" / "database" / "current-unversioned"
        with closing(sqlite3.connect(database_path)) as connection:
            connection.executescript((fixture / "schema.sql").read_text(encoding="utf-8"))
            connection.commit()
        engine = create_engine(f"sqlite:///{database_path}")
        configure_sqlite_engine(engine)
        try:
            run_migrations(engine, database_path, app_version="test", backup_required=False)
            with Session(engine) as session:
                session.add(EventRecord(
                    aggregate_type="library_item",
                    aggregate_id="lib_canary",
                    type="LibraryItemRelinkNeedsReview",
                    payload={"path": str(media_root.resolve())},
                ))
                session.commit()
        finally:
            engine.dispose()
        (input_dir / "media-root.txt").write_text(str(media_root.resolve()), encoding="utf-8")
        stdout = io.StringIO()

        with redirect_stdout(stdout):
            exit_code = main([
                "rehearse",
                "--input-dir",
                str(input_dir),
                "--run-dir",
                str(run_dir),
            ])

        payload = json.loads(stdout.getvalue())
        check = next(item for item in payload["checks"] if item["id"] == "sensitive-canaries-not-exposed")
        self.assertEqual(exit_code, 2)
        self.assertEqual(payload["phases"]["privacy"], "failed")
        self.assertEqual(check["status"], "failed")
        self.assertEqual(check["details"]["leak_layers"], ["event_record"])
        self.assertNotIn(str(media_root.resolve()), stdout.getvalue())

    @staticmethod
    def _tree_hashes(root: Path) -> dict[str, str]:
        return {
            path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in root.rglob("*")
            if path.is_file()
        }


if __name__ == "__main__":
    unittest.main()
