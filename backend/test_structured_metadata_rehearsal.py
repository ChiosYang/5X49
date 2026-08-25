import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from sqlmodel import SQLModel, create_engine

import app.models  # noqa: F401
from app.database import configure_sqlite_engine
from app.migrations.runner import run_migrations
from app.migrations.structured_metadata import (
    StructuredMetadataValidationError,
    preflight_rehearsal,
    run_rehearsal,
)


class StructuredMetadataRehearsalTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.data_root = self.root / "data"
        self.input_dir = self.data_root / "gate-a" / "input"
        self.input_dir.mkdir(parents=True)
        self.runs_root = self.data_root / "structured-metadata" / "runs"
        self.media_root = self.root / "media"
        movie = self.media_root / "Recorded Movie"
        movie.mkdir(parents=True)
        (movie / "movie.mkv").write_bytes(b"synthetic video")
        (movie / "movie.nfo").write_text(
            "<movie><title>Recorded Movie</title><originaltitle>Recorded Movie</originaltitle>"
            "<year>2026</year><country>USA</country><genre>Drama</genre>"
            "<director>Recorded Director</director>"
            "<actor><name>Recorded Actor</name><role>Lead</role><order>0</order></actor>"
            "</movie>",
            encoding="utf-8",
        )
        (self.input_dir / "media-root.txt").write_text(
            str(self.media_root.resolve()),
            encoding="utf-8",
        )

    def tearDown(self):
        self._tmp.cleanup()

    def test_rehearsal_upgrades_copy_and_emits_redacted_pass_report(self):
        database_path = self.input_dir / "library.db"
        engine = create_engine(f"sqlite:///{database_path}")
        configure_sqlite_engine(engine)
        try:
            SQLModel.metadata.create_all(engine)
            run_migrations(
                engine,
                database_path,
                app_version="test",
                backup_required=False,
            )
        finally:
            engine.dispose()
        source_before = database_path.read_bytes()
        run_dir = self.runs_root / "rehearsal-test"

        report = run_rehearsal(self.input_dir, run_dir)

        self.assertEqual(report["overall_status"], "passed")
        self.assertTrue(all(value == "passed" for value in report["phases"].values()))
        self.assertTrue(all(item["status"] == "passed" for item in report["checks"]))
        self.assertEqual(database_path.read_bytes(), source_before)
        persisted = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
        serialized = json.dumps(persisted, ensure_ascii=False)
        self.assertNotIn(str(self.media_root.resolve()), serialized)
        self.assertNotIn("sk-w3-synthetic-secret-canary", serialized)
        self.assertNotRegex(serialized, r"person_[0-9a-f]{32}")

    def test_preflight_rejects_corrupt_input_and_outside_run_directory(self):
        database_path = self.input_dir / "library.db"
        database_path.write_bytes(b"not sqlite")
        with self.assertRaises(StructuredMetadataValidationError):
            preflight_rehearsal(self.input_dir, self.runs_root / "corrupt")

        database_path.unlink()
        with closing(sqlite3.connect(database_path)) as connection:
            connection.execute("CREATE TABLE sentinel (id INTEGER PRIMARY KEY)")
            connection.commit()
        with self.assertRaises(StructuredMetadataValidationError):
            preflight_rehearsal(self.input_dir, self.root / "outside")


if __name__ == "__main__":
    unittest.main()
