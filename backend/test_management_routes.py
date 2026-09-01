import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlmodel import create_engine

from app.database import configure_sqlite_engine
from app.main import app
from app.migrations.runner import run_migrations
from app.services.library import LibraryManager


class MissingLibraryItemTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.database_path = Path(self._tmp.name) / "management.db"
        self.engine = create_engine(f"sqlite:///{self.database_path}")
        configure_sqlite_engine(self.engine)
        run_migrations(
            self.engine,
            self.database_path,
            app_version="test",
            backup_required=False,
        )

    def tearDown(self):
        self.engine.dispose()
        self._tmp.cleanup()

    def _insert_item(
        self,
        *,
        suffix: str,
        title: str,
        year: int,
        status: str,
        missing_since: str | None,
        display_name: str,
    ) -> None:
        film_id = f"film_{suffix * 32}"
        item_id = f"lib_{suffix * 32}"
        now = "2026-09-01T00:00:00Z"
        with self.engine.begin() as connection:
            profile_id = connection.execute(
                text("SELECT id FROM local_profile WHERE profile_key='local'")
            ).scalar_one()
            connection.execute(
                text(
                    "INSERT INTO graph_entity "
                    "(id, entity_type, lifecycle_status, created_at, updated_at) "
                    "VALUES (:id, 'film', 'active', :now, :now)"
                ),
                {"id": film_id, "now": now},
            )
            connection.execute(
                text(
                    "INSERT INTO film "
                    "(id, canonical_title, release_year, lifecycle_status, created_at, updated_at) "
                    "VALUES (:id, :title, :year, 'active', :now, :now)"
                ),
                {"id": film_id, "title": title, "year": year, "now": now},
            )
            connection.execute(
                text(
                    "INSERT INTO library_item "
                    "(id, profile_id, film_id, source_type, source_instance_id, source_item_key, "
                    "display_name, availability_status, resolution_status, missing_since, "
                    "scrape_status, created_at, updated_at) "
                    "VALUES (:id, :profile_id, :film_id, 'nfo', 'local', :source_key, :display_name, "
                    ":status, 'matched', :missing_since, 'matched', :now, :now)"
                ),
                {
                    "id": item_id,
                    "profile_id": profile_id,
                    "film_id": film_id,
                    "source_key": f"private/{suffix}/movie.nfo",
                    "display_name": display_name,
                    "status": status,
                    "missing_since": missing_since,
                    "now": now,
                },
            )

    def test_service_lists_only_missing_items_in_stable_order_without_paths(self):
        self._insert_item(
            suffix="a",
            title="Later Film",
            year=2001,
            status="missing",
            missing_since="2026-08-31T00:00:00Z",
            display_name="Later Film (2001)",
        )
        self._insert_item(
            suffix="b",
            title="Earlier Film",
            year=1994,
            status="missing",
            missing_since="2026-08-01T00:00:00Z",
            display_name="Earlier Film (1994)",
        )
        self._insert_item(
            suffix="c",
            title="Available Film",
            year=2010,
            status="available",
            missing_since=None,
            display_name="Available Film (2010)",
        )

        with patch("app.services.library.engine", self.engine):
            items = LibraryManager().list_missing_items()

        self.assertEqual([item["title"] for item in items], ["Earlier Film", "Later Film"])
        self.assertEqual(
            set(items[0]),
            {"library_item_id", "film_id", "title", "year", "display_name", "missing_since"},
        )
        self.assertNotIn("source_item_key", items[0])
        self.assertNotIn("locator", items[0])

    def test_get_route_is_read_only_and_returns_count(self):
        fixture = [{
            "library_item_id": "lib_" + "a" * 32,
            "film_id": "film_" + "b" * 32,
            "title": "A Film",
            "year": 2000,
            "display_name": "A Film (2000)",
            "missing_since": "2026-08-01T00:00:00Z",
        }]
        with (
            patch("app.api.library.library_manager.list_missing_items", return_value=fixture),
            patch("app.api.library.library_manager.cleanup_missing") as cleanup_missing,
            TestClient(app) as client,
        ):
            response = client.get("/library/missing")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"count": 1, "items": fixture})
        cleanup_missing.assert_not_called()

    def test_delete_route_keeps_existing_response_contract(self):
        with (
            patch("app.api.library.library_manager.cleanup_missing", return_value=3) as cleanup_missing,
            patch("app.api.library.library_event_bus.publish_library_changed") as publish,
            TestClient(app) as client,
        ):
            response = client.delete("/library/missing")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "success", "deleted": 3})
        cleanup_missing.assert_called_once_with()
        publish.assert_called_once_with("missing_cleanup", deleted=3)
