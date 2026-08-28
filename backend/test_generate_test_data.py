import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from app.services.scanner import NFOScanner
from scripts.generate_test_data import GENERATOR_NAME, SCHEMA_VERSION, clean_dataset, generate_dataset


class FreshCanonicalTestDataGeneratorTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_normal_profile_generates_twelve_scan_ready_films_and_local_artwork(self):
        output = self.root / "normal"
        manifest = generate_dataset(output, count=12, seed=549, profile="normal")
        self.assertEqual(manifest["generator"], GENERATOR_NAME)
        self.assertEqual(manifest["schema_version"], SCHEMA_VERSION)
        self.assertEqual(manifest["count"], 12)
        self.assertFalse((output / "movies.json").exists())
        self.assertFalse((output / "user_states.json").exists())
        observed = NFOScanner(str(output / "media")).scan_observed()
        self.assertEqual(len(observed), 12)
        self.assertTrue(all(item.film["library_status"] == "available" for item in observed))
        self.assertTrue(all(Path(item.film["poster_local"].replace("/media/", str(output / "media") + "/")).is_file() for item in observed))
        self.assertEqual(len(list((output / "media").glob("*/film-fanart.jpg"))), 12)

    def test_generation_is_deterministic_and_force_only_replaces_owned_output(self):
        first = self.root / "first"
        second = self.root / "second"
        generate_dataset(first, count=4, seed=7, profile="normal")
        generate_dataset(second, count=4, seed=7, profile="normal")
        self.assertEqual(
            json.loads((first / "manifest.json").read_text(encoding="utf-8")),
            json.loads((second / "manifest.json").read_text(encoding="utf-8")),
        )
        with self.assertRaises(ValueError):
            generate_dataset(first, count=4, seed=7, profile="normal")
        generate_dataset(first, count=2, seed=8, profile="normal", force=True)
        self.assertEqual(json.loads((first / "manifest.json").read_text(encoding="utf-8"))["count"], 2)

    def test_clean_refuses_unowned_directory(self):
        unowned = self.root / "unowned"
        unowned.mkdir()
        (unowned / "manifest.json").write_text("{}", encoding="utf-8")
        with self.assertRaises(ValueError):
            clean_dataset(unowned)

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg is unavailable")
    def test_valid_video_mode_generates_ffprobe_readable_media(self):
        output = self.root / "valid"
        manifest = generate_dataset(
            output,
            count=2,
            seed=549,
            profile="normal",
            video_mode="valid",
        )
        video = output / "media" / "film-0001" / "film.mp4"
        probe = subprocess.run(
            [
                str(shutil.which("ffprobe")),
                "-v",
                "error",
                "-show_entries",
                "stream=codec_type,width,height",
                "-of",
                "json",
                str(video),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        streams = json.loads(probe.stdout)["streams"]
        self.assertEqual(manifest["video_mode"], "valid")
        self.assertEqual({item["codec_type"] for item in streams}, {"video", "audio"})
        video_stream = next(item for item in streams if item["codec_type"] == "video")
        self.assertEqual((video_stream["width"], video_stream["height"]), (320, 180))
        self.assertNotEqual(
            video.read_bytes(),
            (output / "media" / "film-0002" / "film.mp4").read_bytes(),
        )


if __name__ == "__main__":
    unittest.main()
