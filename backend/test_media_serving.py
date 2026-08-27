import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api.media import MediaFileUnavailable, resolve_media_path
from app.main import app


class DynamicMediaServingTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.first_root = self.root / "first"
        self.second_root = self.root / "second"
        self.relative_path = Path("Film") / "poster.jpg"
        for media_root, content in (
            (self.first_root, b"first-image"),
            (self.second_root, b"second-image"),
        ):
            target = media_root / self.relative_path
            target.parent.mkdir(parents=True)
            target.write_bytes(content)
        self.client = TestClient(app)

    def tearDown(self):
        self._tmp.cleanup()

    def test_media_root_switch_takes_effect_without_rebuilding_the_app(self):
        request_path = "/media/Film/poster.jpg"
        with patch("app.api.media.get_media_dir", return_value=str(self.first_root)):
            first = self.client.get(request_path)
        with patch("app.api.media.get_media_dir", return_value=str(self.second_root)):
            second = self.client.get(request_path)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.content, b"first-image")
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.content, b"second-image")
        self.assertEqual(second.headers["content-type"], "image/jpeg")
        self.assertEqual(second.headers["cache-control"], "no-cache")

    def test_missing_root_and_file_return_bounded_404(self):
        missing_root = self.root / "missing"
        with patch("app.api.media.get_media_dir", return_value=str(missing_root)):
            response = self.client.get("/media/Film/poster.jpg")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "Media file not found"})
        self.assertNotIn(str(missing_root), response.text)

    def test_media_directory_setting_is_validated_and_applies_immediately(self):
        with patch("app.api.settings.set_media_dir", return_value=True) as save:
            response = self.client.put(
                "/settings/media-dir",
                params={"media_dir": str(self.second_root)},
            )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("restart", response.json()["message"].casefold())
        save.assert_called_once_with(str(self.second_root.resolve()))

        missing = self.client.put(
            "/settings/media-dir",
            params={"media_dir": str(self.root / "missing")},
        )
        self.assertEqual(missing.status_code, 400)
        self.assertEqual(missing.json(), {"detail": "Media directory does not exist"})

    def test_path_traversal_and_absolute_paths_are_rejected(self):
        outside = self.root / "outside.jpg"
        outside.write_bytes(b"outside")
        for candidate in ("../outside.jpg", str(outside), "Film/../../outside.jpg"):
            with self.subTest(candidate=candidate):
                with self.assertRaises(MediaFileUnavailable):
                    resolve_media_path(self.first_root, candidate)

    def test_symlink_escape_is_rejected_when_supported(self):
        outside = self.root / "outside.jpg"
        outside.write_bytes(b"outside")
        link = self.first_root / "Film" / "linked.jpg"
        try:
            os.symlink(outside, link)
        except OSError as exc:
            self.skipTest(f"symlinks are unavailable: {type(exc).__name__}")

        with self.assertRaises(MediaFileUnavailable):
            resolve_media_path(self.first_root, "Film/linked.jpg")


if __name__ == "__main__":
    unittest.main()
