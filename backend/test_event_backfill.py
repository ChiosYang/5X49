import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, create_engine, select

import app.database as database
import app.services.event_backfill as event_backfill_module
import app.services.library as library_module
import app.services.projections.movie_rebuild as movie_rebuild_module
from app.main import app
from app.models import EventRecord, Movie
from app.services.event_backfill import movie_replay_backfill
from app.services.projections.movie_rebuild import movie_projection_dry_run


class MovieReplayBackfillTests(unittest.TestCase):
    def setUp(self):
        self._original_database_engine = database.engine
        self._original_library_engine = library_module.engine
        self._original_backfill_engine = event_backfill_module.engine
        self._original_rebuild_engine = movie_rebuild_module.engine
        self._original_media_dir_env = os.environ.get("MEDIA_DIR")
        self._original_get_media_dir = event_backfill_module.get_media_dir
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmp.name)
        self.media_dir = self.tmp_path / "media"
        self.media_dir.mkdir()
        self.engine = create_engine(f"sqlite:///{self.tmp_path / 'library.db'}")
        database.engine = self.engine
        library_module.engine = self.engine
        event_backfill_module.engine = self.engine
        movie_rebuild_module.engine = self.engine
        os.environ["MEDIA_DIR"] = str(self.media_dir)
        event_backfill_module.get_media_dir = lambda: str(self.media_dir)
        SQLModel.metadata.create_all(self.engine)

    def tearDown(self):
        database.engine = self._original_database_engine
        library_module.engine = self._original_library_engine
        event_backfill_module.engine = self._original_backfill_engine
        movie_rebuild_module.engine = self._original_rebuild_engine
        event_backfill_module.get_media_dir = self._original_get_media_dir
        if self._original_media_dir_env is None:
            os.environ.pop("MEDIA_DIR", None)
        else:
            os.environ["MEDIA_DIR"] = self._original_media_dir_env
        self.engine.dispose()
        self._tmp.cleanup()

    def test_dry_run_reports_missing_movie_discovered_without_writing(self):
        self._insert_movie(Movie(id="missing_init", title="No Init", year=2026))

        report = movie_replay_backfill.run(movie_id="missing_init", dry_run=True)

        self.assertEqual(report["events_to_create"], 1)
        self.assertEqual(report["sample_events"][0]["type"], "MovieDiscovered")
        self.assertEqual(report["sample_events"][0]["context"]["source"], "backfill")
        self.assertEqual(self._event_count(), 0)

    def test_execute_creates_movie_discovered_without_changing_movie(self):
        self._insert_movie(Movie(id="execute_init", title="Current", year=2026, tmdb_id="1"))

        report = movie_replay_backfill.run(movie_id="execute_init", dry_run=False)

        self.assertEqual(report["created_events"], 1)
        with Session(self.engine) as session:
            movie = session.get(Movie, "execute_init")
            event = session.exec(select(EventRecord)).one()
        self.assertEqual(movie.title, "Current")
        self.assertEqual(movie.tmdb_id, "1")
        self.assertEqual(event.type, "MovieDiscovered")
        self.assertEqual(event.actor_type, "migration")
        self.assertEqual(event.context["source"], "backfill")

    def test_old_metadata_and_artwork_payloads_generate_projectable_state_snapshot(self):
        self._insert_movie(Movie(
            id="old_payload",
            title="Current Title",
            year=1999,
            tmdb_id="603",
            poster_path="/poster.jpg",
        ))
        self._insert_events([
            self._event("evt_0001", "MovieDiscovered", {
                "movie_id": "old_payload",
                "id": "old_payload",
                "title": "Old Title",
                "year": 1999,
            }),
            self._event("evt_0002", "MetadataMatched", {
                "movie_id": "old_payload",
                "tmdb_id": "603",
                "title": "Current Title",
            }),
            self._event("evt_0003", "ArtworkSelected", {
                "movie_id": "old_payload",
                "poster_path": "/poster.jpg",
            }),
        ])

        dry_run = movie_replay_backfill.run(movie_id="old_payload", dry_run=True)
        state_specs = [item for item in dry_run["sample_events"] if item["type"] == "MovieStateBackfilled"]
        self.assertEqual(len(state_specs), 1)
        self.assertEqual(state_specs[0]["payload"]["current"]["title"], "Current Title")
        self.assertEqual(set(state_specs[0]["payload"]["source_event_types"]), {"ArtworkSelected", "MetadataMatched"})

        movie_replay_backfill.run(movie_id="old_payload", dry_run=False)
        replay = movie_projection_dry_run.run(movie_id="old_payload", base="empty")
        self.assertEqual(replay["differences"], [])

    def test_backfill_is_idempotent(self):
        self._insert_movie(Movie(id="idempotent", title="Current", year=2026))

        first = movie_replay_backfill.run(movie_id="idempotent", dry_run=False)
        second = movie_replay_backfill.run(movie_id="idempotent", dry_run=False)

        self.assertEqual(first["created_events"], 1)
        self.assertEqual(second["created_events"], 0)
        self.assertEqual(self._event_count(), 1)

    def test_file_snapshot_backfill_records_existing_files_and_reports_unavailable(self):
        movie_dir = self.media_dir / "Movie"
        movie_dir.mkdir()
        poster = movie_dir / "poster.jpg"
        nfo = movie_dir / "Movie.nfo"
        poster.write_text("poster")
        nfo.write_text("<movie />")
        self._insert_movie(Movie(
            id="files",
            title="Files",
            year=2026,
            folder_path="/media/Movie",
            poster_local="/media/Movie/poster.jpg",
            backdrop_local="/outside/backdrop.jpg",
            nfo_file="Movie.nfo",
        ))

        report = movie_replay_backfill.run(movie_id="files", dry_run=True)

        file_specs = [item for item in report["sample_events"] if item["type"] == "MovieFileSnapshotBackfilled"]
        self.assertEqual({item["payload"]["file_type"] for item in file_specs}, {"poster", "nfo"})
        self.assertTrue(all(item["payload"]["restore_available"] is False for item in file_specs))
        self.assertEqual(report["unavailable_file_snapshots"][0]["file_type"], "backdrop")
        self.assertIn("outside MEDIA_DIR", report["unavailable_file_snapshots"][0]["reason"])

    def test_endpoint_smoke(self):
        self._insert_movie(Movie(id="route_backfill", title="Route", year=2026))
        client = TestClient(app)

        success = client.post("/library/events/backfill/movie-replay?movie_id=route_backfill")
        invalid = client.post("/library/events/backfill/movie-replay?movie_id=bad id")
        missing = client.post("/library/events/backfill/movie-replay?movie_id=missing_movie")

        self.assertEqual(success.status_code, 200, success.text)
        self.assertTrue(success.json()["dry_run"])
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(missing.status_code, 404)

    def _insert_movie(self, movie: Movie):
        with Session(self.engine) as session:
            session.add(movie)
            session.commit()

    def _insert_events(self, events: list[EventRecord]):
        with Session(self.engine) as session:
            session.add_all(events)
            session.commit()

    def _event(self, event_id: str, event_type: str, payload: dict) -> EventRecord:
        return EventRecord(
            id=event_id,
            aggregate_type="movie",
            aggregate_id=payload.get("movie_id"),
            type=event_type,
            payload=payload,
            occurred_at=f"2026-05-22T00:00:{event_id[-1]}0+00:00",
        )

    def _event_count(self) -> int:
        with Session(self.engine) as session:
            return len(session.exec(select(EventRecord)).all())


if __name__ == "__main__":
    unittest.main()
