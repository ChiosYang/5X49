import hashlib
import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from pydantic import ValidationError
from sqlmodel import Session, SQLModel, create_engine, select

from app.models import Movie, MovieUserState
from app.services.scanner import NFOScanner
from app.services import event_store as event_store_module
from app.services import library as library_module
from app.utils.security import validate_movie_id
from scripts.generate_test_data import clean_dataset, generate_dataset, main


class TestDataGeneratorTests(unittest.TestCase):
    def test_default_dataset_has_repeatable_distribution_and_model_payloads(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / "first"
            second = root / "second"

            first_manifest = generate_dataset(first)
            second_manifest = generate_dataset(second)

            self.assertEqual(first_manifest, second_manifest)
            self.assertEqual(
                json.loads((first / "movies.json").read_text(encoding="utf-8")),
                json.loads((second / "movies.json").read_text(encoding="utf-8")),
            )
            self.assertEqual(first_manifest["count"], 200)
            self.assertEqual(
                first_manifest["distribution"],
                {"complete": 140, "incomplete": 40, "edge": 20},
            )

            movies = json.loads((first / "movies.json").read_text(encoding="utf-8"))
            states = json.loads((first / "user_states.json").read_text(encoding="utf-8"))
            self.assertEqual(len(movies), 200)
            self.assertEqual(len({movie["id"] for movie in movies}), 200)
            self.assertTrue(all(Movie.model_validate(movie) for movie in movies))
            self.assertTrue(all(MovieUserState.model_validate(state) for state in states))

            file_hashes = self._relative_file_hashes(first / "media")
            self.assertEqual(file_hashes, self._relative_file_hashes(second / "media"))

    def test_media_tree_exercises_scanner_success_fallback_and_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "generated"
            manifest = generate_dataset(output, count=80, seed=549)
            media_root = output / "media"
            scenarios = manifest["media_scenarios"]

            scanned = NFOScanner(str(media_root)).scan()
            scanned_titles = {movie["title"] for movie in scanned}
            scanned_folders = {movie["folder_name"] for movie in scanned}

            self.assertGreaterEqual(len(scanned), 1)
            self.assertTrue(any(item["scenario"] == "missing_nfo" for item in scenarios))
            self.assertTrue(any(item["scenario"] == "corrupt_xml" for item in scenarios))
            fallback = next(item for item in scenarios if item["scenario"] == "missing_nfo")
            self.assertIn(fallback["title"], scanned_titles)
            corrupt = next(item for item in scenarios if item["scenario"] == "corrupt_xml")
            self.assertNotIn(Path(corrupt["path"]).name, scanned_folders)
            multiple = next(item for item in scenarios if item["scenario"] == "multiple_videos")
            multiple_movie = next(movie for movie in scanned if movie["folder_name"] == Path(multiple["path"]).name)
            self.assertEqual(multiple_movie["video_file"], "clip-a.mp4")
            self.assertTrue(any(count > 1 for count in Counter(movie["id"] for movie in scanned).values()))

            root_video = output / manifest["root_video"]
            self.assertTrue(root_video.is_file())
            self.assertNotIn(root_video.stem, scanned_titles)

    def test_normal_profile_generates_only_valid_movies_with_local_artwork(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "normal"
            manifest = generate_dataset(output, count=12, seed=549, profile="normal")

            self.assertEqual(manifest["profile"], "normal")
            self.assertEqual(
                manifest["distribution"],
                {"complete": 12, "incomplete": 0, "edge": 0},
            )
            self.assertIsNone(manifest["root_video"])
            self.assertEqual(manifest["invalid_record_names"], [])
            self.assertTrue(
                all(item["scenario"] == "valid_nfo" for item in manifest["media_scenarios"])
            )

            for item in manifest["media_scenarios"]:
                movie_dir = output / item["path"]
                poster = movie_dir / "movie-poster.jpg"
                backdrop = movie_dir / "movie-fanart.jpg"
                self.assertTrue((movie_dir / "movie.nfo").is_file())
                self.assertTrue((movie_dir / "movie.mp4").is_file())
                with Image.open(poster) as image:
                    self.assertEqual(image.size, (600, 900))
                with Image.open(backdrop) as image:
                    self.assertEqual(image.size, (1280, 720))

            with patch("app.services.scanner.artwork_cache.generate", return_value=None), patch(
                "app.services.scanner.video_probe_service.probe", return_value={}
            ):
                scanned = NFOScanner(str(output / "media")).scan()
            self.assertEqual(len(scanned), 12)
            generated_movies = json.loads((output / "movies.json").read_text(encoding="utf-8"))
            self.assertEqual(
                {movie["id"] for movie in scanned},
                {movie["id"] for movie in generated_movies},
            )
            self.assertTrue(all(movie["poster_local"] for movie in scanned))
            self.assertTrue(all(movie["backdrop_local"] for movie in scanned))

    def test_generated_movies_can_be_imported_into_a_temporary_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "generated"
            generate_dataset(output, count=12, seed=549)
            movies = json.loads((output / "movies.json").read_text(encoding="utf-8"))
            states = json.loads((output / "user_states.json").read_text(encoding="utf-8"))
            scanned_movies = NFOScanner(str(output / "media")).scan()
            engine = create_engine(f"sqlite:///{Path(tmp) / 'library.db'}")
            SQLModel.metadata.create_all(engine)

            with patch.object(library_module, "engine", engine), patch.object(
                event_store_module, "engine", engine
            ):
                self.assertEqual(library_module.library_manager.add_movies(movies), 12)
                self.assertEqual(library_module.library_manager.add_movies(scanned_movies), len(scanned_movies))
                with Session(engine) as session:
                    session.add_all(MovieUserState.model_validate(state) for state in states)
                    session.commit()
                    stored_movies = session.exec(select(Movie)).all()
                    stored_states = session.exec(select(MovieUserState)).all()
            engine.dispose()

            self.assertEqual(len(stored_movies), 12 + len(scanned_movies))
            self.assertEqual(len(stored_states), len(states))

    def test_output_boundary_and_precise_cleanup_are_safe(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "generated"
            sibling = root / "keep.txt"
            sibling.write_text("keep", encoding="utf-8")
            generate_dataset(output, count=4)

            with self.assertRaises(ValueError):
                generate_dataset(output)
            with self.assertRaises(ValueError):
                generate_dataset(Path.cwd())
            with self.assertRaises(ValueError):
                generate_dataset(Path(Path.cwd().anchor))
            with self.assertRaises(ValueError):
                clean_dataset(root)

            clean_dataset(output)
            self.assertFalse(output.exists())
            self.assertEqual(sibling.read_text(encoding="utf-8"), "keep")

    def test_cli_can_generate_and_clean_a_small_fixture(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "cli"
            self.assertEqual(
                main(["--count", "12", "--seed", "549", "--output-dir", str(output)]),
                0,
            )
            self.assertEqual(main(["--clean", "--output-dir", str(output)]), 0)
            self.assertFalse(output.exists())

    def test_committed_small_fixture_is_model_compatible(self):
        fixture_root = Path(__file__).parent / "fixtures" / "test-data-small"
        movies = json.loads((fixture_root / "movies.json").read_text(encoding="utf-8"))
        states = json.loads((fixture_root / "user_states.json").read_text(encoding="utf-8"))

        self.assertEqual(len(movies), 12)
        self.assertTrue(all(Movie.model_validate(movie) for movie in movies))
        self.assertTrue(all(MovieUserState.model_validate(state) for state in states))

    def test_explicit_invalid_cases_are_rejected_at_real_validation_seams(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "generated"
            generate_dataset(output, count=12)
            invalid = json.loads((output / "invalid_records.json").read_text(encoding="utf-8"))

        self.assertEqual(len(invalid), 4)
        with self.assertRaises(ValidationError):
            Movie.model_validate(invalid[0]["payload"])
        with self.assertRaises(ValidationError):
            Movie.model_validate(invalid[1]["payload"])
        self.assertFalse(validate_movie_id(invalid[2]["payload"]["id"]))
        with self.assertRaises(ValidationError):
            MovieUserState.model_validate(invalid[3]["payload"])

    def _relative_file_hashes(self, root: Path) -> dict[str, str]:
        return {
            str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(root.rglob("*"))
            if path.is_file()
        }


if __name__ == "__main__":
    unittest.main()
