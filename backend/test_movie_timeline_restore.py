import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, create_engine, select

import app.database as database
import app.services.event_store as event_store_module
import app.services.library as library_module
import app.services.projections.movie_timeline as movie_timeline_module
import app.services.timeline_restore as timeline_restore_module
from app.main import app
from app.models import EventRecord, Movie
from app.services.timeline_restore import TimelineRestoreBlocked, movie_timeline_restore


class MovieTimelineRestoreTests(unittest.TestCase):
    def setUp(self):
        self._original_database_engine = database.engine
        self._original_event_store_engine = event_store_module.engine
        self._original_library_engine = library_module.engine
        self._original_timeline_engine = movie_timeline_module.engine
        self._original_restore_engine = timeline_restore_module.engine
        self._original_media_dir = os.environ.get("MEDIA_DIR")
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmp.name)
        self.media_dir = self.tmp_path / "media"
        self.media_dir.mkdir()
        os.environ["MEDIA_DIR"] = str(self.media_dir)
        self.engine = create_engine(f"sqlite:///{self.tmp_path / 'library.db'}")
        database.engine = self.engine
        event_store_module.engine = self.engine
        library_module.engine = self.engine
        movie_timeline_module.engine = self.engine
        timeline_restore_module.engine = self.engine
        SQLModel.metadata.create_all(self.engine)

    def tearDown(self):
        database.engine = self._original_database_engine
        event_store_module.engine = self._original_event_store_engine
        library_module.engine = self._original_library_engine
        movie_timeline_module.engine = self._original_timeline_engine
        timeline_restore_module.engine = self._original_restore_engine
        if self._original_media_dir is None:
            os.environ.pop("MEDIA_DIR", None)
        else:
            os.environ["MEDIA_DIR"] = self._original_media_dir
        self.engine.dispose()
        self._tmp.cleanup()

    def test_restores_selected_fields_with_movie_state_restored_event(self):
        self._insert_movie(Movie(id="field_restore", title="Updated", year=2026, tmdb_id="999"))
        self._insert_events([
            self._event(
                "evt_0001",
                "MovieDiscovered",
                {"movie_id": "field_restore", "id": "field_restore", "title": "Original", "year": 2026},
                "2026-05-22T00:00:01+00:00",
            ),
            self._event(
                "evt_0002",
                "MetadataMatched",
                {
                    "movie_id": "field_restore",
                    "changed_fields": ["title", "tmdb_id"],
                    "previous": {"title": "Original", "tmdb_id": None},
                    "current": {"title": "Updated", "tmdb_id": "999"},
                },
                "2026-05-22T00:00:02+00:00",
            ),
        ])

        report = movie_timeline_restore.run(
            movie_id="field_restore",
            before_event_id="evt_0002",
            restore_fields=["title"],
            restore_files=[],
        )

        self.assertEqual(report["status"], "restored")
        self.assertEqual(report["restored"][0]["action"], "restore_fields")
        stored = self._movie("field_restore")
        self.assertEqual(stored.title, "Original")
        self.assertEqual(stored.tmdb_id, "999")
        event = self._latest_event("MovieStateRestored")
        self.assertEqual(event.aggregate_id, "field_restore")
        self.assertEqual(event.payload["restored_fields"][0]["field"], "title")
        self.assertEqual(event.payload["target"]["before_event_id"], "evt_0002")

    def test_default_field_restore_restores_all_preview_fields(self):
        self._insert_movie(Movie(id="default_fields", title="Updated", year=2026, tmdb_id="999"))
        self._insert_events([
            self._event(
                "evt_0101",
                "MovieDiscovered",
                {"movie_id": "default_fields", "id": "default_fields", "title": "Original", "year": 2026},
                "2026-05-22T00:00:01+00:00",
            ),
            self._event(
                "evt_0102",
                "MetadataMatched",
                {
                    "movie_id": "default_fields",
                    "changed_fields": ["title", "tmdb_id"],
                    "previous": {"title": "Original", "tmdb_id": None},
                    "current": {"title": "Updated", "tmdb_id": "999"},
                },
                "2026-05-22T00:00:02+00:00",
            ),
        ])

        report = movie_timeline_restore.run(
            movie_id="default_fields",
            before_event_id="evt_0102",
            restore_files=[],
        )

        self.assertEqual(report["restored"][0]["restored_fields"], 1)
        stored = self._movie("default_fields")
        self.assertEqual(stored.title, "Original")
        self.assertEqual(stored.tmdb_id, "999")

    def test_conflict_blocks_without_mutation_when_partial_not_allowed(self):
        self._insert_movie(Movie(id="conflict_block", title="Manual", year=2026, tmdb_id="999"))
        before_counts = self._counts()

        with patch.object(
            timeline_restore_module.movie_timeline_dry_run,
            "restore_preview",
            return_value=self._preview(
                movie_id="conflict_block",
                fields=[{"field": "title", "current": "Updated", "target": "Original", "restorable": True}],
            ),
        ):
            with self.assertRaises(TimelineRestoreBlocked) as context:
                movie_timeline_restore.run(
                    movie_id="conflict_block",
                    before_event_id="evt_0202",
                    restore_fields=["title"],
                    restore_files=[],
                )

        self.assertEqual(self._counts(), before_counts)
        self.assertEqual(self._movie("conflict_block").title, "Manual")
        self.assertEqual(context.exception.report["conflicts"][0]["field"], "title")

    def test_conflict_allows_safe_subset_when_partial_allowed(self):
        self._insert_movie(Movie(id="partial_fields", title="Manual", year=2026, tmdb_id="999"))
        with patch.object(
            timeline_restore_module.movie_timeline_dry_run,
            "restore_preview",
            return_value=self._preview(
                movie_id="partial_fields",
                fields=[
                    {"field": "title", "current": "Updated", "target": "Original", "restorable": True},
                    {"field": "tmdb_id", "current": "999", "target": None, "restorable": True},
                ],
            ),
        ):
            report = movie_timeline_restore.run(
                movie_id="partial_fields",
                before_event_id="evt_0302",
                restore_fields=["title", "tmdb_id"],
                restore_files=[],
                allow_partial=True,
            )

        self.assertEqual(report["status"], "partial")
        self.assertEqual(report["conflicts"][0]["field"], "title")
        stored = self._movie("partial_fields")
        self.assertEqual(stored.title, "Manual")
        self.assertIsNone(stored.tmdb_id)

    def test_restores_artwork_and_nfo_files_from_backups(self):
        movie_dir = self.media_dir / "Movie"
        movie_dir.mkdir()
        poster = movie_dir / "poster.jpg"
        nfo = movie_dir / "movie.nfo"
        poster.write_text("new poster")
        nfo.write_text("new nfo")
        poster_backup = movie_dir / "poster.backup.jpg"
        nfo_backup = movie_dir / "movie.backup.nfo"
        poster_backup.write_text("old poster")
        nfo_backup.write_text("old nfo")
        self._insert_movie(Movie(id="files_restore", title="Files", year=2026))
        self._insert_events([
            self._event(
                "evt_0401",
                "MovieDiscovered",
                {"movie_id": "files_restore", "id": "files_restore", "title": "Files", "year": 2026},
                "2026-05-22T00:00:01+00:00",
            ),
            self._event(
                "evt_0402",
                "ArtworkDownloaded",
                {
                    "movie_id": "files_restore",
                    "asset_type": "poster",
                    "destination": str(poster),
                    "backup_path": str(poster_backup),
                },
                "2026-05-22T00:00:02+00:00",
            ),
            self._event(
                "evt_0403",
                "NfoWritten",
                {
                    "movie_id": "files_restore",
                    "path": str(nfo),
                    "backup_path": str(nfo_backup),
                },
                "2026-05-22T00:00:03+00:00",
            ),
        ])

        report = movie_timeline_restore.run(
            movie_id="files_restore",
            before_event_id="evt_0402",
            restore_fields=[],
            restore_files=["poster", "nfo"],
        )

        self.assertEqual(report["status"], "restored")
        self.assertEqual(poster.read_text(), "old poster")
        self.assertEqual(nfo.read_text(), "old nfo")
        self.assertIsNotNone(self._latest_event("ArtworkRestored"))
        self.assertIsNotNone(self._latest_event("NfoRestored"))

    def test_missing_backup_blocks_without_mutation_when_partial_not_allowed(self):
        movie_dir = self.media_dir / "MissingBackup"
        movie_dir.mkdir()
        poster = movie_dir / "poster.jpg"
        poster.write_text("new poster")
        self._insert_movie(Movie(id="missing_backup", title="Files", year=2026))
        self._insert_events([
            self._event(
                "evt_0501",
                "MovieDiscovered",
                {"movie_id": "missing_backup", "id": "missing_backup", "title": "Files", "year": 2026},
                "2026-05-22T00:00:01+00:00",
            ),
            self._event(
                "evt_0502",
                "ArtworkDownloaded",
                {
                    "movie_id": "missing_backup",
                    "asset_type": "poster",
                    "destination": str(poster),
                    "backup_path": str(movie_dir / "missing.backup.jpg"),
                },
                "2026-05-22T00:00:02+00:00",
            ),
        ])
        before_counts = self._counts()

        with self.assertRaises(TimelineRestoreBlocked):
            movie_timeline_restore.run(
                movie_id="missing_backup",
                before_event_id="evt_0502",
                restore_fields=[],
                restore_files=["poster"],
            )

        self.assertEqual(self._counts(), before_counts)
        self.assertEqual(poster.read_text(), "new poster")

    def test_missing_backup_is_skipped_when_partial_allowed(self):
        movie_dir = self.media_dir / "PartialBackup"
        movie_dir.mkdir()
        poster = movie_dir / "poster.jpg"
        poster.write_text("new poster")
        self._insert_movie(Movie(id="partial_backup", title="Files", year=2026))
        self._insert_events([
            self._event(
                "evt_0601",
                "MovieDiscovered",
                {"movie_id": "partial_backup", "id": "partial_backup", "title": "Files", "year": 2026},
                "2026-05-22T00:00:01+00:00",
            ),
            self._event(
                "evt_0602",
                "ArtworkDownloaded",
                {
                    "movie_id": "partial_backup",
                    "asset_type": "poster",
                    "destination": str(poster),
                    "backup_path": str(movie_dir / "missing.backup.jpg"),
                },
                "2026-05-22T00:00:02+00:00",
            ),
        ])

        report = movie_timeline_restore.run(
            movie_id="partial_backup",
            before_event_id="evt_0602",
            restore_fields=[],
            restore_files=["poster"],
            allow_partial=True,
        )

        self.assertEqual(report["status"], "skipped")
        self.assertEqual(report["skipped"][0]["file_type"], "poster")
        self.assertEqual(poster.read_text(), "new poster")

    def test_multiple_overwrites_use_earliest_after_cutoff_backup(self):
        movie_dir = self.media_dir / "Multi"
        movie_dir.mkdir()
        poster = movie_dir / "poster.jpg"
        poster.write_text("latest")
        first_backup = movie_dir / "first.backup.jpg"
        second_backup = movie_dir / "second.backup.jpg"
        first_backup.write_text("historical target")
        second_backup.write_text("intermediate")
        self._insert_movie(Movie(id="multi_backup", title="Files", year=2026))
        self._insert_events([
            self._event(
                "evt_0701",
                "MovieDiscovered",
                {"movie_id": "multi_backup", "id": "multi_backup", "title": "Files", "year": 2026},
                "2026-05-22T00:00:01+00:00",
            ),
            self._event(
                "evt_0702",
                "ArtworkDownloaded",
                {
                    "movie_id": "multi_backup",
                    "asset_type": "poster",
                    "destination": str(poster),
                    "backup_path": str(first_backup),
                },
                "2026-05-22T00:00:02+00:00",
            ),
            self._event(
                "evt_0703",
                "ArtworkDownloaded",
                {
                    "movie_id": "multi_backup",
                    "asset_type": "poster",
                    "destination": str(poster),
                    "backup_path": str(second_backup),
                },
                "2026-05-22T00:00:03+00:00",
            ),
        ])

        report = movie_timeline_restore.run(
            movie_id="multi_backup",
            before_event_id="evt_0702",
            restore_fields=[],
            restore_files=["poster"],
        )

        self.assertEqual(Path(report["restored"][0]["backup_path"]), first_backup.resolve())
        self.assertEqual(poster.read_text(), "historical target")

    def test_timeline_restore_endpoint_smoke_and_errors(self):
        self._insert_movie(Movie(id="route_restore", title="Updated", year=2026))
        self._insert_events([
            self._event(
                "evt_0801",
                "MovieDiscovered",
                {"movie_id": "route_restore", "id": "route_restore", "title": "Original", "year": 2026},
                "2026-05-22T00:00:01+00:00",
            ),
            self._event(
                "evt_0802",
                "MetadataMatched",
                {
                    "movie_id": "route_restore",
                    "changed_fields": ["title"],
                    "previous": {"title": "Original"},
                    "current": {"title": "Updated"},
                },
                "2026-05-22T00:00:02+00:00",
            ),
        ])
        client = TestClient(app)

        success = client.post(
            "/library/route_restore/timeline/restore",
            json={"before_event_id": "evt_0802", "restore_fields": ["title"], "restore_files": []},
        )
        bad_selector = client.post(
            "/library/route_restore/timeline/restore",
            json={"before_event_id": "evt_0802", "at": "2026-05-22T00:00:02+00:00"},
        )
        missing_event = client.post(
            "/library/route_restore/timeline/restore",
            json={"before_event_id": "evt_missing"},
        )

        self.assertEqual(success.status_code, 200, success.text)
        self.assertEqual(success.json()["status"], "restored")
        self.assertEqual(bad_selector.status_code, 400)
        self.assertEqual(missing_event.status_code, 404)

    def _insert_movie(self, movie: Movie):
        with Session(self.engine) as session:
            session.add(movie)
            session.commit()

    def _insert_events(self, events: list[EventRecord]):
        with Session(self.engine) as session:
            session.add_all(events)
            session.commit()

    def _event(self, event_id: str, event_type: str, payload: dict, occurred_at: str) -> EventRecord:
        return EventRecord(
            id=event_id,
            aggregate_type="movie",
            aggregate_id=payload["movie_id"],
            type=event_type,
            payload=payload,
            occurred_at=occurred_at,
        )

    def _movie(self, movie_id: str) -> Movie:
        with Session(self.engine) as session:
            return session.get(Movie, movie_id)

    def _latest_event(self, event_type: str) -> EventRecord | None:
        with Session(self.engine) as session:
            return session.exec(
                select(EventRecord)
                .where(EventRecord.type == event_type)
                .order_by(EventRecord.occurred_at.desc(), EventRecord.id.desc())
            ).first()

    def _counts(self) -> tuple[int, int]:
        with Session(self.engine) as session:
            movie_count = len(session.exec(select(Movie)).all())
            event_count = len(session.exec(select(EventRecord)).all())
        return movie_count, event_count

    def _preview(self, movie_id: str, fields: list[dict]) -> dict:
        return {
            "dry_run": True,
            "movie_id": movie_id,
            "target": {"selector_type": "before_event_id", "before_event_id": "evt_0202", "at": None},
            "current_state": {},
            "target_state": {field["field"]: field["target"] for field in fields},
            "field_diff": fields,
            "events_processed": 1,
            "events_after_cutoff": 1,
            "projectable_events": 1,
            "skipped_projectable_events": 0,
            "unsupported_events": 0,
            "unsupported_event_types": {},
            "skipped_events": [],
            "missing_payload": [],
            "status": "safe",
            "field_restore": fields,
            "file_restore": {"restorable_files": [], "missing_file_backups": [], "unsafe_files": []},
            "restorable_files": [],
            "missing_file_backups": [],
        }


if __name__ == "__main__":
    unittest.main()
