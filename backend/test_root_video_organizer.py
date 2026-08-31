import tempfile
import unittest
import os
from pathlib import Path
from unittest.mock import patch

from app.services.metadata.models import MetadataSearchResult
from app.services.metadata.organizer import RootVideoOrganizer
from app.services.operation_manifests import OperationManifestError, OperationManifestStore


class RootVideoOrganizerTests(unittest.TestCase):
    candidate = MetadataSearchResult(
        tmdb_id=603,
        title="The Matrix",
        original_title="The Matrix",
        year=1999,
        overview="",
        score=100,
    )

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

    def test_candidates_include_direct_root_and_legacy_inbox_only(self):
        organizer = RootVideoOrganizer()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inbox = root / "inbox"
            nested = root / "nested"
            inbox.mkdir()
            nested.mkdir()
            (root / "Root Film.mkv").write_bytes(b"root")
            (inbox / "Inbox Film.mp4").write_bytes(b"inbox")
            (nested / "Nested Film.mkv").write_bytes(b"nested")

            with patch("app.services.metadata.organizer.get_media_file_stable_seconds", return_value=0):
                candidates = organizer.list_organization_candidates(str(root))

        self.assertEqual(
            {(item["source_path"], item["source_location"]) for item in candidates},
            {("Root Film.mkv", "root"), ("inbox/Inbox Film.mp4", "legacy_inbox")},
        )
        self.assertTrue(all("path" not in item for item in candidates))

    def test_preview_is_read_only_and_standardizes_video_and_sidecars(self):
        organizer = RootVideoOrganizer()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inbox = root / "inbox"
            inbox.mkdir()
            source = inbox / "the.matrix.1999.1080p.mkv"
            subtitle = inbox / "the.matrix.1999.1080p.zh.forced.srt"
            source.write_bytes(b"video")
            subtitle.write_text("subtitle", encoding="utf-8")

            with (
                patch("app.services.metadata.organizer.get_media_file_stable_seconds", return_value=0),
                patch("app.services.metadata.organizer.metadata_scraper.get_candidate", return_value=self.candidate),
            ):
                preview = organizer.preview_organization(
                    root,
                    "inbox/the.matrix.1999.1080p.mkv",
                    603,
                    "title_year",
                )

            self.assertTrue(source.is_file())
            self.assertTrue(subtitle.is_file())
            self.assertFalse((root / "The Matrix (1999)").exists())
            self.assertEqual(preview["target"]["folder_name"], "The Matrix (1999)")
            self.assertEqual(preview["target"]["video_name"], "The Matrix (1999).mkv")
            self.assertEqual(
                preview["sidecars"],
                [{
                    "source_name": subtitle.name,
                    "target_name": "The Matrix (1999).zh.forced.srt",
                    "conflict": False,
                }],
            )
            self.assertTrue(preview["can_confirm"])
            self.assertRegex(preview["confirmation_token"], r"^[0-9a-f]{64}$")

    def test_preserve_preview_keeps_video_and_sidecar_names(self):
        organizer = RootVideoOrganizer()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "Messy.Name.1999.mkv"
            subtitle = root / "Messy.Name.1999.en.srt"
            source.write_bytes(b"video")
            subtitle.write_text("subtitle", encoding="utf-8")
            with (
                patch("app.services.metadata.organizer.get_media_file_stable_seconds", return_value=0),
                patch("app.services.metadata.organizer.metadata_scraper.get_candidate", return_value=self.candidate),
            ):
                preview = organizer.preview_organization(root, source.name, 603, "preserve_stem")

        self.assertEqual(preview["target"]["video_name"], source.name)
        self.assertEqual(preview["sidecars"][0]["target_name"], subtitle.name)

    def test_conflict_blocks_confirmation_and_source_drift_invalidates_token(self):
        organizer = RootVideoOrganizer()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "Matrix.mkv"
            source.write_bytes(b"video")
            with (
                patch("app.services.metadata.organizer.get_media_file_stable_seconds", return_value=0),
                patch("app.services.metadata.organizer.metadata_scraper.get_candidate", return_value=self.candidate),
            ):
                first = organizer.preview_organization(root, source.name, 603, "title_year")
                source.write_bytes(b"changed-video")
                os.utime(source, ns=(source.stat().st_atime_ns, source.stat().st_mtime_ns + 1_000_000))
                with self.assertRaisesRegex(RuntimeError, "stale"):
                    organizer.validate_organization_confirmation(
                        root,
                        source.name,
                        603,
                        "title_year",
                        first["confirmation_token"],
                    )

                target_dir = root / "The Matrix (1999)"
                target_dir.mkdir()
                (target_dir / "The Matrix (1999).mkv").write_bytes(b"existing")
                conflict = organizer.preview_organization(root, source.name, 603, "title_year")

        self.assertFalse(conflict["can_confirm"])
        self.assertEqual(conflict["conflicts"], [{"kind": "video", "name": "The Matrix (1999).mkv"}])

    def test_preview_rejects_nested_and_traversal_paths(self):
        organizer = RootVideoOrganizer()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            nested = root / "nested"
            nested.mkdir()
            (nested / "Film.mkv").write_bytes(b"video")
            with self.assertRaisesRegex(ValueError, "pending-file locations"):
                organizer.preview_organization(root, "nested/Film.mkv", 603)
            with self.assertRaises(ValueError):
                organizer.preview_organization(root, "../Film.mkv", 603)

    def test_standardized_sidecars_move_with_the_video_stem(self):
        organizer = RootVideoOrganizer()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "Messy.Name.mkv"
            subtitle = root / "Messy.Name.en.forced.srt"
            source.write_bytes(b"video")
            subtitle.write_text("subtitle", encoding="utf-8")
            target_dir = root / "The Matrix (1999)"
            target_dir.mkdir()

            moved, moves = organizer._move_sidecars(
                source,
                target_dir,
                "The Matrix (1999).mkv",
                "title_year",
                False,
            )

            target = target_dir / "The Matrix (1999).en.forced.srt"
            self.assertEqual(moved, [target.name])
            self.assertEqual(Path(moves[0]["target"]), target)
            self.assertFalse(subtitle.exists())
            self.assertTrue(target.is_file())

    def test_sidecar_target_conflict_blocks_manual_preview(self):
        organizer = RootVideoOrganizer()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "Matrix.mkv"
            subtitle = root / "Matrix.en.srt"
            source.write_bytes(b"video")
            subtitle.write_text("subtitle", encoding="utf-8")
            target_dir = root / "The Matrix (1999)"
            target_dir.mkdir()
            (target_dir / "The Matrix (1999).en.srt").write_text("existing", encoding="utf-8")

            with (
                patch("app.services.metadata.organizer.get_media_file_stable_seconds", return_value=0),
                patch("app.services.metadata.organizer.metadata_scraper.get_candidate", return_value=self.candidate),
            ):
                preview = organizer.preview_organization(root, source.name, 603, "title_year")

        self.assertFalse(preview["can_confirm"])
        self.assertEqual(
            preview["conflicts"],
            [{"kind": "sidecar", "name": "The Matrix (1999).en.srt"}],
        )


if __name__ == "__main__":
    unittest.main()
