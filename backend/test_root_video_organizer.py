import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services.metadata.organizer import RootVideoOrganizer


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


if __name__ == "__main__":
    unittest.main()
