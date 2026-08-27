import hashlib
import tempfile
import unittest
from pathlib import Path

from sqlmodel import Session, create_engine, delete, select

import app.database as database
import app.services.event_store as event_store_module
import app.services.graph_query as graph_query_module
import app.services.library as library_module
import app.services.operation_snapshots as snapshots_module
import app.services.user_state as user_state_module
from app.canonical_models import (
    Assertion,
    AssertionProvenance,
    Concept,
    Credit,
    CreditProvenance,
    GraphEntity,
    GraphNodeReadModel,
    Person,
    ProjectionState,
)
from app.contracts.analysis_persistence import assertion_qualifier_hash, assertion_semantic_key
from app.contracts.structured_metadata import credit_semantic_key, normalize_metadata_text
from app.database import configure_sqlite_engine
from app.migrations.runner import run_migrations
from app.services.graph_query import graph_query_service
from app.services.library import library_manager
from app.services.projections import ProjectionUnavailable, projection_coordinator


NOW = "2026-08-27T00:00:00+00:00"


class GraphQueryTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.database_path = self.root / "library.db"
        self.engine = create_engine(f"sqlite:///{self.database_path}")
        configure_sqlite_engine(self.engine)
        run_migrations(self.engine, self.database_path, app_version="test", backup_required=False)
        projection_coordinator.bootstrap(self.engine)
        self._engines = {
            module: module.engine
            for module in (
                database,
                event_store_module,
                graph_query_module,
                library_module,
                snapshots_module,
                user_state_module,
            )
        }
        for module in self._engines:
            module.engine = self.engine
        self.film_id = self._seed()

    def tearDown(self):
        for module, original in self._engines.items():
            module.engine = original
        self.engine.dispose()
        self._tmp.cleanup()

    def test_graph_contains_selected_credits_and_accepted_factual_assertions_only(self):
        with Session(self.engine) as session:
            self._add_director(session)
            concepts = session.exec(select(Concept).where(Concept.kind == "genre").order_by(Concept.id)).all()
            self._add_assertion(session, concepts[0], status="accepted", scope="factual")
            hidden_id = self._add_assertion(session, concepts[1], status="proposed", scope="inferred")
            session.commit()

        graph = graph_query_service.get_film_graph(self.film_id)
        self.assertEqual(graph["visibility_policy"], "graph-visibility.v1")
        self.assertEqual([edge["relation"] for edge in graph["edges"]], ["HAS_GENRE", "DIRECTED_BY"])
        self.assertNotIn(hidden_id, {edge["id"] for edge in graph["edges"]})
        self.assertTrue(all(edge["review_status"] == "accepted" for edge in graph["edges"]))
        self.assertTrue(all("origin_ref" not in edge for edge in graph["edges"]))

    def test_stale_graph_projection_is_not_silently_rebuilt(self):
        with Session(self.engine) as session:
            session.exec(delete(ProjectionState).where(ProjectionState.name == "graph_edges"))
            session.commit()
        with self.assertRaises(ProjectionUnavailable):
            graph_query_service.get_film_graph(self.film_id)

    def test_unknown_film_returns_none(self):
        self.assertIsNone(graph_query_service.get_film_graph("film_" + "f" * 32))

    def _seed(self) -> str:
        folder = self.root / "graph"
        folder.mkdir()
        path = folder / "graph.mkv"
        path.write_bytes(b"graph")
        library_manager.add_observations([
            {
                "title": "Graph Film",
                "original_title": "Graph Film",
                "year": 2026,
                "media_path": str(path.resolve()),
                "video_file": path.name,
                "folder_path": str(folder.resolve()),
                "folder_name": folder.name,
                "file_size": path.stat().st_size,
                "file_mtime": path.stat().st_mtime,
                "library_status": "available",
                "metadata_source": "filename",
                "scrape_status": "pending",
                "last_seen_at": NOW,
            }
        ])
        with Session(self.engine) as session:
            return session.exec(select(GraphEntity.id).where(GraphEntity.entity_type == "film")).one()

    def _add_director(self, session: Session) -> None:
        person_id = "person_" + "d" * 32
        session.add(GraphEntity(id=person_id, entity_type="person", lifecycle_status="active"))
        session.add(
            Person(
                id=person_id,
                canonical_name="Director Example",
                normalized_name=normalize_metadata_text("Director Example"),
                resolution_status="verified",
                lifecycle_status="active",
            )
        )
        session.flush()
        credit_id = "credit_" + "d" * 32
        session.add(
            Credit(
                id=credit_id,
                film_id=self.film_id,
                person_id=person_id,
                department="Directing",
                job="Director",
                semantic_key=credit_semantic_key(
                    self.film_id, person_id, "Directing", "Director"
                ),
            )
        )
        session.add(
            CreditProvenance(
                id="cprov_" + "d" * 32,
                credit_id=credit_id,
                origin_kind="nfo",
                origin_ref="lib_graph",
                observed_at=NOW,
            )
        )

    def _add_assertion(self, session: Session, concept: Concept, *, status: str, scope: str) -> str:
        qualifier_hash = assertion_qualifier_hash({})
        assertion_key = assertion_semantic_key(
            subject_entity_id=self.film_id,
            predicate="HAS_GENRE",
            object_entity_id=concept.id,
            qualifier_hash=qualifier_hash,
        )
        assertion_id = "assert_" + hashlib.sha256(assertion_key.encode()).hexdigest()[:32]
        session.add(
            Assertion(
                id=assertion_id,
                subject_entity_id=self.film_id,
                object_entity_id=concept.id,
                predicate="HAS_GENRE",
                qualifiers={},
                qualifier_hash=qualifier_hash,
                assertion_key=assertion_key,
                source_scope=scope,
                review_status=status,
                review_method="import_policy" if status == "accepted" else "none",
                review_policy_version="test.v1" if status == "accepted" else None,
                reviewed_at=NOW if status == "accepted" else None,
                first_seen_at=NOW,
                last_seen_at=NOW,
            )
        )
        session.add(
            AssertionProvenance(
                id="aprov_" + hashlib.sha256((assertion_id + scope).encode()).hexdigest()[:32],
                assertion_id=assertion_id,
                origin_kind="nfo" if scope == "factual" else "rule",
                origin_scope=scope,
                origin_ref=f"test:{scope}:{concept.id}",
                source_field="genres",
                first_observed_at=NOW,
                last_observed_at=NOW,
            )
        )
        return f"assertion:{assertion_id}"


if __name__ == "__main__":
    unittest.main()
