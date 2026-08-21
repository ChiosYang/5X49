import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlmodel import create_engine

from app.migrations.runner import run_migrations


class CanonicalSchemaTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.database_path = Path(self._tmp.name) / "canonical.db"
        with closing(sqlite3.connect(self.database_path)) as connection:
            connection.executescript(
                "CREATE TABLE movie (id VARCHAR PRIMARY KEY, title VARCHAR NOT NULL, "
                "year INTEGER NOT NULL);"
                "INSERT INTO movie VALUES ('legacy_schema', 'Schema Sentinel', 2001);"
            )
        self.engine = create_engine(f"sqlite:///{self.database_path}")
        run_migrations(
            self.engine,
            self.database_path,
            app_version="test",
            backup_dir=Path(self._tmp.name) / "backups",
        )

    def tearDown(self):
        self.engine.dispose()
        self._tmp.cleanup()

    def test_schema_contains_canonical_tables_and_single_local_profile(self):
        tables = set(inspect(self.engine).get_table_names())
        self.assertTrue({
            "graph_entity",
            "local_profile",
            "film",
            "external_identity",
            "library_item",
            "library_item_locator_history",
            "media_asset",
            "legacy_movie_alias",
            "identity_review",
            "canonical_backfill_run",
        }.issubset(tables))
        with self.engine.connect() as connection:
            profiles = connection.execute(
                text("SELECT id, profile_key FROM local_profile")
            ).mappings().all()
        self.assertEqual(len(profiles), 1)
        self.assertEqual(profiles[0]["profile_key"], "local")
        self.assertRegex(profiles[0]["id"], r"^profile_[0-9a-f]{32}$")

    def test_same_title_year_and_multiple_library_items_are_allowed(self):
        with self.engine.begin() as connection:
            profile_id = connection.execute(
                text("SELECT id FROM local_profile WHERE profile_key = 'local'")
            ).scalar_one()
            for suffix in ("a", "b"):
                film_id = f"film_{suffix * 32}"
                connection.execute(
                    text(
                        "INSERT INTO graph_entity VALUES "
                        "(:id, 'film', 'active', NULL, :now, :now)"
                    ),
                    {"id": film_id, "now": "2026-08-21T00:00:00Z"},
                )
                connection.execute(
                    text(
                        "INSERT INTO film "
                        "(id, canonical_title, release_year, lifecycle_status, created_at, updated_at) "
                        "VALUES (:id, 'Same Title', 2001, 'active', :now, :now)"
                    ),
                    {"id": film_id, "now": "2026-08-21T00:00:00Z"},
                )
            for index in (1, 2):
                connection.execute(
                    text(
                        "INSERT INTO library_item "
                        "(id, profile_id, film_id, source_type, source_instance_id, "
                        "source_item_key, availability_status, resolution_status, "
                        "scrape_status, created_at, updated_at) VALUES "
                        "(:id, :profile, :film, 'local_nfo', 'root', :key, "
                        "'available', 'matched', 'pending', :now, :now)"
                    ),
                    {
                        "id": f"lib_{index:032x}",
                        "profile": profile_id,
                        "film": "film_" + "a" * 32,
                        "key": f"movie-{index}",
                        "now": "2026-08-21T00:00:00Z",
                    },
                )

        with self.engine.connect() as connection:
            self.assertEqual(
                connection.execute(
                    text(
                        "SELECT COUNT(*) FROM film "
                        "WHERE canonical_title = 'Same Title' AND release_year = 2001"
                    )
                ).scalar_one(),
                2,
            )
            self.assertEqual(
                connection.execute(
                    text("SELECT COUNT(*) FROM library_item WHERE film_id = :film"),
                    {"film": "film_" + "a" * 32},
                ).scalar_one(),
                2,
            )

    def test_external_identity_active_source_and_asset_owner_constraints(self):
        with self.engine.begin() as connection:
            connection.execute(text("PRAGMA foreign_keys = ON"))
            profile_id = connection.execute(
                text("SELECT id FROM local_profile WHERE profile_key = 'local'")
            ).scalar_one()
            for suffix in ("c", "d"):
                film_id = f"film_{suffix * 32}"
                connection.execute(
                    text("INSERT INTO graph_entity VALUES (:id, 'film', 'active', NULL, :n, :n)"),
                    {"id": film_id, "n": "2026-08-21T00:00:00Z"},
                )
                connection.execute(
                    text(
                        "INSERT INTO film (id, canonical_title, lifecycle_status, created_at, updated_at) "
                        "VALUES (:id, :id, 'active', :n, :n)"
                    ),
                    {"id": film_id, "n": "2026-08-21T00:00:00Z"},
                )
            connection.execute(
                text(
                    "INSERT INTO external_identity "
                    "(id, entity_id, provider, external_id, identity_status, provenance_kind, "
                    "created_at, updated_at) VALUES "
                    "('identity_one', :film, 'tmdb.movie', '42', 'active', 'test', :n, :n)"
                ),
                {"film": "film_" + "c" * 32, "n": "2026-08-21T00:00:00Z"},
            )
            connection.execute(
                text(
                    "INSERT INTO library_item "
                    "(id, profile_id, film_id, source_type, source_instance_id, source_item_key, "
                    "availability_status, resolution_status, scrape_status, created_at, updated_at) "
                    "VALUES ('lib_constraint', :profile, :film, 'local_nfo', 'root', 'same-key', "
                    "'available', 'matched', 'pending', :n, :n)"
                ),
                {
                    "profile": profile_id,
                    "film": "film_" + "c" * 32,
                    "n": "2026-08-21T00:00:00Z",
                },
            )

        with self.assertRaises(IntegrityError), self.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO external_identity "
                    "(id, entity_id, provider, external_id, identity_status, provenance_kind, "
                    "created_at, updated_at) VALUES "
                    "('identity_two', :film, 'tmdb.movie', '42', 'active', 'test', :n, :n)"
                ),
                {"film": "film_" + "d" * 32, "n": "2026-08-21T00:00:00Z"},
            )

        with self.assertRaises(IntegrityError), self.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO media_asset "
                    "(id, asset_kind, locator_kind, locator, normalized_locator_hash, "
                    "availability_status, source, created_at, updated_at) VALUES "
                    "('asset_bad', 'video', 'local_path', 'movie.mkv', 'hash', "
                    "'present', 'test', :n, :n)"
                ),
                {"n": "2026-08-21T00:00:00Z"},
            )

        with self.assertRaises(IntegrityError), self.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO library_item "
                    "(id, profile_id, film_id, source_type, source_instance_id, source_item_key, "
                    "availability_status, resolution_status, scrape_status, created_at, updated_at) "
                    "SELECT 'lib_duplicate', profile_id, film_id, source_type, source_instance_id, "
                    "source_item_key, 'available', resolution_status, scrape_status, created_at, updated_at "
                    "FROM library_item WHERE id = 'lib_constraint'"
                )
            )

    def test_referenced_film_delete_is_restricted_when_foreign_keys_are_enabled(self):
        with self.engine.begin() as connection:
            connection.execute(text("PRAGMA foreign_keys = ON"))
            profile_id = connection.execute(
                text("SELECT id FROM local_profile WHERE profile_key = 'local'")
            ).scalar_one()
            film_id = "film_" + "e" * 32
            now = "2026-08-21T00:00:00Z"
            connection.execute(
                text("INSERT INTO graph_entity VALUES (:id, 'film', 'active', NULL, :n, :n)"),
                {"id": film_id, "n": now},
            )
            connection.execute(
                text(
                    "INSERT INTO film (id, canonical_title, lifecycle_status, created_at, updated_at) "
                    "VALUES (:id, 'Restricted', 'active', :n, :n)"
                ),
                {"id": film_id, "n": now},
            )
            connection.execute(
                text(
                    "INSERT INTO library_item "
                    "(id, profile_id, film_id, source_type, source_instance_id, source_item_key, "
                    "availability_status, resolution_status, scrape_status, created_at, updated_at) "
                    "VALUES ('lib_restrict', :profile, :film, 'local_nfo', 'root', 'restrict', "
                    "'available', 'matched', 'pending', :n, :n)"
                ),
                {"profile": profile_id, "film": film_id, "n": now},
            )

        with self.assertRaises(IntegrityError), self.engine.begin() as connection:
            connection.execute(text("PRAGMA foreign_keys = ON"))
            connection.execute(text("DELETE FROM film WHERE id = :id"), {"id": film_id})


if __name__ == "__main__":
    unittest.main()
