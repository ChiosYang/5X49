import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlmodel import SQLModel, create_engine

import app.database as database
import app.services.library as library_module
from app.services.library import library_manager
from app.services.library_sync import library_sync_service
from app.services.metadata.models import ScrapeOptions
from app.services.metadata.scraper import metadata_scraper


class MetadataScraperIntegrationTests(unittest.TestCase):
    def setUp(self):
        self._original_database_engine = database.engine
        self._original_library_engine = library_module.engine
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmp.name)
        self.engine = create_engine(f"sqlite:///{self.tmp_path / 'library.db'}")
        database.engine = self.engine
        library_module.engine = self.engine
        SQLModel.metadata.create_all(self.engine)

    def tearDown(self):
        database.engine = self._original_database_engine
        library_module.engine = self._original_library_engine
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

            result = metadata_scraper.scrape_movie(movie["id"], ScrapeOptions())

        self.assertEqual(result.status, "success")
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


if __name__ == "__main__":
    unittest.main()
