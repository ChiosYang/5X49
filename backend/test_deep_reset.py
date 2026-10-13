"""Exercise production reset with foreign keys enabled on disposable data only."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import event, text
from sqlmodel import Session, create_engine, select

from app import database
from app.database import configure_sqlite_engine
from app.main import app
from app.migrations.runner import run_migrations
from app.models import Concept, ConceptAlias, Film, GraphEntity, Person, Setting
from app.services import event_store, library
from app.services.library_sync import LibrarySyncService
from app.services.projections import projection_coordinator


class DeepResetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="reset-")
        self.root = Path(self.temp.name)
        self.db_path = self.root / "db.sqlite"
        self.engine = create_engine(f"sqlite:///{self.db_path}")
        configure_sqlite_engine(self.engine)
        run_migrations(self.engine, self.db_path, backup_required=False)
        for module in (database, library, event_store):
            guard = patch.object(module, "engine", self.engine)
            guard.start()
            self.addCleanup(guard.stop)
        self.client = TestClient(app, raise_server_exceptions=False)
        with Session(self.engine) as session:
            session.add(Setting(key="language", value="en"))
            session.add(Setting(key="maintenance_backup_status", value={"sentinel": "preserve"}))
            session.commit()

    def tearDown(self):
        self.client.close()
        self.engine.dispose()
        self.temp.cleanup()

    def snapshot(self):
        with self.engine.connect() as connection:
            self.assertEqual(connection.exec_driver_sql("PRAGMA foreign_keys").scalar(), 1)
            self.assertEqual(connection.exec_driver_sql("PRAGMA foreign_key_check").all(), [])
            return "\n".join(connection.connection.driver_connection.iterdump())

    def retained_rows(self):
        tables = ("setting", "local_profile", "assertion_predicate", "concept", "concept_alias")
        with self.engine.connect() as connection:
            return {name: connection.exec_driver_sql(f"SELECT * FROM {name} ORDER BY 1").all()
                    for name in tables}

    def chain(self, model, prefix, *, reverse_ids=False, kind="theme"):
        # Target is inserted first in both ID orders, the order that broke reset.
        values = ("z", "m", "a") if reverse_ids else ("a", "m", "z")
        ids = [f"{prefix}_{value}" for value in values]
        with Session(self.engine) as session:
            for index, identifier in enumerate(ids):
                target = ids[index - 1] if index else None
                status = "merged" if target else "active"
                entity_type = {Film: "film", Person: "person", Concept: "concept"}[model]
                session.add(GraphEntity(id=identifier, entity_type=entity_type,
                    lifecycle_status=status, merged_into_id=target))
                session.flush()
                values = dict(id=identifier, lifecycle_status=status, merged_into_id=target)
                if model is Film:
                    values["canonical_title"] = identifier
                elif model is Person:
                    values.update(canonical_name=identifier, normalized_name=identifier)
                else:
                    values.update(kind=kind, canonical_key=identifier, canonical_name=identifier)
                session.add(model(**values))
                session.flush()
            session.commit()
        return ids

    def reset(self):
        response = self.client.delete("/library/data")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(set(body), {"status", "message", "deleted"})
        self.assertEqual(body["status"], "success")
        self.assertEqual(body["message"], "Library data cleared")
        self.assertEqual(set(body["deleted"]), {"films", "library_items", "jobs", "events"})
        self.snapshot()
        return body["deleted"]

    def test_empty_reset_is_repeatable_and_preserves_reference_settings(self):
        before = self.retained_rows()
        for _ in range(2):
            self.assertEqual(self.reset(), dict(films=0, library_items=0, jobs=0, events=0))
            self.assertEqual(self.retained_rows(), before)

    def test_film_alias_chains_reset_in_both_id_orders(self):
        before = self.retained_rows()
        for reverse_ids in (False, True):
            with self.subTest(reverse_ids=reverse_ids):
                ids = self.chain(Film, f"film_{int(reverse_ids)}", reverse_ids=reverse_ids)
                self.assertEqual(self.reset()["films"], 3)
                with Session(self.engine) as session:
                    self.assertEqual(session.exec(select(Film)).all(), [])
                    self.assertEqual(session.exec(select(GraphEntity).where(GraphEntity.id.in_(ids))).all(), [])
                self.assertEqual(self.retained_rows(), before)

    def test_person_alias_chains_keep_existing_graph_retention_scope(self):
        ids = self.chain(Person, "person")
        self.reset()
        with Session(self.engine) as session:
            self.assertEqual(session.exec(select(Person)).all(), [])
            # Reset has historically retained person GraphEntity rows.
            self.assertEqual(session.get(GraphEntity, ids[-1]).merged_into_id, ids[-2])

    def test_non_genre_concept_chains_removed_and_genre_chains_unchanged(self):
        kept = self.chain(Concept, "genre", kind="genre")
        before = self.retained_rows()
        removed = self.chain(Concept, "theme", reverse_ids=True)
        with Session(self.engine) as session:
            session.add(ConceptAlias(id="alias_theme", concept_id=removed[-1], alias="Theme alias",
                normalized_alias="theme alias", provenance_ref="synthetic"))
            session.commit()
        self.reset()
        self.assertEqual(self.retained_rows(), before)
        with Session(self.engine) as session:
            self.assertEqual(session.get(Concept, kept[-1]).merged_into_id, kept[-2])
            self.assertEqual(session.get(GraphEntity, kept[-1]).merged_into_id, kept[-2])
            self.assertTrue(all(session.get(GraphEntity, identifier) is None for identifier in removed))

    def test_retained_incoming_alias_only_detaches_if_target_is_removed(self):
        removed = self.chain(Concept, "theme")
        with Session(self.engine) as session:
            session.add(GraphEntity(id="genre_kept", entity_type="concept", lifecycle_status="merged",
                merged_into_id=removed[0]))
            session.flush()
            session.add(Concept(id="genre_kept", kind="genre", canonical_key="kept", canonical_name="Kept",
                lifecycle_status="merged", merged_into_id=removed[0]))
            session.commit()
        self.reset()
        with Session(self.engine) as session:
            self.assertIsNone(session.get(Concept, "genre_kept").merged_into_id)
            self.assertIsNone(session.get(GraphEntity, "genre_kept").merged_into_id)

    def test_graph_entity_aliases_do_not_block_film_deletion(self):
        ids = self.chain(Film, "film")
        # Isolate the graph constraint from Film's own merge references.
        with Session(self.engine) as session:
            session.exec(text("UPDATE film SET merged_into_id = NULL"))
            session.commit()
        self.assertEqual(self.reset()["films"], len(ids))

    def test_failure_after_unlink_and_deletes_rolls_back_exact_database(self):
        self.chain(Film, "film")
        self.chain(Person, "person")
        self.chain(Concept, "theme")
        before = self.snapshot()
        original = projection_coordinator.rebuild_all

        def fail_after_rebuild(session):
            original(session)
            raise RuntimeError("Synthetic failure after reset and projection rebuild")

        with patch.object(projection_coordinator, "rebuild_all", side_effect=fail_after_rebuild) as rebuild, patch(
            "app.api.library.library_event_bus.publish_library_changed") as publish:
            self.assertEqual(self.client.delete("/library/data").status_code, 500)
            publish.assert_not_called()
            rebuild.assert_called_once()
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.reset()["films"], 3)

    def test_failure_during_delete_rolls_back_unlinked_aliases(self):
        self.chain(Film, "film")
        before = self.snapshot()
        unlinked_counts = []

        def fail_delete(connection, _cursor, statement, _parameters, _context, _many):
            if statement.startswith("DELETE FROM film ") or statement == "DELETE FROM film":
                unlinked_counts.append(connection.exec_driver_sql(
                    "SELECT count(*) FROM film WHERE merged_into_id IS NOT NULL").scalar())
                raise RuntimeError("Synthetic delete failure")

        event.listen(self.engine, "before_cursor_execute", fail_delete)
        try:
            self.assertEqual(self.client.delete("/library/data").status_code, 500)
        finally:
            event.remove(self.engine, "before_cursor_execute", fail_delete)
        self.assertEqual(unlinked_counts, [0])
        self.assertEqual(self.snapshot(), before)

    def test_real_scan_reset_and_rescan_preserve_media(self):
        media = self.root / "media"
        media.mkdir()
        video = media / "Synthetic.mkv"
        video.write_bytes(b"disposable synthetic video")
        nfo = video.with_suffix(".nfo")
        nfo.write_text("<movie><title>Synthetic</title><year>2001</year><tmdbid>981001</tmdbid></movie>")
        before = {path.name: path.read_bytes() for path in media.iterdir()}
        service = LibrarySyncService()
        with patch("app.services.scanner.video_probe_service.probe", return_value={}):
            self.assertTrue(service.reconcile(str(media))["complete"])
            self.assertEqual(self.reset()["library_items"], 1)
            self.assertTrue(service.reconcile(str(media))["complete"])
        self.assertEqual(len(library.library_manager.list_films()), 1)
        self.assertEqual({path.name: path.read_bytes() for path in media.iterdir()}, before)


if __name__ == "__main__":
    unittest.main()
