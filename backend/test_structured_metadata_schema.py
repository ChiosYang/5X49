import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlmodel import SQLModel, create_engine

import app.models  # noqa: F401
from app.contracts.structured_metadata import (
    PROVISIONAL_PERSON_PROVIDER,
    credit_semantic_key,
    normalize_metadata_text,
    provisional_person_external_id,
    structured_metadata_review_key,
    validate_provenance_ref,
    validate_review_raw_value,
)
from app.database import configure_sqlite_engine
from app.migrations.runner import run_migrations
from app.migrations.versions import MIGRATIONS


STRUCTURED_TABLES = (
    "person",
    "credit",
    "credit_provenance",
    "concept",
    "concept_alias",
    "film_title",
    "film_country",
    "film_country_provenance",
    "structured_metadata_review",
)


class StructuredMetadataContractTests(unittest.TestCase):
    def test_text_and_deterministic_keys_are_stable_without_over_normalizing(self):
        self.assertEqual(normalize_metadata_text("  HéLÈNE\tCATTANEO  "), "hélène cattaneo")
        self.assertNotEqual(normalize_metadata_text("Jose"), normalize_metadata_text("José"))

        first = provisional_person_external_id("legacy.local", "  Wong  Kar-wai ")
        repeated = provisional_person_external_id("legacy.local", "wong kar-wai")
        other_source = provisional_person_external_id("jellyfin.local", "Wong Kar-wai")

        self.assertEqual(PROVISIONAL_PERSON_PROVIDER, "legacy.local.person")
        self.assertEqual(first, repeated)
        self.assertNotEqual(first, other_source)
        self.assertRegex(first, r"^sha256:[0-9a-f]{64}$")
        self.assertNotIn("wong", first)
        self.assertNotIn("legacy", first)

        self.assertEqual(
            credit_semantic_key(
                "film_" + "a" * 32,
                "person_" + "b" * 32,
                "Directing",
                "Director",
            ),
            credit_semantic_key(
                "film_" + "a" * 32,
                "person_" + "b" * 32,
                " directing ",
                "DIRECTOR",
            ),
        )

    def test_review_key_is_canonical_and_provenance_rejects_paths(self):
        arguments = {
            "film_id": "film_" + "a" * 32,
            "field_kind": "country",
            "reason_code": "unknown_name",
            "origin_kind": "nfo",
            "origin_ref": "lib_" + "b" * 32,
        }
        first = structured_metadata_review_key(raw_value={"b": 2, "a": 1}, **arguments)
        second = structured_metadata_review_key(raw_value={"a": 1, "b": 2}, **arguments)

        self.assertEqual(first, second)
        self.assertRegex(first[0], r"^[0-9a-f]{64}$")
        self.assertRegex(first[1], r"^[0-9a-f]{64}$")
        self.assertEqual(validate_provenance_ref("tmdb.movie:42"), "tmdb.movie:42")
        for value in ("C:\\Private\\movie.nfo", "/private/movie.nfo", "file:///private/movie.nfo"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_provenance_ref(value)
        for value in (
            {"path": "relative/movie.nfo"},
            "C:\\Private\\movie.nfo",
            "sk-gateasecret123",
            "x" * 5000,
        ):
            with self.subTest(raw=value), self.assertRaises(ValueError):
                validate_review_raw_value(value)


class StructuredMetadataSchemaTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmp.name)
        self.database_path = self.tmp_path / "structured.db"
        with closing(sqlite3.connect(self.database_path)) as connection:
            connection.executescript(
                "CREATE TABLE movie (id VARCHAR PRIMARY KEY, title VARCHAR NOT NULL, "
                "year INTEGER NOT NULL);"
                "INSERT INTO movie VALUES ('legacy_structured', 'Schema Sentinel', 2001);"
            )
        self.engine = create_engine(f"sqlite:///{self.database_path}")
        configure_sqlite_engine(self.engine)
        run_migrations(
            self.engine,
            self.database_path,
            app_version="test",
            backup_dir=self.tmp_path / "backups",
        )
        self.now = "2026-08-25T00:00:00Z"

    def tearDown(self):
        self.engine.dispose()
        self._tmp.cleanup()

    def test_schema_version_tables_indexes_and_seeded_vocabulary_are_available(self):
        inspector = inspect(self.engine)
        tables = set(inspector.get_table_names())
        self.assertEqual(MIGRATIONS[-1].version, 9)
        self.assertTrue(set(STRUCTURED_TABLES).issubset(tables))
        with self.engine.connect() as connection:
            self.assertEqual(connection.execute(text("SELECT COUNT(*) FROM concept")).scalar_one(), 19)
            self.assertGreater(connection.execute(text("SELECT COUNT(*) FROM concept_alias")).scalar_one(), 19)
            self.assertEqual(connection.execute(text("SELECT COUNT(*) FROM film_title")).scalar_one(), 2)
            for table in (
                "person",
                "credit",
                "credit_provenance",
                "film_country",
                "film_country_provenance",
                "structured_metadata_review",
            ):
                self.assertEqual(connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one(), 0)
        self.assertTrue(
            {
                "ix_person_normalized_name",
                "ix_person_resolution_status",
            }.issubset({index["name"] for index in inspector.get_indexes("person")})
        )
        self.assertTrue(
            {
                "ix_structured_metadata_review_film_status",
                "ix_structured_metadata_review_field_status",
            }.issubset(
                {index["name"] for index in inspector.get_indexes("structured_metadata_review")}
            )
        )
        with self.engine.connect() as connection:
            self.assertEqual(
                connection.execute(
                    text("SELECT title FROM movie WHERE id='legacy_structured'")
                ).scalar_one(),
                "Schema Sentinel",
            )

    def test_fresh_create_all_and_migrated_structured_schema_are_equivalent(self):
        fresh_path = self.tmp_path / "fresh.db"
        fresh = create_engine(f"sqlite:///{fresh_path}")
        configure_sqlite_engine(fresh)
        try:
            SQLModel.metadata.create_all(fresh)
            run_migrations(
                fresh,
                fresh_path,
                app_version="test",
                backup_required=False,
            )
            for table in STRUCTURED_TABLES:
                self.assertEqual(self._schema_signature(fresh, table), self._schema_signature(self.engine, table))
        finally:
            fresh.dispose()

    def test_person_names_are_not_unique_but_external_identity_is(self):
        first = "person_" + "a" * 32
        second = "person_" + "b" * 32
        with self.engine.begin() as connection:
            self._insert_graph_entity(connection, first, "person")
            self._insert_graph_entity(connection, second, "person")
            for person_id in (first, second):
                connection.execute(
                    text(
                        "INSERT INTO person (id, canonical_name, normalized_name, "
                        "resolution_status, lifecycle_status, created_at, updated_at) "
                        "VALUES (:id, 'Alex Kim', 'alex kim', 'provisional', 'active', :now, :now)"
                    ),
                    {"id": person_id, "now": self.now},
                )
            connection.execute(
                text(
                    "INSERT INTO external_identity (id, entity_id, provider, external_id, "
                    "identity_status, provenance_kind, created_at, updated_at) "
                    "VALUES ('identity_person_one', :person, 'tmdb.person', '42', "
                    "'active', 'tmdb', :now, :now)"
                ),
                {"person": first, "now": self.now},
            )

        with self.assertRaises(IntegrityError), self.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO external_identity (id, entity_id, provider, external_id, "
                    "identity_status, provenance_kind, created_at, updated_at) "
                    "VALUES ('identity_person_two', :person, 'tmdb.person', '42', "
                    "'active', 'tmdb', :now, :now)"
                ),
                {"person": second, "now": self.now},
            )

        with self.assertRaises(IntegrityError), self.engine.begin() as connection:
            connection.execute(text("DELETE FROM graph_entity WHERE id=:id"), {"id": first})

    def test_credit_semantics_and_provenance_are_unique_and_restricted(self):
        film_id, person_id = self._insert_film_and_person()
        key = credit_semantic_key(film_id, person_id, "Directing", "Director")
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO credit (id, film_id, person_id, department, job, character, "
                    "billing_order, semantic_key, created_at, updated_at) VALUES "
                    "('credit_one', :film, :person, 'Directing', 'Director', '', 0, :key, :now, :now)"
                ),
                {"film": film_id, "person": person_id, "key": key, "now": self.now},
            )
            connection.execute(
                text(
                    "INSERT INTO credit_provenance "
                    "(id, credit_id, origin_kind, origin_ref, observed_at) "
                    "VALUES ('credit_provenance_one', 'credit_one', 'nfo', 'lib_source', :now)"
                ),
                {"now": self.now},
            )

        with self.assertRaises(IntegrityError), self.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO credit (id, film_id, person_id, department, job, character, "
                    "semantic_key, created_at, updated_at) VALUES "
                    "('credit_duplicate', :film, :person, 'Directing', 'Director', '', :key, :now, :now)"
                ),
                {"film": film_id, "person": person_id, "key": key, "now": self.now},
            )
        with self.assertRaises(IntegrityError), self.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO credit (id, film_id, person_id, department, job, character, "
                    "billing_order, semantic_key, created_at, updated_at) VALUES "
                    "('credit_bad_order', :film, :person, 'Acting', 'Actor', '', -1, "
                    "'different-key', :now, :now)"
                ),
                {"film": film_id, "person": person_id, "now": self.now},
            )
        with self.assertRaises(IntegrityError), self.engine.begin() as connection:
            connection.execute(text("DELETE FROM credit WHERE id='credit_one'"))

    def test_concept_alias_title_country_and_review_constraints(self):
        film_id, _ = self._insert_film_and_person()
        concept_ids = ("concept_" + "c" * 32, "concept_" + "d" * 32)
        with self.engine.begin() as connection:
            for index, concept_id in enumerate(concept_ids):
                self._insert_graph_entity(connection, concept_id, "concept")
                connection.execute(
                    text(
                        "INSERT INTO concept (id, kind, canonical_key, canonical_name, "
                        "lifecycle_status, created_at, updated_at) VALUES "
                        "(:id, 'genre', :key, :name, 'active', :now, :now)"
                    ),
                    {
                        "id": concept_id,
                        "key": f"genre-{index}",
                        "name": f"Genre {index}",
                        "now": self.now,
                    },
                )
                connection.execute(
                    text(
                        "INSERT INTO concept_alias (id, concept_id, locale, alias, "
                        "normalized_alias, provenance_ref, created_at, updated_at) VALUES "
                        "(:alias_id, :concept, 'en', 'Drama', 'drama', 'genre-v1', :now, :now)"
                    ),
                    {"alias_id": f"alias_{index}", "concept": concept_id, "now": self.now},
                )
            connection.execute(
                text(
                    "INSERT INTO film_title (id, film_id, locale, title_type, title, "
                    "normalized_title, origin_kind, origin_ref, observed_at) VALUES "
                    "('title_one', :film, 'zh-CN', 'localized', '测试电影', '测试电影', "
                    "'nfo', 'lib_source', :now)"
                ),
                {"film": film_id, "now": self.now},
            )
            connection.execute(
                text(
                    "INSERT INTO film_country (id, film_id, iso_3166_1, created_at, updated_at) "
                    "VALUES ('country_one', :film, 'CN', :now, :now)"
                ),
                {"film": film_id, "now": self.now},
            )
            connection.execute(
                text(
                    "INSERT INTO film_country_provenance "
                    "(id, film_country_id, origin_kind, origin_ref, observed_at) VALUES "
                    "('country_provenance_one', 'country_one', 'nfo', 'lib_source', :now)"
                ),
                {"now": self.now},
            )
            review_key, raw_hash = structured_metadata_review_key(
                film_id=film_id,
                field_kind="country",
                reason_code="unknown_name",
                origin_kind="nfo",
                origin_ref="lib_source",
                raw_value="Unknownland",
            )
            connection.execute(
                text(
                    "INSERT INTO structured_metadata_review "
                    "(id, film_id, field_kind, reason_code, raw_value, raw_value_hash, "
                    "origin_kind, origin_ref, review_key, status, created_at, updated_at) VALUES "
                    "('review_one', :film, 'country', 'unknown_name', :raw, :raw_hash, "
                    "'nfo', 'lib_source', :review_key, 'open', :now, :now)"
                ),
                {
                    "film": film_id,
                    "raw": '"Unknownland"',
                    "raw_hash": raw_hash,
                    "review_key": review_key,
                    "now": self.now,
                },
            )

        with self.assertRaises(IntegrityError), self.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO film_country (id, film_id, iso_3166_1, created_at, updated_at) "
                    "VALUES ('country_bad', :film, 'cn', :now, :now)"
                ),
                {"film": film_id, "now": self.now},
            )
        with self.assertRaises(IntegrityError), self.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO concept_alias (id, concept_id, locale, alias, "
                    "normalized_alias, provenance_ref, created_at, updated_at) VALUES "
                    "('alias_duplicate', :concept, 'en', 'DRAMA', 'drama', "
                    "'other-source', :now, :now)"
                ),
                {"concept": concept_ids[0], "now": self.now},
            )
        with self.assertRaises(IntegrityError), self.engine.begin() as connection:
            duplicate_concept = "concept_" + "a" * 32
            self._insert_graph_entity(connection, duplicate_concept, "concept")
            connection.execute(
                text(
                    "INSERT INTO concept (id, kind, canonical_key, canonical_name, "
                    "lifecycle_status, created_at, updated_at) VALUES "
                    "(:id, 'genre', 'genre-0', 'Duplicate Genre', 'active', :now, :now)"
                ),
                {"id": duplicate_concept, "now": self.now},
            )
        with self.assertRaises(IntegrityError), self.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO film_title (id, film_id, locale, title_type, title, "
                    "normalized_title, origin_kind, origin_ref, observed_at) "
                    "SELECT 'title_duplicate', film_id, locale, title_type, title, "
                    "normalized_title, origin_kind, origin_ref, observed_at "
                    "FROM film_title WHERE id='title_one'"
                )
            )
        with self.assertRaises(IntegrityError), self.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO structured_metadata_review "
                    "(id, film_id, field_kind, reason_code, raw_value_hash, origin_kind, "
                    "origin_ref, review_key, status, created_at, updated_at) "
                    "SELECT 'review_duplicate', film_id, field_kind, reason_code, raw_value_hash, "
                    "origin_kind, origin_ref, review_key, status, created_at, updated_at "
                    "FROM structured_metadata_review WHERE id='review_one'"
                )
            )

    def _insert_film_and_person(self) -> tuple[str, str]:
        film_id = "film_" + "f" * 32
        person_id = "person_" + "p" * 32
        with self.engine.begin() as connection:
            self._insert_graph_entity(connection, film_id, "film")
            self._insert_graph_entity(connection, person_id, "person")
            connection.execute(
                text(
                    "INSERT INTO film (id, canonical_title, lifecycle_status, created_at, updated_at) "
                    "VALUES (:id, 'Structured Film', 'active', :now, :now)"
                ),
                {"id": film_id, "now": self.now},
            )
            connection.execute(
                text(
                    "INSERT INTO person (id, canonical_name, normalized_name, resolution_status, "
                    "lifecycle_status, created_at, updated_at) VALUES "
                    "(:id, 'Director', 'director', 'provisional', 'active', :now, :now)"
                ),
                {"id": person_id, "now": self.now},
            )
        return film_id, person_id

    def _insert_graph_entity(self, connection, entity_id: str, entity_type: str) -> None:
        connection.execute(
            text(
                "INSERT INTO graph_entity "
                "(id, entity_type, lifecycle_status, created_at, updated_at) "
                "VALUES (:id, :type, 'active', :now, :now)"
            ),
            {"id": entity_id, "type": entity_type, "now": self.now},
        )

    @staticmethod
    def _schema_signature(engine, table: str) -> dict:
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
