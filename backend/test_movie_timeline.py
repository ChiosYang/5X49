import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, create_engine, select

import app.database as database
import app.services.library as library_module
import app.services.projections.movie_timeline as movie_timeline_module
from app.main import app
from app.models import EventRecord, Movie
from app.services.projections.movie_timeline import movie_timeline_dry_run


class MovieTimelineDryRunTests(unittest.TestCase):
    def setUp(self):
        self._original_database_engine = database.engine
        self._original_library_engine = library_module.engine
        self._original_timeline_engine = movie_timeline_module.engine
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmp.name)
        self.engine = create_engine(f"sqlite:///{self.tmp_path / 'library.db'}")
        database.engine = self.engine
        library_module.engine = self.engine
        movie_timeline_module.engine = self.engine
        SQLModel.metadata.create_all(self.engine)

    def tearDown(self):
        database.engine = self._original_database_engine
        library_module.engine = self._original_library_engine
        movie_timeline_module.engine = self._original_timeline_engine
        self.engine.dispose()
        self._tmp.cleanup()

    def test_before_event_id_replays_state_before_target_event(self):
        self._insert_movie(Movie(id="603_1999", title="Updated", year=1999, tmdb_id="603"))
        metadata_event_id = "evt_0002"
        metadata_event = self._event(
            "evt_0002",
            "MetadataMatched",
            {
                "movie_id": "603_1999",
                "changed_fields": ["title", "tmdb_id"],
                "previous": {"title": "Original", "tmdb_id": None},
                "current": {"title": "Updated", "tmdb_id": "603"},
            },
            "2026-05-22T00:00:02+00:00",
        )
        self._insert_events([
            self._event(
                "evt_0001",
                "MovieDiscovered",
                {"movie_id": "603_1999", "id": "603_1999", "title": "Original", "year": 1999},
                "2026-05-22T00:00:01+00:00",
            ),
            metadata_event,
        ])

        report = movie_timeline_dry_run.state(movie_id="603_1999", before_event_id=metadata_event_id)

        self.assertEqual(report["target"]["cutoff_event"]["id"], metadata_event_id)
        self.assertEqual(report["target_state"]["title"], "Original")
        self.assertEqual(report["events_processed"], 1)
        self.assertIn({"field": "title", "current": "Updated", "target": "Original", "restorable": True}, report["field_diff"])

    def test_at_timestamp_includes_events_at_cutoff(self):
        self._insert_movie(Movie(id="238_1972", title="Updated", year=1972, tmdb_id="238"))
        self._insert_events([
            self._event(
                "evt_0101",
                "MovieDiscovered",
                {"movie_id": "238_1972", "id": "238_1972", "title": "Original", "year": 1972},
                "2026-05-22T00:00:01+00:00",
            ),
            self._event(
                "evt_0102",
                "MetadataMatched",
                {
                    "movie_id": "238_1972",
                    "changed_fields": ["title", "tmdb_id"],
                    "previous": {"title": "Original", "tmdb_id": None},
                    "current": {"title": "Updated", "tmdb_id": "238"},
                },
                "2026-05-22T00:00:02+00:00",
            ),
        ])

        report = movie_timeline_dry_run.state(movie_id="238_1972", at="2026-05-22T00:00:02+00:00")

        self.assertEqual(report["target_state"]["title"], "Updated")
        self.assertEqual(report["target_state"]["tmdb_id"], "238")
        self.assertEqual(report["events_processed"], 2)

    def test_side_effect_events_are_unsupported_during_state_replay(self):
        self._insert_movie(Movie(id="side_effect", title="Current", year=2026))
        cutoff_event_id = "evt_0203"
        cutoff = self._event(
            "evt_0203",
            "MetadataMatched",
            {
                "movie_id": "side_effect",
                "changed_fields": ["title"],
                "previous": {"title": "Current"},
                "current": {"title": "Later"},
            },
            "2026-05-22T00:00:03+00:00",
        )
        self._insert_events([
            self._event(
                "evt_0201",
                "MovieDiscovered",
                {"movie_id": "side_effect", "id": "side_effect", "title": "Current", "year": 2026},
                "2026-05-22T00:00:01+00:00",
            ),
            self._event(
                "evt_0202",
                "ArtworkDownloaded",
                {"movie_id": "side_effect", "asset_type": "poster", "destination": "/media/poster.jpg"},
                "2026-05-22T00:00:02+00:00",
            ),
            cutoff,
        ])

        report = movie_timeline_dry_run.state(movie_id="side_effect", before_event_id=cutoff_event_id)

        self.assertEqual(report["unsupported_event_types"], {"ArtworkDownloaded": 1})
        self.assertEqual(report["unsupported_events"], 1)

    def test_missing_discovered_event_returns_null_target_state(self):
        self._insert_movie(Movie(id="missing_init", title="Current", year=2026))
        self._insert_events([
            self._event(
                "evt_0301",
                "MetadataMatched",
                {
                    "movie_id": "missing_init",
                    "changed_fields": ["title"],
                    "previous": {"title": "Old"},
                    "current": {"title": "Current"},
                },
                "2026-05-22T00:00:01+00:00",
            )
        ])

        report = movie_timeline_dry_run.state(movie_id="missing_init", at="2026-05-22T00:00:02+00:00")

        self.assertIsNone(report["target_state"])
        self.assertEqual(report["skipped_projectable_events"], 1)
        self.assertEqual(report["skipped_events"][0]["reason"], "No projected movie state exists for this event")

    def test_old_payload_without_current_is_skipped(self):
        self._insert_movie(Movie(id="old_payload", title="Current", year=2026))
        self._insert_events([
            self._event(
                "evt_0401",
                "MovieDiscovered",
                {"movie_id": "old_payload", "id": "old_payload", "title": "Original", "year": 2026},
                "2026-05-22T00:00:01+00:00",
            ),
            self._event(
                "evt_0402",
                "MetadataMatched",
                {"movie_id": "old_payload", "updated": True},
                "2026-05-22T00:00:02+00:00",
            ),
        ])

        report = movie_timeline_dry_run.state(movie_id="old_payload", at="2026-05-22T00:00:02+00:00")

        self.assertEqual(report["skipped_projectable_events"], 1)
        self.assertEqual(report["skipped_events"][0]["type"], "MetadataMatched")
        self.assertIn("missing current payload", report["skipped_events"][0]["reason"])
        self.assertEqual(report["missing_payload"][0]["event_id"], "evt_0402")

    def test_restore_preview_reports_existing_and_missing_backups_without_mutation(self):
        self._insert_movie(Movie(id="files", title="Current", year=2026, poster_local="/media/poster.jpg"))
        backup = self.tmp_path / "poster.backup.jpg"
        backup.write_text("old poster")
        cutoff_event_id = "evt_0502"
        cutoff = self._event(
            "evt_0502",
            "ArtworkDownloaded",
            {
                "movie_id": "files",
                "asset_type": "poster",
                "destination": "/media/poster.jpg",
                "backup_path": str(backup),
            },
            "2026-05-22T00:00:02+00:00",
        )
        self._insert_events([
            self._event(
                "evt_0501",
                "MovieDiscovered",
                {"movie_id": "files", "id": "files", "title": "Current", "year": 2026},
                "2026-05-22T00:00:01+00:00",
            ),
            cutoff,
            self._event(
                "evt_0503",
                "NfoWritten",
                {"movie_id": "files", "action": "update", "path": "/media/movie.nfo"},
                "2026-05-22T00:00:03+00:00",
            ),
        ])
        before_counts = self._counts()

        report = movie_timeline_dry_run.restore_preview(movie_id="files", before_event_id=cutoff_event_id)
        after_counts = self._counts()

        self.assertEqual(before_counts, after_counts)
        self.assertEqual(report["status"], "partial")
        self.assertEqual(report["restorable_files"][0]["file_type"], "poster")
        self.assertEqual(report["missing_file_backups"][0]["type"], "NfoWritten")

    def test_timeline_endpoints_smoke(self):
        self._insert_movie(Movie(id="route_smoke", title="Current", year=2026, tmdb_id="1"))
        metadata_event_id = "evt_0602"
        metadata_event = self._event(
            "evt_0602",
            "MetadataMatched",
            {
                "movie_id": "route_smoke",
                "changed_fields": ["title", "tmdb_id"],
                "previous": {"title": "Original", "tmdb_id": None},
                "current": {"title": "Current", "tmdb_id": "1"},
            },
            "2026-05-22T00:00:02+00:00",
        )
        self._insert_events([
            self._event(
                "evt_0601",
                "MovieDiscovered",
                {"movie_id": "route_smoke", "id": "route_smoke", "title": "Original", "year": 2026},
                "2026-05-22T00:00:01+00:00",
            ),
            metadata_event,
        ])
        client = TestClient(app)

        state_response = client.get(f"/library/route_smoke/timeline/state?before_event_id={metadata_event_id}")
        preview_response = client.get(f"/library/route_smoke/timeline/restore-preview?before_event_id={metadata_event_id}")

        self.assertEqual(state_response.status_code, 200, state_response.text)
        self.assertEqual(preview_response.status_code, 200, preview_response.text)
        self.assertTrue(state_response.json()["dry_run"])
        self.assertIn("field_restore", preview_response.json())

    def test_before_event_id_for_another_movie_returns_404_from_route(self):
        self._insert_movie(Movie(id="route_404", title="Current", year=2026))
        self._insert_events([
            self._event(
                "evt_0701",
                "MovieDiscovered",
                {"movie_id": "route_404", "id": "route_404", "title": "Current", "year": 2026},
                "2026-05-22T00:00:01+00:00",
            )
        ])
        client = TestClient(app)

        response = client.get("/library/route_404/timeline/state?before_event_id=evt_missing")

        self.assertEqual(response.status_code, 404)

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

    def _counts(self) -> tuple[int, int]:
        with Session(self.engine) as session:
            movie_count = len(session.exec(select(Movie)).all())
            event_count = len(session.exec(select(EventRecord)).all())
        return movie_count, event_count


if __name__ == "__main__":
    unittest.main()
