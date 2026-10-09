import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

from sqlmodel import Session, create_engine, select

import app.database as database
import app.services.event_store as event_store_module
import app.services.library as library_module
import app.services.operation_snapshots as snapshot_module
from app.canonical_models import Assertion, Credit, ExternalIdentity, FilmCountry, OperationSnapshot
from app.database import configure_sqlite_engine
from app.migrations.runner import run_migrations
from app.models import EventRecord, Job, WorkflowRun
from app.services.library import library_manager
from app.services.library_sync import library_sync_service
from app.services.metadata.models import ArtworkSelection, ScrapeOptions
from app.services.metadata.scraper import metadata_scraper
from app.services.operation_snapshots import operation_snapshot_service


class MetadataScraperIntegrationTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        database_path = self.root / "library.db"
        self.engine = create_engine(f"sqlite:///{database_path}")
        configure_sqlite_engine(self.engine)
        run_migrations(self.engine, database_path, app_version="test", backup_required=False)
        self.modules = (database, event_store_module, library_module, snapshot_module)
        self.original = {module: module.engine for module in self.modules}
        for module in self.modules:
            module.engine = self.engine
        self.movie_dir = self.root / "The.Matrix.1999"
        self.movie_dir.mkdir()
        self.video = self.movie_dir / "The.Matrix.1999.1080p.mkv"
        self.video.write_bytes(b"fake video")

    def tearDown(self):
        for module, engine in self.original.items():
            module.engine = engine
        self.engine.dispose()
        self._tmp.cleanup()

    def test_scrape_film_writes_canonical_metadata_assertions_and_bounded_event(self):
        film = library_sync_service.scan_folder(self.movie_dir)
        self.assertEqual(film["primary_item"]["metadata"]["source"], "filename")

        def fake_download(url, destination, overwrite=False):
            destination.write_bytes(url.encode("utf-8"))
            return destination

        with (
            patch("app.services.metadata.scraper.get_scrape_require_confirmation", return_value=False),
            patch.object(metadata_scraper.tmdb, "search_movies", return_value=[self._candidate()]),
            patch.object(metadata_scraper.tmdb, "movie_details", return_value=self._details()),
            patch.object(metadata_scraper.artwork, "download", side_effect=fake_download),
        ):
            result = metadata_scraper.scrape_film(film["id"], ScrapeOptions())

        self.assertEqual(result.status, "success")
        refreshed = library_manager.get_film(film["id"])
        self.assertEqual(refreshed["identities"]["tmdb"], "603")
        self.assertEqual(refreshed["identities"]["imdb"], "tt0133093")
        self.assertEqual(refreshed["genres"], ["Action", "Science Fiction"])
        self.assertEqual(refreshed["countries"], ["US"])
        nfo_path = self.movie_dir / "The.Matrix.1999.1080p.nfo"
        self.assertTrue(nfo_path.exists())
        root = ET.parse(nfo_path).getroot()
        self.assertEqual(root.findtext("title"), "The Matrix")
        self.assertEqual(root.find("director").get("tmdbid"), "9340")
        with Session(self.engine) as session:
            self.assertEqual(len(session.exec(select(Credit)).all()), 2)
            self.assertEqual(len(session.exec(select(FilmCountry)).all()), 1)
            self.assertEqual(len(session.exec(select(Assertion).where(Assertion.predicate == "HAS_GENRE")).all()), 2)
            self.assertEqual(len(session.exec(select(ExternalIdentity).where(ExternalIdentity.provider == "tmdb.person")).all()), 2)
            event = session.exec(select(EventRecord).where(EventRecord.type == "MetadataMatched")).one()
            snapshot = session.exec(
                select(OperationSnapshot).where(OperationSnapshot.event_id == event.id)
            ).one()
            snapshot_id = snapshot.id
        self.assertNotIn("structured_metadata", event.payload)
        self.assertNotIn(str(self.movie_dir.resolve()), str(event.payload))
        self.assertEqual(snapshot.operation_kind, "metadata")
        preview = operation_snapshot_service.preview(snapshot_id)
        self.assertEqual(preview["before"]["library_items"][0]["metadata_source"], "filename")
        self.assertEqual(preview["after"]["library_items"][0]["metadata_source"], "tmdb")
        restored = operation_snapshot_service.restore(snapshot_id, preview["confirmation_token"])
        self.assertEqual(restored["status"], "restored")
        self.assertEqual(
            library_manager.get_film(film["id"])["primary_item"]["metadata"]["source"],
            "filename",
        )

    def test_scrape_confirmation_does_not_mutate_metadata(self):
        film = library_sync_service.scan_folder(self.movie_dir)
        with (
            patch("app.services.metadata.scraper.get_scrape_require_confirmation", return_value=True),
            patch.object(metadata_scraper.tmdb, "search_movies", return_value=[self._candidate()]),
            patch.object(metadata_scraper.tmdb, "movie_details") as details,
        ):
            result = metadata_scraper.scrape_film(film["id"], ScrapeOptions())
        self.assertEqual(result.status, "needs_review")
        details.assert_not_called()
        refreshed = library_manager.get_film(film["id"])
        self.assertEqual(refreshed["primary_item"]["metadata"]["scrape_status"], "needs_review")
        self.assertIsNone(refreshed["primary_item"]["metadata"]["scrape_error"])

    def test_two_prescanned_versions_confirm_into_one_film_and_update_the_correct_item(self):
        second_folder = self.root / "The.Matrix.1999.Directors.Cut"
        second_folder.mkdir()
        (second_folder / "The.Matrix.1999.Directors.Cut.mkv").write_bytes(b"different version")
        originals = [library_sync_service.scan_folder(folder) for folder in (self.movie_dir, second_folder)]
        item_ids = {film["primary_item"]["id"] for film in originals}
        with patch.object(metadata_scraper.tmdb, "movie_details", return_value=self._details()):
            for film in originals:
                result = metadata_scraper.scrape_film(film["id"], ScrapeOptions(tmdb_id=603, download_artwork=False))
                self.assertEqual(result.status, "success", result.message)
                self.assertEqual(result.film_id, originals[0]["id"])
        films = library_manager.list_films()
        self.assertEqual(len(films), 1)
        detail = library_manager.get_film(originals[1]["id"])
        self.assertEqual(detail["identities"], {"tmdb": "603", "imdb": "tt0133093"})
        self.assertEqual({edition["id"] for edition in detail["editions"]}, item_ids)
        for edition in detail["editions"]:
            self.assertEqual(edition["metadata"]["scrape_status"], "matched")
            self.assertIsNotNone(edition["metadata"]["scraped_at"])
            self.assertEqual(edition["metadata"]["match_confidence"], 100)
        for folder in (self.movie_dir, second_folder):
            library_sync_service.scan_folder(folder)
        self.engine.dispose()
        restored = library_manager.get_film(originals[1]["id"])
        self.assertEqual({item["id"] for item in restored["editions"]}, item_ids)
        before = {item["id"]: item["metadata"] for item in detail["editions"]}
        for item in restored["editions"]:
            for field in ("scrape_status", "scrape_error", "scraped_at", "match_confidence"):
                self.assertEqual(item["metadata"][field], before[item["id"]][field])
        with Session(self.engine) as session:
            snapshot = session.exec(
                select(OperationSnapshot).where(OperationSnapshot.aggregate_id == originals[0]["id"])
                .order_by(OperationSnapshot.created_at.desc())
            ).first()
        preview = operation_snapshot_service.preview(snapshot.id)
        self.assertEqual({item["id"] for item in preview["before"]["library_items"]}, item_ids)
        self.assertEqual(preview["before"]["film"]["canonical_title"], detail["title"])

    def test_no_results_are_failed_without_metadata_writes_and_survive_rescan(self):
        film = library_sync_service.scan_folder(self.movie_dir)
        with (
            patch.object(metadata_scraper.tmdb, "search_movies", return_value=[]),
            patch.object(metadata_scraper.tmdb, "movie_details") as details,
        ):
            result = metadata_scraper.scrape_film(film["id"], ScrapeOptions())
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.message, "No TMDB matches found")
        details.assert_not_called()
        self.assertEqual(list(self.movie_dir.glob("*.nfo")), [])
        library_sync_service.scan_folder(self.movie_dir)
        self.engine.dispose()
        metadata = library_manager.get_film(film["id"])["primary_item"]["metadata"]
        self.assertEqual(metadata["scrape_status"], "failed")
        self.assertEqual(metadata["scrape_error"], "No TMDB matches found")

    def test_identity_conflicts_fail_before_writing_nfo_or_artwork(self):
        film = library_sync_service.scan_folder(self.movie_dir)
        library_manager.update_film_observation(film["id"], {"tmdb_id": "604"})
        with (
            patch.object(metadata_scraper.tmdb, "movie_details", return_value=self._details()),
            patch.object(metadata_scraper.artwork, "download") as download,
        ):
            result = metadata_scraper.scrape_film(film["id"], ScrapeOptions(tmdb_id=603))
        self.assertEqual(result.status, "failed")
        self.assertIn("identity review required", result.message)
        download.assert_not_called()
        self.assertEqual(list(self.movie_dir.glob("*.nfo")), [])
        self.assertEqual(library_manager.get_film(film["id"])["identities"]["tmdb"], "604")

    def test_candidate_lookup_is_bounded_and_does_not_mutate_library_state(self):
        film = library_sync_service.scan_folder(self.movie_dir)
        before = library_manager.get_film(film["id"])
        media_before = {
            path.name: path.read_bytes()
            for path in self.movie_dir.iterdir()
            if path.is_file()
        }
        with Session(self.engine) as session:
            event_count = len(session.exec(select(EventRecord)).all())
            snapshot_count = len(session.exec(select(OperationSnapshot)).all())
            job_count = len(session.exec(select(Job)).all())
            workflow_count = len(session.exec(select(WorkflowRun)).all())

        candidates = [
            {
                **self._candidate(),
                "id": index + 1,
                "title": f"Candidate {index + 1}",
            }
            for index in range(25)
        ]
        with patch.object(metadata_scraper.tmdb, "search_movies", return_value=candidates) as search:
            result = metadata_scraper.candidates_for_film(film["id"], language="en-US")

        self.assertEqual(len(result), 20)
        search.assert_any_call("The Matrix", year=1999, language="en-US")
        self.assertEqual(library_manager.get_film(film["id"]), before)
        self.assertEqual(
            {
                path.name: path.read_bytes()
                for path in self.movie_dir.iterdir()
                if path.is_file()
            },
            media_before,
        )
        with Session(self.engine) as session:
            self.assertEqual(len(session.exec(select(EventRecord)).all()), event_count)
            self.assertEqual(len(session.exec(select(OperationSnapshot)).all()), snapshot_count)
            self.assertEqual(len(session.exec(select(Job)).all()), job_count)
            self.assertEqual(len(session.exec(select(WorkflowRun)).all()), workflow_count)

    def test_candidate_lookup_rejects_missing_or_unavailable_films(self):
        with self.assertRaises(LookupError):
            metadata_scraper.candidates_for_film("film_" + "a" * 32)

        film = library_sync_service.scan_folder(self.movie_dir)
        with patch.object(
            library_manager,
            "get_film_operation_context",
            return_value={
                "id": film["id"],
                "library_status": "missing",
                "media_path": str(self.video),
            },
        ), self.assertRaisesRegex(ValueError, "available media edition"):
            metadata_scraper.candidates_for_film(film["id"])

    def test_artwork_selection_updates_canonical_edition(self):
        film = library_sync_service.scan_folder(self.movie_dir)
        library_manager.update_film_observation(
            film["id"],
            {"tmdb_id": "603", "metadata_source": "tmdb", "scrape_status": "matched"},
        )

        def fake_download(url, destination, overwrite=False):
            destination.write_bytes(url.encode("utf-8"))
            return destination

        details = self._details()
        details["images"] = {
            "posters": [{"file_path": "/poster-new.jpg"}],
            "backdrops": [{"file_path": "/backdrop-new.jpg"}],
        }
        with (
            patch.object(metadata_scraper.tmdb, "movie_details", return_value=details),
            patch.object(metadata_scraper.artwork, "download", side_effect=fake_download),
        ):
            result = metadata_scraper.apply_artwork(
                film["id"],
                ArtworkSelection(poster_path="/poster-new.jpg", backdrop_path="/backdrop-new.jpg"),
            )
        self.assertEqual(result["status"], "success")
        artwork = result["film"]["primary_item"]["artwork"]
        self.assertEqual(artwork["poster_provider"], "/poster-new.jpg")
        self.assertEqual(artwork["backdrop_provider"], "/backdrop-new.jpg")
        with Session(self.engine) as session:
            snapshot = session.exec(
                select(OperationSnapshot).where(OperationSnapshot.operation_kind == "artwork")
            ).one()
            snapshot_id = snapshot.id
        preview = operation_snapshot_service.preview(snapshot_id)
        operation_snapshot_service.restore(snapshot_id, preview["confirmation_token"])
        restored_artwork = library_manager.get_film(film["id"])["primary_item"]["artwork"]
        self.assertIsNone(restored_artwork["poster_provider"])
        self.assertIsNone(restored_artwork["backdrop_provider"])

    @staticmethod
    def _candidate():
        return {
            "id": 603,
            "title": "The Matrix",
            "original_title": "The Matrix",
            "release_date": "1999-03-31",
            "overview": "A hacker discovers reality.",
            "poster_path": "/matrix-poster.jpg",
            "backdrop_path": "/matrix-backdrop.jpg",
            "popularity": 100,
        }

    @staticmethod
    def _details():
        return {
            "id": 603,
            "title": "The Matrix",
            "original_title": "The Matrix",
            "original_language": "en",
            "release_date": "1999-03-31",
            "overview": "A hacker discovers reality.",
            "runtime": 136,
            "poster_path": "/matrix-poster.jpg",
            "backdrop_path": "/matrix-backdrop.jpg",
            "external_ids": {"imdb_id": "tt0133093"},
            "genres": [{"id": 28, "name": "Action"}, {"id": 878, "name": "Science Fiction"}],
            "production_countries": [{"iso_3166_1": "US", "name": "United States"}],
            "credits": {
                "crew": [{"id": 9340, "job": "Director", "name": "Lana Wachowski"}],
                "cast": [{"id": 6384, "name": "Keanu Reeves", "character": "Neo", "order": 0}],
            },
        }


if __name__ == "__main__":
    unittest.main()
