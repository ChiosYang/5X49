import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, create_engine, select

import app.database as database
import app.services.library as library_module
import app.services.projections.movie_rebuild as movie_rebuild_module
from app.main import app
from app.models import EventRecord, Movie
from app.services.projections.movie_rebuild import movie_projection_dry_run


class MovieProjectionDryRunTests(unittest.TestCase):
    def setUp(self):
        self._original_database_engine = database.engine
        self._original_library_engine = library_module.engine
        self._original_rebuild_engine = movie_rebuild_module.engine
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmp.name)
        self.engine = create_engine(f"sqlite:///{self.tmp_path / 'library.db'}")
        self._event_index = 0
        database.engine = self.engine
        library_module.engine = self.engine
        movie_rebuild_module.engine = self.engine
        SQLModel.metadata.create_all(self.engine)

    def tearDown(self):
        database.engine = self._original_database_engine
        library_module.engine = self._original_library_engine
        movie_rebuild_module.engine = self._original_rebuild_engine
        self.engine.dispose()
        self._tmp.cleanup()

    def test_empty_replay_projects_metadata_artwork_and_nfo_fields(self):
        with Session(self.engine) as session:
            session.add(Movie(
                id="603_1999",
                title="The Matrix",
                year=1999,
                media_path="/media/The Matrix/The Matrix.mkv",
                folder_path="/media/The Matrix",
                video_file="The Matrix.mkv",
                metadata_source="tmdb",
                scrape_status="matched",
                tmdb_id="603",
                imdb_id="tt0133093",
                runtime=136,
                genres=["Action", "Science Fiction"],
                poster_local="/media/The Matrix/poster.jpg",
                backdrop_local="/media/The Matrix/fanart.jpg",
                poster_path="/poster2.jpg",
                backdrop_path="/backdrop2.jpg",
                metadata_updated_at="2026-05-22T00:00:00+00:00",
                nfo_source="tmdb",
                nfo_file="The Matrix.nfo",
                nfo_path="/media/The Matrix/The Matrix.nfo",
                nfo_size=123,
                nfo_mtime=456.0,
                nfo_fingerprint="abc",
            ))
            session.add_all([
                self._event("MovieDiscovered", {
                    "id": "603_1999",
                    "movie_id": "603_1999",
                    "title": "The Matrix",
                    "year": 1999,
                    "media_path": "/media/The Matrix/The Matrix.mkv",
                    "folder_path": "/media/The Matrix",
                    "video_file": "The Matrix.mkv",
                }),
                self._event("MetadataMatched", {
                    "movie_id": "603_1999",
                    "changed_fields": ["metadata_source", "scrape_status", "tmdb_id", "imdb_id", "runtime", "genres"],
                    "previous": {},
                    "current": {
                        "metadata_source": "tmdb",
                        "scrape_status": "matched",
                        "tmdb_id": "603",
                        "imdb_id": "tt0133093",
                        "runtime": 136,
                        "genres": ["Action", "Science Fiction"],
                    },
                }),
                self._event("ArtworkSelected", {
                    "movie_id": "603_1999",
                    "changed_fields": ["poster_local", "backdrop_local", "poster_path", "backdrop_path", "metadata_updated_at"],
                    "previous": {},
                    "current": {
                        "poster_local": "/media/The Matrix/poster.jpg",
                        "backdrop_local": "/media/The Matrix/fanart.jpg",
                        "poster_path": "/poster2.jpg",
                        "backdrop_path": "/backdrop2.jpg",
                        "metadata_updated_at": "2026-05-22T00:00:00+00:00",
                    },
                }),
                self._event("MovieMetadataParsedFromNfo", {
                    "movie_id": "603_1999",
                    "nfo_source": "tmdb",
                    "changed_fields": ["nfo_file", "nfo_path", "nfo_size", "nfo_mtime", "nfo_fingerprint"],
                    "previous": {},
                    "current": {
                        "nfo_file": "The Matrix.nfo",
                        "nfo_path": "/media/The Matrix/The Matrix.nfo",
                        "nfo_size": 123,
                        "nfo_mtime": 456.0,
                        "nfo_fingerprint": "abc",
                    },
                }),
            ])
            session.commit()

        report = movie_projection_dry_run.run(movie_id="603_1999", base="empty")

        self.assertEqual(report["movies_compared"], 1)
        self.assertEqual(report["skipped_projectable_events"], 0)
        self.assertEqual(report["differences"], [])
        self.assertTrue(report["confirmation_token"])
        self.assertFalse(report["event_stream_truncated"])
        self.assertEqual(report["last_event"]["type"], "MovieMetadataParsedFromNfo")
        self.assertEqual(report["projected_state"]["title"], "The Matrix")

    def test_external_scores_refreshed_projects_new_payload(self):
        score = {"source": "tspdt", "kind": "rank", "rank": 6}
        with Session(self.engine) as session:
            session.add(Movie(
                id="238_1972",
                title="The Godfather",
                year=1972,
                external_scores=[score],
                external_scores_updated_at="2026-05-22T00:00:00+00:00",
            ))
            session.add_all([
                self._event("MovieDiscovered", {"id": "238_1972", "movie_id": "238_1972", "title": "The Godfather", "year": 1972}),
                self._event("ExternalScoresRefreshed", {
                    "movie_id": "238_1972",
                    "changed_fields": ["external_scores", "external_scores_updated_at"],
                    "previous": {"external_scores": None, "external_scores_updated_at": None},
                    "current": {
                        "external_scores": [score],
                        "external_scores_updated_at": "2026-05-22T00:00:00+00:00",
                        "external_scores_error": None,
                    },
                }),
            ])
            session.commit()

        report = movie_projection_dry_run.run(movie_id="238_1972", base="empty")

        self.assertEqual(report["skipped_projectable_events"], 0)
        self.assertEqual(report["differences"], [])

    def test_external_scores_refreshed_old_payload_is_skipped(self):
        with Session(self.engine) as session:
            session.add(Movie(id="238_1972", title="The Godfather", year=1972))
            session.add_all([
                self._event("MovieDiscovered", {"id": "238_1972", "movie_id": "238_1972", "title": "The Godfather", "year": 1972}),
                self._event("ExternalScoresRefreshed", {
                    "movie_id": "238_1972",
                    "updated_sources": ["tspdt"],
                    "skipped_sources": [],
                }),
            ])
            session.commit()

        report = movie_projection_dry_run.run(movie_id="238_1972", base="empty")

        self.assertEqual(report["skipped_projectable_events"], 1)
        self.assertEqual(report["skipped_events"][0]["type"], "ExternalScoresRefreshed")
        self.assertIn("missing current payload", report["skipped_events"][0]["reason"])

    def test_restored_events_still_project_fields(self):
        with Session(self.engine) as session:
            session.add(Movie(id="local_1", title="Original", year=2026, poster_path="/old.jpg"))
            session.add_all([
                self._event("MovieDiscovered", {"id": "local_1", "movie_id": "local_1", "title": "Changed", "year": 2026}),
                self._event("MetadataRestored", {
                    "movie_id": "local_1",
                    "restored_fields": [{"field": "title", "restored": "Original"}],
                }),
                self._event("ArtworkSelectionRestored", {
                    "movie_id": "local_1",
                    "restored_fields": [{"field": "poster_path", "restored": "/old.jpg"}],
                }),
            ])
            session.commit()

        report = movie_projection_dry_run.run(movie_id="local_1", base="empty")

        self.assertEqual(report["differences"], [])

    def test_rebuild_requires_single_movie_empty_base_and_token(self):
        with Session(self.engine) as session:
            session.add(Movie(id="rebuild_rules", title="Current", year=2026))
            session.add(self._event("MovieDiscovered", {
                "id": "rebuild_rules",
                "movie_id": "rebuild_rules",
                "title": "Projected",
                "year": 2026,
            }))
            session.commit()

        with self.assertRaises(ValueError):
            movie_projection_dry_run.run(dry_run=False, base="empty")
        with self.assertRaises(ValueError):
            movie_projection_dry_run.run(dry_run=False, movie_id="rebuild_rules", base="current")
        with self.assertRaises(ValueError):
            movie_projection_dry_run.run(dry_run=False, movie_id="rebuild_rules", base="empty", since="2026-01-01T00:00:00+00:00")
        with self.assertRaises(ValueError):
            movie_projection_dry_run.run(dry_run=False, movie_id="rebuild_rules", base="empty")
        with self.assertRaises(ValueError):
            movie_projection_dry_run.run(dry_run=False, movie_id="rebuild_rules", base="empty", confirmation_token="bad")

        with Session(self.engine) as session:
            movie = session.get(Movie, "rebuild_rules")
        self.assertEqual(movie.title, "Current")

    def test_rebuild_blocks_when_projectable_events_are_skipped(self):
        with Session(self.engine) as session:
            session.add(Movie(id="blocked", title="Current", year=2026))
            session.add_all([
                self._event("MovieDiscovered", {
                    "id": "blocked",
                    "movie_id": "blocked",
                    "title": "Current",
                    "year": 2026,
                }),
                self._event("ExternalScoresRefreshed", {
                    "movie_id": "blocked",
                    "updated_sources": ["tspdt"],
                }),
            ])
            session.commit()

        report = movie_projection_dry_run.run(movie_id="blocked", base="empty")

        with self.assertRaises(ValueError):
            movie_projection_dry_run.run(
                dry_run=False,
                movie_id="blocked",
                base="empty",
                confirmation_token=report["confirmation_token"],
            )

        with Session(self.engine) as session:
            movie = session.get(Movie, "blocked")
        self.assertEqual(movie.title, "Current")

    def test_rebuild_single_movie_replaces_core_fields_and_appends_audit_event(self):
        with Session(self.engine) as session:
            session.add(Movie(
                id="rebuild_success",
                title="Current",
                year=2026,
                tmdb_id="old",
                poster_path="/old.jpg",
            ))
            session.add_all([
                self._event("MovieDiscovered", {
                    "id": "rebuild_success",
                    "movie_id": "rebuild_success",
                    "title": "Projected",
                    "year": 2026,
                }),
                self._event("MetadataMatched", {
                    "movie_id": "rebuild_success",
                    "current": {"tmdb_id": "new"},
                }),
            ])
            session.commit()

        dry_run = movie_projection_dry_run.run(movie_id="rebuild_success", base="empty")
        result = movie_projection_dry_run.run(
            dry_run=False,
            movie_id="rebuild_success",
            base="empty",
            confirmation_token=dry_run["confirmation_token"],
        )

        self.assertEqual(result["status"], "rebuilt")
        self.assertIn("title", result["fields_replaced"])
        self.assertIn("tmdb_id", result["fields_replaced"])
        self.assertIn("poster_path", result["fields_replaced"])
        with Session(self.engine) as session:
            movie = session.get(Movie, "rebuild_success")
            audit_event = session.exec(select(EventRecord).where(EventRecord.type == "MovieProjectionRebuilt")).one()
        self.assertEqual(movie.title, "Projected")
        self.assertEqual(movie.tmdb_id, "new")
        self.assertIsNone(movie.poster_path)
        self.assertEqual(audit_event.aggregate_type, "projection")
        self.assertEqual(audit_event.payload["confirmation_token"], dry_run["confirmation_token"])
        self.assertEqual(audit_event.payload["after"]["title"], "Projected")

        after_report = movie_projection_dry_run.run(movie_id="rebuild_success", base="empty")
        self.assertEqual(after_report["movies_with_differences"], 0)

    def test_rebuild_endpoint_smoke(self):
        with Session(self.engine) as session:
            session.add(Movie(id="route_rebuild", title="Current", year=2026))
            session.add(self._event("MovieDiscovered", {
                "id": "route_rebuild",
                "movie_id": "route_rebuild",
                "title": "Projected",
                "year": 2026,
            }))
            session.commit()
        client = TestClient(app)

        dry_run_response = client.post("/library/projections/movie/rebuild?movie_id=route_rebuild&base=empty")
        self.assertEqual(dry_run_response.status_code, 200, dry_run_response.text)
        token = dry_run_response.json()["confirmation_token"]

        success = client.post(f"/library/projections/movie/rebuild?dry_run=false&movie_id=route_rebuild&base=empty&confirmation_token={token}")
        missing_movie_id = client.post("/library/projections/movie/rebuild?dry_run=false&base=empty")
        wrong_base = client.post(f"/library/projections/movie/rebuild?dry_run=false&movie_id=route_rebuild&base=current&confirmation_token={token}")
        missing_movie = client.post("/library/projections/movie/rebuild?movie_id=missing_route")
        missing_token = client.post("/library/projections/movie/rebuild?dry_run=false&movie_id=route_rebuild&base=empty")
        bad_token = client.post("/library/projections/movie/rebuild?dry_run=false&movie_id=route_rebuild&base=empty&confirmation_token=bad")

        self.assertEqual(success.status_code, 200, success.text)
        self.assertEqual(success.json()["status"], "rebuilt")
        self.assertEqual(missing_movie_id.status_code, 400)
        self.assertEqual(wrong_base.status_code, 400)
        self.assertEqual(missing_movie.status_code, 404)
        self.assertEqual(missing_token.status_code, 409)
        self.assertEqual(bad_token.status_code, 409)

    def _event(self, event_type: str, payload: dict) -> EventRecord:
        self._event_index += 1
        return EventRecord(
            aggregate_type="movie",
            aggregate_id=payload["movie_id"],
            type=event_type,
            payload=payload,
            occurred_at=f"2026-05-22T00:00:{self._event_index:02d}+00:00",
        )


if __name__ == "__main__":
    unittest.main()
