import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from sqlmodel import SQLModel, Session, create_engine, select

import app.database as database
import app.services.event_store as event_store_module
import app.services.library as library_module
from app.models import EventRecord
from app.services.library import library_manager
from app.services.library_sync import library_sync_service
from app.services.metadata.models import ArtworkSelection, RootOrganizeOptions, ScrapeOptions
from app.services.metadata.organizer import root_video_organizer
from app.services.metadata.scraper import metadata_scraper


class MetadataScraperIntegrationTests(unittest.TestCase):
    def setUp(self):
        self._original_database_engine = database.engine
        self._original_event_store_engine = event_store_module.engine
        self._original_library_engine = library_module.engine
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmp.name)
        self.engine = create_engine(f"sqlite:///{self.tmp_path / 'library.db'}")
        database.engine = self.engine
        event_store_module.engine = self.engine
        library_module.engine = self.engine
        SQLModel.metadata.create_all(self.engine)

    def tearDown(self):
        database.engine = self._original_database_engine
        event_store_module.engine = self._original_event_store_engine
        library_module.engine = self._original_library_engine
        self.engine.dispose()
        self._tmp.cleanup()

    def test_scrape_movie_writes_nfo_artwork_and_updates_library(self):
        movie_dir = self.tmp_path / "The.Matrix.1999"
        movie_dir.mkdir()
        video = movie_dir / "The.Matrix.1999.1080p.mkv"
        video.write_bytes(b"fake video")

        movie = library_sync_service.scan_folder(movie_dir)
        self.assertIsNotNone(movie)
        self.assertEqual(movie["metadata_source"], "filename")
        self.assertEqual(movie["scrape_status"], "pending")

        def fake_download(url, destination, overwrite=False):
            destination.write_bytes(f"downloaded {url}".encode("utf-8"))
            return destination

        with (
            patch("app.services.metadata.scraper.get_scrape_require_confirmation", return_value=False),
            patch.object(metadata_scraper.tmdb, "search_movies") as search_movies,
            patch.object(metadata_scraper.tmdb, "movie_details") as movie_details,
            patch.object(metadata_scraper.artwork, "download", side_effect=fake_download) as download,
        ):
            search_movies.return_value = [
                {
                    "id": 603,
                    "title": "The Matrix",
                    "original_title": "The Matrix",
                    "release_date": "1999-03-31",
                    "overview": "A computer hacker learns about the true nature of reality.",
                    "poster_path": "/matrix-poster.jpg",
                    "backdrop_path": "/matrix-backdrop.jpg",
                    "popularity": 100,
                }
            ]
            movie_details.return_value = {
                "id": 603,
                "title": "The Matrix",
                "original_title": "The Matrix",
                "release_date": "1999-03-31",
                "overview": "A computer hacker learns about the true nature of reality.",
                "runtime": 136,
                "poster_path": "/matrix-poster.jpg",
                "backdrop_path": "/matrix-backdrop.jpg",
                "external_ids": {"imdb_id": "tt0133093"},
                "genres": [{"name": "Action"}, {"name": "Science Fiction"}],
                "production_countries": [{"name": "United States of America"}],
                "credits": {
                    "crew": [{"job": "Director", "name": "Lana Wachowski"}],
                    "cast": [{"name": "Keanu Reeves", "character": "Neo"}],
                },
            }

            with patch("app.services.metadata.scraper.library_manager.upsert_movie") as upsert_movie:
                result = metadata_scraper.scrape_movie(movie["id"], ScrapeOptions())

        self.assertEqual(result.status, "success")
        upsert_movie.assert_not_called()
        self.assertEqual(download.call_count, 2)

        nfo_path = movie_dir / "The.Matrix.1999.1080p.nfo"
        poster_path = movie_dir / "The.Matrix.1999.1080p-poster.jpg"
        fanart_path = movie_dir / "The.Matrix.1999.1080p-fanart.jpg"
        self.assertTrue(nfo_path.exists())
        self.assertTrue(poster_path.exists())
        self.assertTrue(fanart_path.exists())

        nfo_text = nfo_path.read_text(encoding="utf-8")
        self.assertIn("<title>The Matrix</title>", nfo_text)
        self.assertIn("<tmdbid>603</tmdbid>", nfo_text)
        self.assertIn("<id>tt0133093</id>", nfo_text)
        self.assertIn("<director>Lana Wachowski</director>", nfo_text)

        stored = library_manager.get_movie(movie["id"])
        self.assertIsNotNone(stored)
        self.assertEqual(stored["metadata_source"], "tmdb")
        self.assertEqual(stored["nfo_source"], "tmdb")
        self.assertEqual(stored["scrape_status"], "matched")
        self.assertEqual(stored["tmdb_id"], "603")
        self.assertEqual(stored["imdb_id"], "tt0133093")
        self.assertEqual(stored["runtime"], 136)
        self.assertEqual(stored["genres"], ["Action", "Science Fiction"])
        self.assertEqual(stored["poster_local"], "/media/The.Matrix.1999/The.Matrix.1999.1080p-poster.jpg")
        self.assertEqual(stored["backdrop_local"], "/media/The.Matrix.1999/The.Matrix.1999.1080p-fanart.jpg")
        self.assertEqual(stored["tmdb_confidence"], 95)
        self.assertIsNone(stored["scrape_error"])
        with Session(self.engine) as session:
            event = session.exec(
                select(EventRecord).where(EventRecord.type == "MetadataMatched")
            ).one()
        self.assertEqual(event.payload["current"]["metadata_source"], "tmdb")
        self.assertEqual(event.payload["current"]["scrape_status"], "matched")
        self.assertEqual(event.payload["current"]["tmdb_id"], "603")
        self.assertEqual(event.payload["current"]["runtime"], 136)
        self.assertIsNone(event.payload["current"]["scrape_error"])

    def test_scrape_movie_requires_confirmation_when_enabled(self):
        movie_dir = self.tmp_path / "The.Matrix.1999"
        movie_dir.mkdir()
        video = movie_dir / "The.Matrix.1999.1080p.mkv"
        video.write_bytes(b"fake video")

        movie = library_sync_service.scan_folder(movie_dir)
        self.assertIsNotNone(movie)

        with (
            patch("app.services.metadata.scraper.get_scrape_require_confirmation", return_value=True),
            patch.object(metadata_scraper.tmdb, "search_movies") as search_movies,
            patch.object(metadata_scraper.tmdb, "movie_details") as movie_details,
            patch.object(metadata_scraper.artwork, "download") as download,
        ):
            search_movies.return_value = [
                {
                    "id": 603,
                    "title": "The Matrix",
                    "original_title": "The Matrix",
                    "release_date": "1999-03-31",
                    "overview": "A computer hacker learns about the true nature of reality.",
                    "poster_path": "/matrix-poster.jpg",
                    "backdrop_path": "/matrix-backdrop.jpg",
                    "popularity": 100,
                }
            ]

            result = metadata_scraper.scrape_movie(movie["id"], ScrapeOptions())

        self.assertEqual(result.status, "needs_review")
        self.assertEqual(len(result.candidates), 1)
        movie_details.assert_not_called()
        download.assert_not_called()
        self.assertFalse((movie_dir / "The.Matrix.1999.1080p.nfo").exists())

        stored = library_manager.get_movie(movie["id"])
        self.assertIsNotNone(stored)
        self.assertEqual(stored["metadata_source"], "filename")
        self.assertEqual(stored["scrape_status"], "needs_review")
        self.assertEqual(stored["scrape_error"], "Manual confirmation required")
        self.assertEqual(stored["tmdb_confidence"], 95)

    def test_apply_artwork_updates_selection_through_event_projection(self):
        movie_dir = self.tmp_path / "The.Matrix.1999"
        movie_dir.mkdir()
        video = movie_dir / "The.Matrix.1999.1080p.mkv"
        video.write_bytes(b"fake video")

        movie = library_sync_service.scan_folder(movie_dir)
        self.assertIsNotNone(movie)
        library_manager.upsert_movie(
            {
                **movie,
                "title": "The Matrix",
                "year": 1999,
                "tmdb_id": "603",
                "metadata_source": "tmdb",
                "scrape_status": "matched",
            },
            preserve_id=movie["id"],
        )

        def fake_download(url, destination, overwrite=False):
            destination.write_bytes(f"downloaded {url}".encode("utf-8"))
            return destination

        with (
            patch.object(metadata_scraper.tmdb, "movie_details") as movie_details,
            patch.object(metadata_scraper.artwork, "download", side_effect=fake_download),
        ):
            movie_details.return_value = {
                "id": 603,
                "title": "The Matrix",
                "original_title": "The Matrix",
                "release_date": "1999-03-31",
                "images": {
                    "posters": [{"file_path": "/poster-new.jpg", "iso_639_1": "en", "vote_average": 9, "vote_count": 10, "width": 1000, "height": 1500}],
                    "backdrops": [{"file_path": "/backdrop-new.jpg", "iso_639_1": None, "vote_average": 9, "vote_count": 10, "width": 1920, "height": 1080}],
                },
            }
            with patch("app.services.metadata.scraper.library_manager.upsert_movie") as upsert_movie:
                result = metadata_scraper.apply_artwork(
                    movie["id"],
                    ArtworkSelection(poster_path="/poster-new.jpg", backdrop_path="/backdrop-new.jpg"),
                )

        self.assertEqual(result["status"], "success")
        upsert_movie.assert_not_called()
        stored = library_manager.get_movie(movie["id"])
        self.assertEqual(stored["poster_path"], "/poster-new.jpg")
        self.assertEqual(stored["backdrop_path"], "/backdrop-new.jpg")
        self.assertEqual(stored["poster_local"], "/media/The.Matrix.1999/The.Matrix.1999.1080p-poster.jpg")
        self.assertEqual(stored["backdrop_local"], "/media/The.Matrix.1999/The.Matrix.1999.1080p-fanart.jpg")
        with Session(self.engine) as session:
            event = session.exec(
                select(EventRecord).where(EventRecord.type == "ArtworkSelected")
            ).one()
        self.assertEqual(event.payload["current"]["poster_path"], "/poster-new.jpg")
        self.assertEqual(event.payload["current"]["backdrop_path"], "/backdrop-new.jpg")
        self.assertEqual(event.payload["current"]["poster_local"], stored["poster_local"])

    def test_scrape_movie_requires_confirmation_for_existing_tmdb_id(self):
        movie_dir = self.tmp_path / "The.Matrix.1999"
        movie_dir.mkdir()
        video = movie_dir / "The.Matrix.1999.1080p.mkv"
        video.write_bytes(b"fake video")

        movie = library_sync_service.scan_folder(movie_dir)
        self.assertIsNotNone(movie)
        library_manager.upsert_movie(
            {
                **movie,
                "title": "The Matrix",
                "year": 1999,
                "tmdb_id": "603",
                "metadata_source": "tmdb",
                "scrape_status": "matched",
            },
            preserve_id=movie["id"],
        )

        with (
            patch("app.services.metadata.scraper.get_scrape_require_confirmation", return_value=True),
            patch.object(metadata_scraper.tmdb, "movie_details") as movie_details,
        ):
            result = metadata_scraper.scrape_movie(movie["id"], ScrapeOptions())

        self.assertEqual(result.status, "needs_review")
        self.assertEqual(result.candidates[0].tmdb_id, 603)
        self.assertEqual(result.candidates[0].score, 100)
        movie_details.assert_not_called()

        stored = library_manager.get_movie(movie["id"])
        self.assertEqual(stored["scrape_status"], "needs_review")
        self.assertEqual(stored["scrape_error"], "Manual confirmation required")

    def test_scrape_movie_can_use_separate_artwork_language(self):
        movie_dir = self.tmp_path / "The.Matrix.1999"
        movie_dir.mkdir()
        video = movie_dir / "The.Matrix.1999.1080p.mkv"
        video.write_bytes(b"fake video")

        movie = library_sync_service.scan_folder(movie_dir)
        self.assertIsNotNone(movie)

        downloaded = []

        def fake_download(url, destination, overwrite=False):
            downloaded.append(url)
            destination.write_bytes(f"downloaded {url}".encode("utf-8"))
            return destination

        with (
            patch("app.services.metadata.scraper.get_scrape_require_confirmation", return_value=False),
            patch.object(metadata_scraper.tmdb, "search_movies") as search_movies,
            patch.object(metadata_scraper.tmdb, "movie_details") as movie_details,
            patch.object(metadata_scraper.artwork, "download", side_effect=fake_download),
        ):
            search_movies.return_value = [
                {
                    "id": 603,
                    "title": "黑客帝国",
                    "original_title": "The Matrix",
                    "release_date": "1999-03-31",
                    "overview": "中文简介",
                    "poster_path": "/zh-default.jpg",
                    "backdrop_path": "/zh-backdrop.jpg",
                    "popularity": 100,
                }
            ]
            movie_details.return_value = {
                "id": 603,
                "title": "黑客帝国",
                "original_title": "The Matrix",
                "release_date": "1999-03-31",
                "overview": "中文简介",
                "poster_path": "/zh-default.jpg",
                "backdrop_path": "/zh-backdrop.jpg",
                "images": {
                    "posters": [
                        {"file_path": "/zh-poster.jpg", "iso_639_1": "zh", "vote_average": 8, "vote_count": 10, "width": 1000, "height": 1500},
                        {"file_path": "/en-poster-low.jpg", "iso_639_1": "en", "vote_average": 7, "vote_count": 20, "width": 1000, "height": 1500},
                        {"file_path": "/en-poster.jpg", "iso_639_1": "en", "vote_average": 9, "vote_count": 20, "width": 1000, "height": 1500},
                    ],
                    "backdrops": [
                        {"file_path": "/textless-backdrop.jpg", "iso_639_1": None, "vote_average": 9, "vote_count": 20, "width": 1920, "height": 1080},
                    ],
                },
            }

            result = metadata_scraper.scrape_movie(
                movie["id"],
                ScrapeOptions(language="zh-CN", artwork_language="en"),
            )

        self.assertEqual(result.status, "success")
        movie_details.assert_called_once_with(603, language="zh-CN", artwork_language="en")
        self.assertIn("https://image.tmdb.org/t/p/original/en-poster.jpg", downloaded)
        self.assertIn("https://image.tmdb.org/t/p/original/textless-backdrop.jpg", downloaded)

    def test_confirmed_root_video_organize_moves_and_scrapes(self):
        video = self.tmp_path / "The.Matrix.1999.1080p.mkv"
        video.write_bytes(b"fake video")

        with (
            patch("app.services.metadata.organizer.get_media_file_stable_seconds", return_value=0),
            patch.object(metadata_scraper.tmdb, "movie_details") as movie_details,
            patch.object(metadata_scraper, "scrape_movie", return_value=SimpleNamespace(status="success")) as scrape_movie,
        ):
            movie_details.return_value = {
                "id": 603,
                "title": "The Matrix",
                "original_title": "The Matrix",
                "release_date": "1999-03-31",
                "overview": "A computer hacker learns about the true nature of reality.",
            }

            result = root_video_organizer.organize_file_confirmed(
                video,
                self.tmp_path.resolve(),
                603,
                RootOrganizeOptions(rename_style="preserve_stem"),
            )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["tmdb_id"], 603)
        self.assertEqual(result["scrape_status"], "success")
        self.assertFalse(video.exists())
        self.assertTrue((self.tmp_path / "The Matrix (1999)" / "The.Matrix.1999.1080p.mkv").exists())
        scrape_movie.assert_called_once()
        scrape_options = scrape_movie.call_args.args[1]
        self.assertEqual(scrape_options.mode, "manual")
        self.assertEqual(scrape_options.tmdb_id, 603)


if __name__ == "__main__":
    unittest.main()
