import tempfile
import unittest
import json
import shutil
from unittest.mock import patch
from pathlib import Path

from sqlalchemy import text
from sqlmodel import SQLModel, Session, create_engine, select

import app.services.event_store as event_store_module
import app.services.library as library_module
import app.services.user_state as user_state_module
from app.database import configure_sqlite_engine
from app.jobs.runtime import JobRuntime
from app.migrations.runner import run_migrations
from app.models import Job, Viewing
from app.services.canonical_runtime import canonical_runtime_writer
from app.services.file_identity import FOREGROUND_BUDGET_BYTES, full_content_hash, observe_file
from app.services.canonical_shadow import CanonicalShadowReader
from app.services.compatibility_projection import rebuild_legacy_compatibility_projections
from app.services.library import library_manager
from app.services.library_sync import library_sync_service
from app.services.user_state import movie_user_state_manager


class CanonicalRuntimeTests(unittest.TestCase):
    def setUp(self):
        self._original_library_engine = library_module.engine
        self._original_event_engine = event_store_module.engine
        self._original_user_state_engine = user_state_module.engine
        self._tmp = tempfile.TemporaryDirectory()
        self.database_path = Path(self._tmp.name) / "runtime.db"
        self.engine = create_engine(f"sqlite:///{self.database_path}")
        configure_sqlite_engine(self.engine)
        import app.models  # noqa: F401

        SQLModel.metadata.create_all(self.engine)
        run_migrations(
            self.engine,
            self.database_path,
            app_version="test",
            backup_required=False,
        )
        library_module.engine = self.engine
        event_store_module.engine = self.engine
        user_state_module.engine = self.engine
        self.reader = CanonicalShadowReader(self.engine)

    def tearDown(self):
        library_module.engine = self._original_library_engine
        event_store_module.engine = self._original_event_engine
        user_state_module.engine = self._original_user_state_engine
        self.engine.dispose()
        self._tmp.cleanup()

    def test_new_runtime_movies_dual_write_and_reuse_exact_external_identity(self):
        added = library_manager.add_movies([
            self._movie("scanner_a", "/media/edition-a/movie.mkv"),
            self._movie("scanner_b", "/media/edition-b/movie.mkv"),
        ])

        legacy_movies = library_manager.get_movies()
        self.assertEqual(added, 2)
        self.assertEqual(len(legacy_movies), 2)
        self.assertTrue(all(movie["id"].startswith("lib_") for movie in legacy_movies))
        self.assertEqual(
            sorted(self.reader.get_movie(movie["id"])["media_path"] for movie in legacy_movies),
            ["/media/edition-a/movie.mkv", "/media/edition-b/movie.mkv"],
        )
        with self.engine.connect() as connection:
            counts = {
                table: connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one()
                for table in ("film", "library_item", "legacy_movie_alias")
            }
        self.assertEqual(counts, {"film": 1, "library_item": 2, "legacy_movie_alias": 2})

    def test_startup_projection_calibration_repairs_drift_and_is_idempotent(self):
        library_manager.add_movies([self._movie("projection_drift", "/media/drift/movie.mkv")])
        movie_id = library_manager.get_movies()[0]["id"]
        movie_user_state_manager.upsert(
            movie_id,
            favorite=True,
            fields_set={"favorite"},
        )
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE movie SET overview=NULL, folder_path='legacy\\\\drift' "
                    "WHERE id=:movie_id"
                ),
                {"movie_id": movie_id},
            )
            connection.execute(
                text(
                    "UPDATE movie_user_state SET updated_at='2000-01-01T00:00:00+00:00' "
                    "WHERE movie_id=:movie_id"
                ),
                {"movie_id": movie_id},
            )

        before_movie = self.reader.compare_movie(movie_id)
        before_state = self.reader.compare_user_states()
        first = rebuild_legacy_compatibility_projections(self.engine)
        second = rebuild_legacy_compatibility_projections(self.engine)

        self.assertGreater(before_movie.records_different, 0)
        self.assertGreater(before_state.records_different, 0)
        self.assertEqual(self.reader.compare_movie(movie_id).records_different, 0)
        self.assertEqual(self.reader.compare_user_states().records_different, 0)
        self.assertEqual(first, {"movies_updated": 1, "user_states_updated": 1})
        self.assertEqual(second, {"movies_updated": 0, "user_states_updated": 0})

    def test_library_read_source_defaults_to_canonical_and_can_roll_back_to_legacy(self):
        library_manager.add_movies([self._movie("scanner_read", "/media/read/movie.mkv")])
        compatibility_id = library_manager.get_movies()[0]["id"]
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE movie SET title = 'Legacy Drift', title_cn = '旧投影漂移' "
                    "WHERE id = :id"
                ),
                {"id": compatibility_id},
            )

        with patch.dict("os.environ", {}, clear=False):
            self.assertEqual(library_manager.get_movie(compatibility_id)["title"], "Runtime Film")
            self.assertEqual(library_manager.get_movie(compatibility_id)["title_cn"], "运行时电影")
        with patch.dict("os.environ", {"LIBRARY_READ_SOURCE": "legacy"}):
            self.assertEqual(library_manager.get_movie(compatibility_id)["title"], "Legacy Drift")
            self.assertEqual(library_manager.get_movie(compatibility_id)["title_cn"], "旧投影漂移")
        with patch.dict("os.environ", {"LIBRARY_READ_SOURCE": "shadow"}), self.assertLogs(
            "compatibility_reads", level="INFO"
        ) as shadow_logs:
            self.assertEqual(library_manager.get_movie(compatibility_id)["title"], "Legacy Drift")
        shadow_output = "\n".join(shadow_logs.output)
        self.assertIn('"field": "title"', shadow_output)
        self.assertNotIn("Legacy Drift", shadow_output)
        self.assertNotIn("旧投影漂移", shadow_output)
        with patch.dict("os.environ", {"LIBRARY_READ_SOURCE": "invalid"}):
            self.assertEqual(library_manager.get_movie(compatibility_id)["title"], "Legacy Drift")

    def test_canonical_library_preserves_legacy_sort_order(self):
        lowercase = {
            **self._movie("sort-lower", "/media/sort-lower/movie.mkv"),
            "title": "alpha",
            "title_cn": None,
            "tmdb_id": "5001",
        }
        uppercase = {
            **self._movie("sort-upper", "/media/sort-upper/movie.mkv"),
            "title": "Beta",
            "title_cn": None,
            "tmdb_id": "5002",
        }
        library_manager.add_movies([lowercase, uppercase])

        with patch.dict("os.environ", {"LIBRARY_READ_SOURCE": "legacy"}):
            legacy_ids = [movie["id"] for movie in library_manager.get_movies()]
        with patch.dict("os.environ", {"LIBRARY_READ_SOURCE": "canonical"}):
            canonical_ids = [movie["id"] for movie in library_manager.get_movies()]

        self.assertEqual(canonical_ids, legacy_ids)

    def test_user_state_is_shared_across_aliases_and_unwatch_preserves_diary(self):
        library_manager.add_movies([
            self._movie("scanner_state_a", "/media/state-a/movie.mkv"),
            self._movie("scanner_state_b", "/media/state-b/movie.mkv"),
        ])
        movie_ids = [movie["id"] for movie in library_manager.get_movies()]
        state = movie_user_state_manager.upsert(
            movie_ids[0],
            watched=True,
            rating=4,
            favorite=True,
            notes="Compatibility note",
            fields_set={"watched", "rating", "favorite", "notes"},
        )
        self.assertTrue(state["watched"])
        self.assertEqual(movie_user_state_manager.get(movie_ids[1]), {**state, "movie_id": movie_ids[1]})
        self.assertEqual(len(movie_user_state_manager.list_all()), 2)

        with self.engine.begin() as connection:
            alias = connection.execute(
                text(
                    "SELECT a.film_id, lp.id AS profile_id FROM legacy_movie_alias a "
                    "CROSS JOIN local_profile lp WHERE a.legacy_movie_id = :id "
                    "AND lp.profile_key = 'local'"
                ),
                {"id": movie_ids[0]},
            ).mappings().one()
        from sqlmodel import Session

        with Session(self.engine) as session:
            session.add(
                Viewing(
                    id="view_diary_runtime",
                    profile_id=alias["profile_id"],
                    film_id=alias["film_id"],
                    watched_at="2026-08-24",
                    watched_at_precision="date",
                    rating=5,
                    review="Diary note",
                    source="diary",
                    source_record_id="diary-runtime",
                    review_status="confirmed",
                )
            )
            session.commit()

        unwatched = movie_user_state_manager.upsert(
            movie_ids[0],
            watched=False,
            fields_set={"watched"},
        )
        self.assertTrue(unwatched["watched"])
        self.assertEqual(unwatched["rating"], 5)
        with self.engine.connect() as connection:
            active_compatibility = connection.execute(
                text(
                    "SELECT COUNT(*) FROM viewing WHERE film_id = :film "
                    "AND source IN ('legacy_movie_user_state', 'legacy_user_state_api') "
                    "AND deleted_at IS NULL"
                ),
                {"film": alias["film_id"]},
            ).scalar_one()
            diary_active = connection.execute(
                text("SELECT deleted_at FROM viewing WHERE id = 'view_diary_runtime'")
            ).scalar_one()
        self.assertEqual(active_compatibility, 0)
        self.assertIsNone(diary_active)
        with patch.dict("os.environ", {"LIBRARY_READ_SOURCE": "legacy"}):
            self.assertTrue(movie_user_state_manager.get(movie_ids[1])["watched"])
            self.assertEqual(movie_user_state_manager.get(movie_ids[1])["rating"], 5)
        history = movie_user_state_manager.watch_history()
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["movie"]["id"], min(movie_ids))

    def test_rating_without_confirmed_watch_is_reviewable_but_not_watch_history(self):
        library_manager.add_movies([self._movie("review-state", "/media/review-state/movie.mkv")])
        movie_id = library_manager.get_movies()[0]["id"]

        state = movie_user_state_manager.upsert(
            movie_id,
            rating=3,
            notes="Remember why",
            fields_set={"rating", "notes"},
        )

        self.assertFalse(state["watched"])
        self.assertEqual(state["rating"], 3)
        self.assertEqual(len(movie_user_state_manager.list_all()), 1)
        self.assertEqual(movie_user_state_manager.watch_history(), [])
        with patch.dict("os.environ", {"LIBRARY_READ_SOURCE": "legacy"}):
            self.assertFalse(movie_user_state_manager.get(movie_id)["watched"])
            self.assertEqual(movie_user_state_manager.get(movie_id)["notes"], "Remember why")

        revised = movie_user_state_manager.upsert(
            movie_id,
            watched=False,
            rating=2,
            notes="Keep for review",
            fields_set={"watched", "rating", "notes"},
        )
        self.assertFalse(revised["watched"])
        self.assertEqual(revised["rating"], 2)
        self.assertEqual(revised["notes"], "Keep for review")
        movie_user_state_manager.upsert(movie_id, watched=False, fields_set={"watched"})
        self.assertEqual(movie_user_state_manager.list_all(), [])

    def test_file_rename_relinks_by_platform_identity_and_preserves_compatibility_id(self):
        original_folder = Path(self._tmp.name) / "original"
        renamed_folder = Path(self._tmp.name) / "renamed"
        original_folder.mkdir()
        video = original_folder / "movie.mkv"
        video.write_bytes(b"runtime-video" * 1024)
        first = self._movie("scanner_original", str(video))
        first["file_size"] = video.stat().st_size
        first["file_mtime"] = video.stat().st_mtime
        library_manager.add_movies([first])
        compatibility_id = library_manager.get_movies()[0]["id"]

        original_folder.rename(renamed_folder)
        renamed_video = renamed_folder / "movie.mkv"
        moved = self._movie("scanner_renamed", str(renamed_video))
        moved["file_size"] = renamed_video.stat().st_size
        moved["file_mtime"] = renamed_video.stat().st_mtime
        added = library_manager.add_movies([moved])

        movies = library_manager.get_movies()
        self.assertEqual(added, 0)
        self.assertEqual([movie["id"] for movie in movies], [compatibility_id])
        self.assertEqual(movies[0]["media_path"], str(renamed_video))
        with self.engine.connect() as connection:
            self.assertEqual(
                connection.execute(text("SELECT COUNT(*) FROM library_item")).scalar_one(),
                1,
            )
            history = connection.execute(
                text(
                    "SELECT source_item_key, observed_to FROM library_item_locator_history "
                    "ORDER BY observed_from"
                )
            ).mappings().all()
        self.assertEqual(len(history), 2)
        self.assertIsNotNone(history[0]["observed_to"])
        self.assertEqual(history[1]["source_item_key"], str(renamed_folder).replace("\\", "/"))

    def test_clear_library_retires_collection_but_rescan_restores_alias_and_personal_state(self):
        movie = self._movie("scanner_clear_restore", "/media/clear-restore/movie.mkv")
        library_manager.add_movies([movie])
        compatibility_id = library_manager.get_movies()[0]["id"]
        movie_user_state_manager.upsert(
            compatibility_id,
            watched=True,
            favorite=True,
            notes="Keep me",
            fields_set={"watched", "favorite", "notes"},
        )

        library_manager.clear_library()

        self.assertEqual(library_manager.get_movies(), [])
        self.assertIsNone(library_manager.get_movie(compatibility_id))
        with self.engine.connect() as connection:
            self.assertEqual(connection.execute(text("SELECT COUNT(*) FROM film")).scalar_one(), 1)
            self.assertEqual(connection.execute(text("SELECT COUNT(*) FROM viewing")).scalar_one(), 1)

        library_manager.add_movies([movie])

        self.assertEqual([item["id"] for item in library_manager.get_movies()], [compatibility_id])
        self.assertTrue(movie_user_state_manager.get(compatibility_id)["favorite"])
        with self.engine.connect() as connection:
            self.assertEqual(
                connection.execute(
                    text(
                        "SELECT availability_status FROM media_asset "
                        "WHERE library_item_id = :id AND asset_kind = 'video'"
                    ),
                    {"id": compatibility_id},
                ).scalar_one(),
                "present",
            )
        with patch.dict("os.environ", {"LIBRARY_READ_SOURCE": "legacy"}):
            restored = movie_user_state_manager.get(compatibility_id)
            self.assertTrue(restored["watched"])
            self.assertTrue(restored["favorite"])
            self.assertEqual(restored["notes"], "Keep me")

    def test_pending_file_reconcile_clear_restore_preserves_permanent_alias(self):
        media_root = Path(self._tmp.name) / "media"
        movie_folder = media_root / "Pending Film (2026)"
        movie_folder.mkdir(parents=True)
        (movie_folder / "Pending Film (2026).mp4").write_bytes(b"pending-video")

        first = library_sync_service.reconcile(str(media_root))
        library_sync_service.reconcile(str(media_root))
        original_id = library_manager.get_movies()[0]["id"]
        movie_user_state_manager.upsert(
            original_id,
            favorite=True,
            fields_set={"favorite"},
        )

        library_manager.clear_library()
        restored = library_sync_service.reconcile(str(media_root))

        self.assertEqual(first["scanned"], 1)
        self.assertEqual(restored["scanned"], 1)
        self.assertEqual([movie["id"] for movie in library_manager.get_movies()], [original_id])
        self.assertTrue(movie_user_state_manager.get(original_id)["favorite"])

    def test_public_job_redacts_internal_paths_from_all_exposed_fields(self):
        media_root = str((Path(self._tmp.name) / "private-media").resolve())
        internal = {
            "id": "job_private_path",
            "type": "library.reconcile",
            "status": "succeeded",
            "payload": {"media_dir": media_root},
            "result": {"status": "success", "media_dir": media_root, "scanned": 1},
            "result_summary": f"Scanned private media at {media_root}",
            "error": f"Previous path: {media_root}",
            "dedupe_key": f"library.reconcile:{media_root}",
        }
        public = JobRuntime.public_job(internal)

        self.assertNotIn(media_root, json.dumps(public))
        self.assertEqual(public["payload"], {})
        self.assertEqual(public["result"], {"status": "success", "scanned": 1})

        queued_internal = {
            **internal,
            "status": "queued",
            "result": None,
            "result_summary": None,
            "error": None,
        }
        with patch("app.jobs.runtime.job_store") as store, patch(
            "app.jobs.runtime.library_event_bus"
        ) as event_bus:
            store.find_active.return_value = None
            store.create.return_value = queued_internal
            accepted = JobRuntime().enqueue(
                "library.reconcile",
                {"media_dir": media_root},
                dedupe_key=f"library.reconcile:{media_root}",
            )

        self.assertNotIn(media_root, json.dumps(accepted))
        self.assertEqual(accepted["payload"], {})
        event_bus.publish.assert_called_once_with("job_queued", {"job": accepted})

    def test_missing_cleanup_retires_item_and_rescan_restores_state(self):
        movie = self._movie("cleanup-restore", "/media/cleanup-restore/movie.mkv")
        library_manager.add_movies([movie])
        movie_id = library_manager.get_movies()[0]["id"]
        movie_user_state_manager.upsert(
            movie_id,
            watched=True,
            fields_set={"watched"},
        )
        library_manager.mark_missing_not_seen_since("9999-01-01T00:00:00+00:00")

        self.assertEqual(library_manager.cleanup_missing(), 1)
        self.assertIsNone(library_manager.get_movie(movie_id))

        library_manager.add_movies([movie])

        self.assertEqual([item["id"] for item in library_manager.get_movies()], [movie_id])
        self.assertTrue(movie_user_state_manager.get(movie_id)["watched"])

    def test_clear_all_data_removes_domain_rows_but_preserves_migration_journal(self):
        library_manager.add_movies([self._movie("clear-all", "/media/clear-all/movie.mkv")])
        movie_id = library_manager.get_movies()[0]["id"]
        movie_user_state_manager.upsert(
            movie_id,
            watched=True,
            favorite=True,
            fields_set={"watched", "favorite"},
        )
        with self.engine.connect() as connection:
            journal_before = connection.execute(
                text("SELECT COUNT(*) FROM schema_migrations")
            ).scalar_one()

        result = library_manager.clear_all_data()

        self.assertEqual(set(result), {"user_states", "movies", "jobs", "events"})
        with self.engine.connect() as connection:
            for table in (
                "movie_user_state",
                "movie",
                "viewing",
                "film_profile_state",
                "media_asset",
                "library_item_locator_history",
                "legacy_movie_alias",
                "library_item",
                "external_identity",
                "film",
                "graph_entity",
                "local_profile",
                "canonical_backfill_run",
                "events",
                "job",
            ):
                self.assertEqual(
                    connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one(),
                    0,
                    table,
                )
            self.assertEqual(
                connection.execute(text("SELECT COUNT(*) FROM schema_migrations")).scalar_one(),
                journal_before,
            )

    def test_large_file_identity_never_reads_more_than_twelve_mib_in_foreground(self):
        video = Path(self._tmp.name) / "large.mkv"
        with video.open("wb") as stream:
            stream.seek(13 * 1024 * 1024 - 1)
            stream.write(b"\0")

        observation = observe_file(video)

        self.assertIsNotNone(observation)
        self.assertEqual(observation.bytes_read, FOREGROUND_BUDGET_BYTES)
        self.assertIsNone(observation.content_hash)

    def test_identity_conflict_never_relinks_even_when_file_fingerprint_matches(self):
        original = Path(self._tmp.name) / "identity-a" / "movie.mkv"
        copy = Path(self._tmp.name) / "identity-b" / "movie.mkv"
        original.parent.mkdir()
        copy.parent.mkdir()
        original.write_bytes(b"same-content" * 1024)
        shutil.copyfile(original, copy)
        library_manager.add_movies([self._movie("identity-a", str(original))])
        original_id = library_manager.get_movies()[0]["id"]
        conflicting = self._movie("identity-b", str(copy))
        conflicting["tmdb_id"] = "9999"

        added = library_manager.add_movies([conflicting])

        self.assertEqual(added, 1)
        self.assertEqual(len(library_manager.get_movies()), 2)
        with self.engine.connect() as connection:
            review = connection.execute(
                text(
                    "SELECT li.resolution_status, e.payload FROM library_item li "
                    "JOIN events e ON e.aggregate_id = li.id "
                    "WHERE li.id <> :original_id AND e.type = 'LibraryItemRelinkNeedsReview'"
                ),
                {"original_id": original_id},
            ).mappings().one()
        self.assertEqual(review["resolution_status"], "review_required")
        self.assertNotIn(str(copy), str(review["payload"]))
        self.assertNotIn("Runtime Film", str(review["payload"]))

    def test_canonical_failure_rolls_back_legacy_and_canonical_rows(self):
        with patch.object(
            canonical_runtime_writer,
            "_sync_assets",
            side_effect=RuntimeError("simulated canonical failure"),
        ):
            with self.assertRaisesRegex(RuntimeError, "simulated canonical failure"):
                library_manager.add_movies(
                    [self._movie("rollback", "/media/rollback/movie.mkv")]
                )

        with self.engine.connect() as connection:
            self.assertEqual(connection.execute(text("SELECT COUNT(*) FROM movie")).scalar_one(), 0)
            self.assertEqual(connection.execute(text("SELECT COUNT(*) FROM film")).scalar_one(), 0)
            self.assertEqual(
                connection.execute(text("SELECT COUNT(*) FROM graph_entity")).scalar_one(),
                0,
            )

    def test_ambiguous_fast_fingerprint_queues_deduped_relink_job_and_full_hash_relinks(self):
        size = 13 * 1024 * 1024
        first_path = Path(self._tmp.name) / "first" / "movie.mkv"
        second_path = Path(self._tmp.name) / "second" / "movie.mkv"
        moved_path = Path(self._tmp.name) / "moved" / "movie.mkv"
        for path, first_byte in ((first_path, b"A"), (second_path, b"B")):
            path.parent.mkdir()
            with path.open("wb") as stream:
                stream.write(first_byte)
                stream.seek(size - 1)
                stream.write(b"\0")
        with second_path.open("r+b") as stream:
            stream.seek(4 * 1024 * 1024 + 128)
            stream.write(b"different-full-hash")

        library_manager.add_movies([self._movie("first", str(first_path))])
        first_id = library_manager.get_movies()[0]["id"]
        library_manager.add_movies([self._movie("second", str(second_path))])
        second_id = next(
            movie["id"] for movie in library_manager.get_movies() if movie["id"] != first_id
        )

        # Make both stored candidates share the same quick fingerprint while retaining
        # different complete content hashes.
        with second_path.open("r+b") as stream:
            stream.seek(0)
            stream.write(b"A")
        shared_fingerprint = observe_file(first_path).content_fingerprint
        first_complete_hash = full_content_hash(first_path)
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE media_asset SET content_fingerprint = :fingerprint, content_hash = NULL "
                    "WHERE library_item_id IN (:first_id, :second_id) AND asset_kind = 'video'"
                ),
                {
                    "fingerprint": shared_fingerprint,
                    "first_id": first_id,
                    "second_id": second_id,
                },
            )
            connection.execute(
                text(
                    "UPDATE media_asset SET content_hash = :content_hash "
                    "WHERE library_item_id = :first_id AND asset_kind = 'video'"
                ),
                {"content_hash": first_complete_hash, "first_id": first_id},
            )
        moved_path.parent.mkdir()
        shutil.copyfile(first_path, moved_path)
        first_path.unlink()

        added = library_manager.add_movies([self._movie("moved", str(moved_path))])
        library_manager.add_movies([self._movie("moved-again", str(moved_path))])

        self.assertEqual(added, 0)
        with Session(self.engine) as session:
            jobs = session.exec(select(Job).where(Job.type == "library.resolve_relink")).all()
            self.assertEqual(len(jobs), 1)
            payload = jobs[0].payload
            public = __import__("app.jobs.runtime", fromlist=["JobRuntime"]).JobRuntime.public_job(
                jobs[0].model_dump()
            )
        self.assertNotIn(str(moved_path), json.dumps(public))
        self.assertNotIn("Runtime Film", json.dumps(public))

        from app.jobs.actors import resolve_relink

        class Context:
            def progress(self, **_kwargs):
                return None

            def raise_if_cancelled(self):
                return None

        result = resolve_relink(payload, Context())

        self.assertEqual(result["status"], "relinked")
        self.assertEqual(result["matched"], 1)
        self.assertNotIn(str(moved_path), json.dumps(result))
        movies = library_manager.get_movies()
        self.assertEqual(len(movies), 2)
        self.assertEqual(library_manager.get_movie(first_id)["media_path"], str(moved_path))
        self.assertEqual(library_manager.get_movie(second_id)["media_path"], str(second_path))

    @staticmethod
    def _movie(scanner_id: str, media_path: str) -> dict:
        folder_path = str(Path(media_path).parent)
        return {
            "id": scanner_id,
            "title": "Runtime Film",
            "title_cn": "运行时电影",
            "year": 2026,
            "tmdb_id": "4242",
            "media_path": media_path,
            "folder_path": folder_path,
            "folder_name": Path(folder_path).name,
            "file_size": 123,
            "file_mtime": 456.0,
            "library_status": "available",
            "metadata_source": "nfo",
            "scrape_status": "matched",
        }


if __name__ == "__main__":
    unittest.main()
