import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services.metadata.organizer import RootVideoOrganizer
from app.services.operation_manifests import OperationManifestError, OperationManifestStore


class RootVideoOrganizerTests(unittest.TestCase):
    def test_list_root_videos_reports_unreadable_media_directory(self):
        organizer = RootVideoOrganizer()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(
                Path,
                "iterdir",
                side_effect=PermissionError(1, "Operation not permitted", str(root)),
            ):
                with self.assertRaisesRegex(PermissionError, "Cannot read media directory"):
                    organizer.list_root_videos(str(root))

    def test_controlled_manifest_restores_video_and_sidecar_without_public_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            media_root = workspace / "media"
            media_root.mkdir()
            source = media_root / "Film.mkv"
            source_sidecar = media_root / "Film.srt"
            source.write_bytes(b"video")
            source_sidecar.write_text("subtitle", encoding="utf-8")
            store = OperationManifestStore(workspace / "manifests")
            reference = store.create(media_root, source)
            target_dir = media_root / "Film (2026)"
            target_dir.mkdir()
            target = target_dir / source.name
            target_sidecar = target_dir / source_sidecar.name
            source.replace(target)
            source_sidecar.replace(target_sidecar)
            store.finalize(
                reference,
                target=target,
                sidecars=[{"source": str(source_sidecar), "target": str(target_sidecar)}],
            )

            self.assertRegex(reference, r"^manifest_[0-9a-f]{32}$")
            self.assertNotIn(str(media_root), reference)
            self.assertEqual(store.state(reference), "target")
            store.restore(reference)
            self.assertEqual(store.state(reference), "source")
            self.assertTrue(source.is_file())
            self.assertTrue(source_sidecar.is_file())

    def test_manifest_rejects_paths_outside_the_media_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            media_root = workspace / "media"
            media_root.mkdir()
            outside = workspace / "outside.mkv"
            outside.write_bytes(b"video")
            store = OperationManifestStore(workspace / "manifests")
            with self.assertRaisesRegex(OperationManifestError, "escapes"):
                store.create(media_root, outside)


if __name__ == "__main__":
    unittest.main()
