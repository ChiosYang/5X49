import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from sqlalchemy import text
from sqlmodel import create_engine

from app.migrations.runner import run_migrations
from app.services.canonical_backfill import backfill_legacy_movies


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "database" / "canonical-identities"


class CanonicalBackfillTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.database_path = Path(self._tmp.name) / "canonical-identities.db"
        with closing(sqlite3.connect(self.database_path)) as connection:
            connection.executescript((FIXTURE_DIR / "schema.sql").read_text(encoding="utf-8"))
            connection.commit()
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

    def test_exact_identities_reuse_film_but_conflicts_and_title_matches_do_not(self):
        with self.engine.connect() as connection:
            aliases = {
                row["legacy_movie_id"]: row["film_id"]
                for row in connection.execute(
                    text("SELECT legacy_movie_id, film_id FROM legacy_movie_alias")
                ).mappings()
            }
            review = connection.execute(
                text("SELECT * FROM identity_review WHERE legacy_movie_id = 'identity_conflict'")
            ).mappings().one()

        self.assertEqual(len(aliases), 6)
        self.assertEqual(aliases["identity_a"], aliases["identity_b"])
        self.assertNotEqual(aliases["identity_conflict"], aliases["identity_a"])
        self.assertNotEqual(aliases["identity_conflict"], aliases["identity_c"])
        self.assertNotEqual(aliases["same_title_one"], aliases["same_title_two"])
        self.assertEqual(review["reason"], "identity_conflict")
        self.assertEqual(review["status"], "open")
        self.assertEqual(review["tmdb_film_id"], aliases["identity_a"])
        self.assertEqual(review["imdb_film_id"], aliases["identity_c"])

    def test_backfill_preserves_one_item_and_alias_per_movie_and_maps_assets(self):
        with self.engine.connect() as connection:
            counts = {
                table: connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one()
                for table in (
                    "movie",
                    "film",
                    "library_item",
                    "legacy_movie_alias",
                    "external_identity",
                    "identity_review",
                )
            }
            assets = connection.execute(
                text(
                    "SELECT ma.asset_kind, ma.locator, ma.availability_status "
                    "FROM media_asset ma JOIN legacy_movie_alias a "
                    "ON a.library_item_id = ma.library_item_id "
                    "WHERE a.legacy_movie_id = 'identity_c' ORDER BY ma.asset_kind"
                )
            ).mappings().all()
            ignored = connection.execute(
                text(
                    "SELECT li.availability_status FROM library_item li "
                    "JOIN legacy_movie_alias a ON a.library_item_id = li.id "
                    "WHERE a.legacy_movie_id = 'same_title_two'"
                )
            ).scalar_one()

        self.assertEqual(counts, {
            "movie": 6,
            "film": 5,
            "library_item": 6,
            "legacy_movie_alias": 6,
            "external_identity": 4,
            "identity_review": 1,
        })
        self.assertTrue(any(asset["asset_kind"] == "video" for asset in assets))
        self.assertTrue(all(asset["availability_status"] == "missing" for asset in assets))
        self.assertEqual(ignored, "ignored")

    def test_report_is_auditable_without_paths_and_repeat_execution_is_idempotent(self):
        with self.engine.begin() as connection:
            report_row = connection.execute(
                text(
                    "SELECT * FROM canonical_backfill_run "
                    "WHERE run_key = 'legacy_movie_to_canonical.v1'"
                )
            ).mappings().one()
            first_counts = self._durable_counts(connection)
            dry_run = backfill_legacy_movies(connection, dry_run=True)
            repeated = backfill_legacy_movies(connection, dry_run=False)
            second_counts = self._durable_counts(connection)

        stored_counts = json.loads(report_row["counts"])
        self.assertEqual(stored_counts["movies_scanned"], 6)
        self.assertEqual(stored_counts["films_created"], 5)
        self.assertEqual(stored_counts["films_reused"], 1)
        self.assertEqual(stored_counts["identity_reviews_created"], 1)
        self.assertNotIn("path", report_row["counts"].casefold())
        self.assertEqual(dry_run.counts["movies_skipped"], 6)
        self.assertEqual(repeated.counts["movies_skipped"], 6)
        self.assertEqual(first_counts, second_counts)

    @staticmethod
    def _durable_counts(connection) -> dict[str, int]:
        return {
            table: connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one()
            for table in (
                "film",
                "external_identity",
                "library_item",
                "media_asset",
                "legacy_movie_alias",
                "identity_review",
            )
        }


if __name__ == "__main__":
    unittest.main()
