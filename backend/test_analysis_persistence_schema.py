import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlmodel import SQLModel, create_engine

import app.models  # noqa: F401
import app.services.event_store as event_store_module
import app.services.library as library_module
from app.contracts.analysis_persistence import (
    ASSERTION_PREDICATE_DEFINITIONS,
    PREDICATE_VOCABULARY_VERSION,
    STRUCTURED_GENRE_IMPORT_POLICY_VERSION,
    AssertionPredicateKey,
    analysis_review_key,
    analysis_run_idempotency_key,
    assertion_qualifier_hash,
    assertion_semantic_key,
    evidence_semantic_key,
    normalize_evidence_uri,
    preserve_review_status,
    validate_analysis_review_candidate,
    validate_assertion_semantics,
    validate_automatic_assertion_decision,
)
from app.contracts.analysis_v2 import AnalysisPredicate
from app.database import configure_sqlite_engine
from app.migrations.runner import run_migrations
from app.migrations.versions import MIGRATIONS
from app.services.library import library_manager


ANALYSIS_TABLES = (
    "assertion_predicate",
    "analysis_run",
    "assertion",
    "evidence",
    "assertion_evidence",
    "assertion_provenance",
    "analysis_resolution_review",
)


class AnalysisPersistenceContractTests(unittest.TestCase):
    def test_predicate_registry_extends_but_does_not_widen_model_output(self):
        persisted = {item.key.value for item in ASSERTION_PREDICATE_DEFINITIONS}
        model = {item.value for item in AnalysisPredicate}

        self.assertEqual(PREDICATE_VOCABULARY_VERSION, "assertion-predicate.v1")
        self.assertEqual(len(persisted), 9)
        self.assertEqual(persisted - model, {AssertionPredicateKey.HAS_GENRE.value})
        self.assertNotIn(AssertionPredicateKey.HAS_GENRE.value, model)

    def test_deterministic_keys_use_canonical_content_and_version_dimensions(self):
        first_qualifier = assertion_qualifier_hash(
            {"relationship_type": "Visual", "period_start_year": 1999}
        )
        second_qualifier = assertion_qualifier_hash(
            {"period_start_year": 1999, "relationship_type": "Visual"}
        )
        self.assertEqual(first_qualifier, second_qualifier)
        assertion_key = assertion_semantic_key(
            subject_entity_id="film_" + "a" * 32,
            predicate="INFLUENCED_BY",
            object_entity_id="film_" + "b" * 32,
            qualifier_hash=first_qualifier,
        )
        self.assertRegex(assertion_key, r"^[0-9a-f]{64}$")

        arguments = {
            "film_id": "film_" + "a" * 32,
            "analysis_kind": "genealogy_v2",
            "provider": "openrouter",
            "model": "provider/model",
            "prompt_version": "genealogy-v2.1",
            "schema_version": "analysis-output.v2",
            "resolver_version": "resolver.v1",
            "policy_version": "policy.v1",
            "app_version": "0.1.0",
            "input_hash": "c" * 64,
        }
        first_run = analysis_run_idempotency_key(**arguments)
        self.assertEqual(first_run, analysis_run_idempotency_key(**arguments))
        self.assertNotEqual(
            first_run,
            analysis_run_idempotency_key(**{**arguments, "policy_version": "policy.v2"}),
        )

        first_evidence = evidence_semantic_key(
            source_uri="HTTPS://Example.com:443/source?b=2&a=1#fragment",
            content_hash="d" * 64,
            claim="  A bounded Claim ",
        )
        repeated_evidence = evidence_semantic_key(
            source_uri="https://example.com/source?a=1&b=2",
            content_hash="d" * 64,
            claim="a bounded claim",
        )
        self.assertEqual(first_evidence, repeated_evidence)

        candidate = {
            "target": {"entity_type": "film", "display_name": "Example", "release_year": 2001}
        }
        first_review = analysis_review_key(
            analysis_run_id="arun_" + "e" * 32,
            candidate_kind="entity_reference",
            reason_code="unresolved_reference",
            predicate="INFLUENCED_BY",
            candidate=candidate,
        )
        second_review = analysis_review_key(
            analysis_run_id="arun_" + "e" * 32,
            candidate_kind="entity_reference",
            reason_code="unresolved_reference",
            predicate="INFLUENCED_BY",
            candidate={"target": {"release_year": 2001, "display_name": "Example", "entity_type": "film"}},
        )
        self.assertEqual(first_review, second_review)

    def test_evidence_and_review_inputs_reject_private_or_sensitive_content(self):
        self.assertEqual(
            normalize_evidence_uri("HTTPS://Example.com:443/a?b=2&a=1#fragment"),
            "https://example.com/a?a=1&b=2",
        )
        for uri in (
            "file:///private/source",
            "http://127.0.0.1/source",
            "http://169.254.169.254/latest/meta-data",
            "http://user:password@example.com/source",
            "https://example.com/source?api_key=secret",
        ):
            with self.subTest(uri=uri), self.assertRaises(ValueError):
                normalize_evidence_uri(uri)
        for candidate in (
            {"path": "relative/private.nfo"},
            {"target": {"display_name": "C:\\Private\\movie.nfo"}},
            {"target": {"display_name": "sk-analysisSecret123"}},
            {"target": {"display_name": "x" * 5000}},
        ):
            with self.subTest(candidate=candidate), self.assertRaises(ValueError):
                validate_analysis_review_candidate(candidate)

    def test_semantics_and_automatic_review_protection_are_explicit(self):
        validate_assertion_semantics(
            predicate="HAS_GENRE",
            subject_entity_type="film",
            object_entity_type="concept",
            object_concept_kind="genre",
        )
        with self.assertRaises(ValueError):
            validate_assertion_semantics(
                predicate="HAS_GENRE",
                subject_entity_type="film",
                object_entity_type="concept",
                object_concept_kind="theme",
            )
        validate_automatic_assertion_decision(
            predicate="INFLUENCED_BY",
            source_scope="inferred",
            review_status="proposed",
            review_method="none",
            origin_kind="analysis_run",
        )
        validate_automatic_assertion_decision(
            predicate="HAS_GENRE",
            source_scope="factual",
            review_status="accepted",
            review_method="import_policy",
            review_policy_version=STRUCTURED_GENRE_IMPORT_POLICY_VERSION,
            origin_kind="tmdb",
        )
        with self.assertRaises(ValueError):
            validate_automatic_assertion_decision(
                predicate="INFLUENCED_BY",
                source_scope="inferred",
                review_status="accepted",
                review_method="import_policy",
                review_policy_version=STRUCTURED_GENRE_IMPORT_POLICY_VERSION,
                origin_kind="analysis_run",
            )
        self.assertEqual(preserve_review_status("accepted", "proposed"), "accepted")
        self.assertEqual(preserve_review_status("rejected", "proposed"), "rejected")
        self.assertEqual(preserve_review_status("proposed", "accepted"), "accepted")


class AnalysisPersistenceSchemaTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmp.name)
        self.database_path = self.tmp_path / "analysis.db"
        self.engine = create_engine(f"sqlite:///{self.database_path}")
        configure_sqlite_engine(self.engine)
        run_migrations(
            self.engine,
            self.database_path,
            app_version="test",
            backup_required=False,
        )
        self.now = "2026-08-25T00:00:00Z"
        self.film_a = "film_" + "a" * 32
        self.film_b = "film_" + "b" * 32
        self.concept = "concept_" + "c" * 32
        self.profile = "profile_" + "d" * 32
        self.run_id = "arun_" + "e" * 32
        self._insert_graph_foundation()

    def tearDown(self):
        self.engine.dispose()
        self._tmp.cleanup()

    def test_fresh_v1_analysis_schema_and_reference_rows_are_available(self):
        self.assertEqual(MIGRATIONS[-1].version, 1)
        inspector = inspect(self.engine)
        self.assertTrue(set(ANALYSIS_TABLES).issubset(inspector.get_table_names()))
        with self.engine.connect() as connection:
            rows = connection.execute(
                text(
                    "SELECT key, vocabulary_version FROM assertion_predicate ORDER BY key"
                )
            ).all()
        self.assertEqual(len(rows), 9)
        self.assertTrue(all(row[1] == PREDICATE_VOCABULARY_VERSION for row in rows))

        migrated_path = self.tmp_path / "migrated.db"
        with closing(sqlite3.connect(migrated_path)) as connection:
            connection.executescript(
                "CREATE TABLE movie (id VARCHAR PRIMARY KEY, title VARCHAR NOT NULL, "
                "year INTEGER NOT NULL);"
                "INSERT INTO movie VALUES ('legacy_analysis', 'Analysis Sentinel', 2001);"
            )
        migrated = create_engine(f"sqlite:///{migrated_path}")
        configure_sqlite_engine(migrated)
        try:
            run_migrations(migrated, migrated_path, app_version="test", backup_required=False)
            for table in ANALYSIS_TABLES:
                self.assertEqual(
                    self._schema_signature(self.engine, table),
                    self._schema_signature(migrated, table),
                    table,
                )
        finally:
            migrated.dispose()

    def test_analysis_run_constraints_and_idempotency(self):
        run_values = self._run_values()
        self._insert_run(run_values)
        with self.assertRaises(IntegrityError), self.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO analysis_run "
                    "(id, film_id, analysis_kind, provider, model, prompt_version, schema_version, "
                    "resolver_version, policy_version, app_version, input_hash, idempotency_key, "
                    "status, attempt_count, created_at, updated_at) VALUES "
                    "('arun_duplicate', :film_id, :analysis_kind, :provider, :model, "
                    ":prompt_version, :schema_version, :resolver_version, :policy_version, "
                    ":app_version, :input_hash, :idempotency_key, 'queued', 0, :now, :now)"
                ),
                {**run_values, "now": self.now},
            )
        with self.assertRaises(IntegrityError), self.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO analysis_run "
                    "(id, film_id, analysis_kind, provider, model, prompt_version, schema_version, "
                    "resolver_version, policy_version, app_version, input_hash, idempotency_key, "
                    "status, attempt_count, created_at, updated_at) VALUES "
                    "('arun_bad', :film_id, :analysis_kind, :provider, :model, :prompt_version, "
                    ":schema_version, :resolver_version, :policy_version, :app_version, "
                    ":input_hash, :other_key, 'succeeded', 0, :now, :now)"
                ),
                {**run_values, "other_key": "f" * 64, "now": self.now},
            )

    def test_assertion_evidence_provenance_and_review_constraints(self):
        run_values = self._run_values(status="succeeded")
        self._insert_run(run_values)
        qualifier_hash = assertion_qualifier_hash(None)
        assertion_key = assertion_semantic_key(
            subject_entity_id=self.film_a,
            predicate="HAS_GENRE",
            object_entity_id=self.concept,
            qualifier_hash=qualifier_hash,
        )
        evidence_key = evidence_semantic_key(
            source_uri="https://example.com/catalog/42",
            content_hash="6" * 64,
            claim="Catalog genre assignment",
        )
        candidate = {
            "target": {"entity_type": "film", "display_name": "Unknown", "release_year": 2002}
        }
        review_key, candidate_hash = analysis_review_key(
            analysis_run_id=self.run_id,
            candidate_kind="entity_reference",
            reason_code="unresolved_reference",
            predicate="INFLUENCED_BY",
            candidate=candidate,
        )
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO assertion "
                    "(id, subject_entity_id, object_entity_id, predicate, qualifiers, "
                    "qualifier_hash, assertion_key, source_scope, review_status, review_method, "
                    "review_policy_version, reviewed_at, first_seen_at, last_seen_at, created_at, updated_at) "
                    "VALUES ('ast_one', :subject, :object, 'HAS_GENRE', '{}', :qualifier_hash, "
                    ":assertion_key, 'factual', 'accepted', 'import_policy', :policy, :now, :now, :now, :now, :now)"
                ),
                {
                    "subject": self.film_a,
                    "object": self.concept,
                    "qualifier_hash": qualifier_hash,
                    "assertion_key": assertion_key,
                    "policy": STRUCTURED_GENRE_IMPORT_POLICY_VERSION,
                    "now": self.now,
                },
            )
            connection.execute(
                text(
                    "INSERT INTO evidence "
                    "(id, evidence_key, evidence_type, source_title, source_uri, claim, "
                    "retrieved_at, content_hash, verification_policy_version, created_at, updated_at) "
                    "VALUES ('evd_one', :key, 'catalog', 'Example Catalog', "
                    "'https://example.com/catalog/42', 'Catalog genre assignment', :now, "
                    ":content_hash, 'evidence-http.v1', :now, :now)"
                ),
                {"key": evidence_key, "content_hash": "6" * 64, "now": self.now},
            )
            connection.execute(
                text(
                    "INSERT INTO assertion_evidence "
                    "(id, assertion_id, evidence_id, stance, link_status, created_at) "
                    "VALUES ('aev_one', 'ast_one', 'evd_one', 'supports', 'active', :now)"
                ),
                {"now": self.now},
            )
            connection.execute(
                text(
                    "INSERT INTO assertion_provenance "
                    "(id, assertion_id, origin_kind, origin_scope, origin_ref, first_observed_at, last_observed_at) "
                    "VALUES ('aprov_one', 'ast_one', 'tmdb', 'factual', 'tmdb.movie:42', :now, :now)"
                ),
                {"now": self.now},
            )
            connection.execute(
                text(
                    "INSERT INTO analysis_resolution_review "
                    "(id, analysis_run_id, film_id, predicate, candidate_kind, reason_code, "
                    "candidate_summary, candidate_hash, review_key, status, created_at, updated_at) "
                    "VALUES ('arev_one', :run, :film, 'INFLUENCED_BY', 'entity_reference', "
                    "'unresolved_reference', :candidate, :candidate_hash, :review_key, 'open', :now, :now)"
                ),
                {
                    "run": self.run_id,
                    "film": self.film_a,
                    "candidate": json.dumps(candidate, ensure_ascii=False),
                    "candidate_hash": candidate_hash,
                    "review_key": review_key,
                    "now": self.now,
                },
            )

        for statement in (
            "DELETE FROM assertion WHERE id='ast_one'",
            "DELETE FROM evidence WHERE id='evd_one'",
            f"DELETE FROM analysis_run WHERE id='{self.run_id}'",
        ):
            with self.subTest(statement=statement), self.assertRaises(IntegrityError), self.engine.begin() as connection:
                connection.execute(text(statement))

        with self.assertRaises(IntegrityError), self.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO assertion "
                    "(id, subject_entity_id, object_entity_id, predicate, qualifiers, qualifier_hash, "
                    "assertion_key, source_scope, review_status, review_method, reviewed_at, first_seen_at, "
                    "last_seen_at, created_at, updated_at) VALUES "
                    "('ast_bad_review', :subject, :object, 'HAS_GENRE', '{}', :qualifier_hash, "
                    ":other_key, 'factual', 'accepted', 'import_policy', :now, :now, :now, :now, :now)"
                ),
                {
                    "subject": self.film_a,
                    "object": self.concept,
                    "qualifier_hash": qualifier_hash,
                    "other_key": "7" * 64,
                    "now": self.now,
                },
            )

        with self.assertRaises(IntegrityError), self.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO assertion "
                    "(id, subject_entity_id, object_entity_id, predicate, qualifiers, qualifier_hash, "
                    "assertion_key, source_scope, review_status, review_method, confidence, first_seen_at, "
                    "last_seen_at, created_at, updated_at) VALUES "
                    "('ast_bad_confidence', :subject, :object, 'HAS_GENRE', '{}', :qualifier_hash, "
                    ":other_key, 'factual', 'proposed', 'none', 0.8, :now, :now, :now, :now)"
                ),
                {
                    "subject": self.film_a,
                    "object": self.concept,
                    "qualifier_hash": qualifier_hash,
                    "other_key": "8" * 64,
                    "now": self.now,
                },
            )

    def test_library_clear_preserves_w4_data_and_deep_clear_preserves_registry(self):
        original_library_engine = library_module.engine
        original_event_engine = event_store_module.engine
        library_module.engine = self.engine
        event_store_module.engine = self.engine
        try:
            run_values = self._run_values()
            self._insert_run(run_values)
            before = self._counts(("analysis_run", "assertion_predicate"))
            library_manager.clear_library()
            self.assertEqual(self._counts(("analysis_run", "assertion_predicate")), before)

            result = library_manager.clear_all_data()
            self.assertEqual(set(result), {"films", "library_items", "jobs", "events"})
            self.assertEqual(self._counts(ANALYSIS_TABLES[1:]), {name: 0 for name in ANALYSIS_TABLES[1:]})
            self.assertEqual(self._counts(("assertion_predicate",))["assertion_predicate"], 9)
            with self.engine.connect() as connection:
                self.assertGreater(
                    connection.execute(text("SELECT COUNT(*) FROM schema_migrations")).scalar_one(),
                    0,
                )
        finally:
            library_module.engine = original_library_engine
            event_store_module.engine = original_event_engine

    def _insert_graph_foundation(self):
        with self.engine.begin() as connection:
            for entity_id, entity_type in (
                (self.film_a, "film"),
                (self.film_b, "film"),
                (self.concept, "concept"),
            ):
                connection.execute(
                    text(
                        "INSERT INTO graph_entity "
                        "(id, entity_type, lifecycle_status, created_at, updated_at) "
                        "VALUES (:id, :type, 'active', :now, :now)"
                    ),
                    {"id": entity_id, "type": entity_type, "now": self.now},
                )
            for film_id, title in ((self.film_a, "Film A"), (self.film_b, "Film B")):
                connection.execute(
                    text(
                        "INSERT INTO film "
                        "(id, canonical_title, lifecycle_status, created_at, updated_at) "
                        "VALUES (:id, :title, 'active', :now, :now)"
                    ),
                    {"id": film_id, "title": title, "now": self.now},
                )
            connection.execute(
                text(
                    "INSERT INTO concept "
                    "(id, kind, canonical_key, canonical_name, lifecycle_status, created_at, updated_at) "
                    "VALUES (:id, 'genre', 'test.genre', 'Test Genre', 'active', :now, :now)"
                ),
                {"id": self.concept, "now": self.now},
            )
            connection.execute(
                text(
                    "INSERT OR IGNORE INTO local_profile "
                    "(id, profile_key, display_name, created_at, updated_at) "
                    "VALUES (:id, 'test-profile', 'Test', :now, :now)"
                ),
                {"id": self.profile, "now": self.now},
            )

    def _run_values(self, status="queued"):
        values = {
            "id": self.run_id,
            "film_id": self.film_a,
            "analysis_kind": "genealogy_v2",
            "provider": "openrouter",
            "model": "provider/model",
            "prompt_version": "genealogy-v2.1",
            "schema_version": "analysis-output.v2",
            "resolver_version": "resolver.v1",
            "policy_version": "policy.v1",
            "app_version": "0.1.0",
            "input_hash": "4" * 64,
        }
        values["idempotency_key"] = analysis_run_idempotency_key(**{key: value for key, value in values.items() if key != "id"})
        values["status"] = status
        return values

    def _insert_run(self, values):
        succeeded = values["status"] == "succeeded"
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO analysis_run "
                    "(id, film_id, analysis_kind, provider, model, prompt_version, schema_version, "
                    "resolver_version, policy_version, app_version, input_hash, output_hash, "
                    "idempotency_key, status, attempt_count, result_summary, started_at, finished_at, "
                    "created_at, updated_at) VALUES "
                    "(:id, :film_id, :analysis_kind, :provider, :model, :prompt_version, "
                    ":schema_version, :resolver_version, :policy_version, :app_version, :input_hash, "
                    ":output_hash, :idempotency_key, :status, :attempt_count, :result_summary, "
                    ":started_at, :finished_at, :now, :now)"
                ),
                {
                    **values,
                    "output_hash": "5" * 64 if succeeded else None,
                    "attempt_count": 1 if succeeded else 0,
                    "result_summary": "Validated summary" if succeeded else None,
                    "started_at": self.now if succeeded else None,
                    "finished_at": self.now if succeeded else None,
                    "now": self.now,
                },
            )

    def _counts(self, tables):
        with self.engine.connect() as connection:
            return {
                table: connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one()
                for table in tables
            }

    @staticmethod
    def _schema_signature(engine, table):
        inspector = inspect(engine)
        normalize = lambda value: " ".join(str(value).split())
        return {
            "columns": [
                (column["name"], str(column["type"]), column["nullable"], column.get("default"))
                for column in inspector.get_columns(table)
            ],
            "indexes": sorted(
                (index["name"], tuple(index["column_names"]), index["unique"])
                for index in inspector.get_indexes(table)
            ),
            "unique": sorted(
                (constraint.get("name"), tuple(constraint["column_names"]))
                for constraint in inspector.get_unique_constraints(table)
            ),
            "checks": sorted(
                (constraint.get("name"), normalize(constraint["sqltext"]))
                for constraint in inspector.get_check_constraints(table)
            ),
            "foreign_keys": sorted(
                (
                    tuple(constraint["constrained_columns"]),
                    constraint["referred_table"],
                    tuple(constraint["referred_columns"]),
                    constraint.get("options", {}).get("ondelete"),
                )
                for constraint in inspector.get_foreign_keys(table)
            ),
        }


if __name__ == "__main__":
    unittest.main()
