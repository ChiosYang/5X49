import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlmodel import create_engine

from app.migrations.runner import run_migrations
from app.services.canonical_shadow import CanonicalShadowReader
from app.services.viewing_backfill import backfill_legacy_user_states


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "database" / "viewing-migration"


class ViewingMigrationTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.database_path = Path(self._tmp.name) / "viewing.db"
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
        self.shadow = CanonicalShadowReader(self.engine)

    def tearDown(self):
        self.engine.dispose()
        self._tmp.cleanup()

    def test_migration_preserves_favorite_and_creates_confirmed_and_review_viewings(self):
        with self.engine.connect() as connection:
            alias_films = {
                row["legacy_movie_id"]: row["film_id"]
                for row in connection.execute(
                    text("SELECT legacy_movie_id, film_id FROM legacy_movie_alias")
                ).mappings()
            }
            viewings = connection.execute(
                text(
                    "SELECT source_record_id, review_status, watched_at_precision, rating, review "
                    "FROM viewing ORDER BY source_record_id"
                )
            ).mappings().all()
            shared_state = connection.execute(
                text(
                    "SELECT favorite FROM film_profile_state WHERE film_id = :film"
                ),
                {"film": alias_films["viewing_a"]},
            ).scalar_one()
            empty_state = connection.execute(
                text(
                    "SELECT COUNT(*) FROM film_profile_state WHERE film_id = :film"
                ),
                {"film": alias_films["viewing_empty"]},
            ).scalar_one()

        self.assertEqual(alias_films["viewing_a"], alias_films["viewing_b"])
        self.assertTrue(shared_state)
        self.assertEqual(empty_state, 0)
        self.assertEqual(len(viewings), 2)
        self.assertEqual(viewings[0]["source_record_id"], "viewing_a")
        self.assertEqual(viewings[0]["review_status"], "confirmed")
        self.assertEqual(viewings[0]["watched_at_precision"], "timestamp")
        self.assertEqual(viewings[1]["source_record_id"], "viewing_b")
        self.assertEqual(viewings[1]["review_status"], "needs_review")
        self.assertEqual(viewings[1]["rating"], 3)
        self.assertEqual(viewings[1]["review"], "Needs review but must survive")

    def test_repeat_backfill_is_idempotent_and_initial_report_remains_auditable(self):
        with self.engine.begin() as connection:
            before = self._counts(connection)
            repeated = backfill_legacy_user_states(connection)
            after = self._counts(connection)
            stored = connection.execute(
                text(
                    "SELECT counts, warning_count FROM canonical_backfill_run "
                    "WHERE run_key = 'legacy_movie_user_state_to_viewing.v1'"
                )
            ).mappings().one()

        report_counts = json.loads(stored["counts"])
        self.assertEqual(before, after)
        self.assertEqual(repeated.counts["states_skipped"], 2)
        self.assertEqual(report_counts["states_scanned"], 4)
        self.assertEqual(report_counts["viewings_created"], 2)
        self.assertEqual(report_counts["empty_states_skipped"], 1)
        self.assertEqual(stored["warning_count"], 0)

    def test_shadow_state_shares_film_aggregate_and_excludes_needs_review_from_history(self):
        state_a = self.shadow.get_user_state("viewing_a")
        state_b = self.shadow.get_user_state("viewing_b")
        history = self.shadow.watch_history()

        self.assertEqual(state_a["favorite"], True)
        self.assertEqual(state_a["watched"], True)
        self.assertEqual(state_a["rating"], 5)
        self.assertEqual(state_b, {**state_a, "movie_id": "viewing_b"})
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["user_state"]["watched"], True)

    def test_shadow_reports_are_explainable_and_do_not_contain_raw_library_values(self):
        library_report = self.shadow.compare_library()
        state_report = self.shadow.compare_user_states()

        self.assertEqual(library_report.records_compared, 4)
        self.assertEqual(library_report.records_missing, 0)
        self.assertEqual(state_report.records_compared, 4)
        self.assertEqual(state_report.records_missing, 0)
        favorite_difference = next(
            difference
            for difference in state_report.differences
            if difference.field == "favorite"
            and difference.source_layer == "film_profile_state"
        )
        self.assertEqual(favorite_difference.source_layer, "film_profile_state")
        serialized = json.dumps(
            [difference.__dict__ for difference in library_report.differences],
            sort_keys=True,
        )
        self.assertNotIn("Edition-A", serialized)
        self.assertNotIn("Shared Viewing Film", serialized)

    def test_viewing_constraints_and_library_item_retirement_do_not_delete_history(self):
        with self.engine.connect() as connection:
            profile_id = connection.execute(
                text("SELECT id FROM local_profile WHERE profile_key = 'local'")
            ).scalar_one()
            alias = connection.execute(
                text(
                    "SELECT film_id, library_item_id FROM legacy_movie_alias "
                    "WHERE legacy_movie_id = 'viewing_a'"
                )
            ).mappings().one()

        with self.assertRaises(IntegrityError), self.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO viewing "
                    "(id, profile_id, film_id, watched_at_precision, rating, source, "
                    "source_record_id, review_status, created_at, updated_at) VALUES "
                    "('view_bad_rating', :profile, :film, 'unknown', 6, 'manual', "
                    "'bad', 'confirmed', :now, :now)"
                ),
                {
                    "profile": profile_id,
                    "film": alias["film_id"],
                    "now": "2026-08-21T00:00:00Z",
                },
            )

        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE library_item SET availability_status = 'retired', "
                    "retired_at = '2026-08-21T00:00:00Z' WHERE id = :item"
                ),
                {"item": alias["library_item_id"]},
            )
            viewing_count = connection.execute(
                text("SELECT COUNT(*) FROM viewing WHERE film_id = :film"),
                {"film": alias["film_id"]},
            ).scalar_one()
        self.assertEqual(viewing_count, 2)

    @staticmethod
    def _counts(connection):
        return {
            table: connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one()
            for table in ("film_profile_state", "viewing", "canonical_backfill_run")
        }


if __name__ == "__main__":
    unittest.main()
