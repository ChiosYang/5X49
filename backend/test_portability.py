import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from sqlmodel import Session, create_engine, select

from app.canonical_models import (
    Assertion,
    Concept,
    ExternalIdentity,
    Film,
    FilmProfileState,
    FilmTitle,
    GraphEntity,
    LibraryItem,
    MediaAsset,
    Setting,
    Viewing,
)
from app.contracts.analysis_persistence import assertion_qualifier_hash, assertion_semantic_key
from app.database import configure_sqlite_engine
from app.migrations.runner import run_migrations
from app.migrations.versions.v0001_fresh_canonical_baseline import LOCAL_PROFILE_ID
from app.portability import PortabilityError, export_package, validate_package


FILM_ID = "film_11111111111111111111111111111111"
CONCEPT_ID = "concept_22222222222222222222222222222222"


class PortabilityTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.database_path = self.root / "library.db"
        self.engine = create_engine(f"sqlite:///{self.database_path}")
        configure_sqlite_engine(self.engine)
        run_migrations(
            self.engine,
            self.database_path,
            app_version="portability-test",
            backup_required=False,
        )
        self._seed()

    def tearDown(self):
        self.engine.dispose()
        self._tmp.cleanup()

    def _seed(self):
        now = "2026-08-27T00:00:00+00:00"
        with Session(self.engine) as session:
            session.add(GraphEntity(id=FILM_ID, entity_type="film", created_at=now, updated_at=now))
            session.add(GraphEntity(id=CONCEPT_ID, entity_type="concept", created_at=now, updated_at=now))
            session.flush()
            session.add(
                Film(
                    id=FILM_ID,
                    canonical_title="Portable Film",
                    original_title="Portable Film",
                    release_year=2001,
                    created_at=now,
                    updated_at=now,
                )
            )
            session.add(
                Concept(
                    id=CONCEPT_ID,
                    kind="theme",
                    canonical_key="theme:memory",
                    canonical_name="Memory",
                    created_at=now,
                    updated_at=now,
                )
            )
            # Flush the graph/profile parents before inserting rows whose
            # foreign keys are intentionally represented without ORM
            # relationships. This mirrors the layered domain writers.
            session.flush()
            session.add(
                ExternalIdentity(
                    id="identity_portable",
                    entity_id=FILM_ID,
                    provider="tmdb.movie",
                    external_id="123",
                    identity_status="active",
                    provenance_kind="tmdb",
                    provenance_ref="tmdb.movie:123",
                    created_at=now,
                    updated_at=now,
                )
            )
            session.add(
                FilmTitle(
                    id="ftitle_portable",
                    film_id=FILM_ID,
                    locale="en",
                    title_type="canonical",
                    title="Portable Film",
                    normalized_title="portable film",
                    origin_kind="curated",
                    origin_ref="rule:portable",
                    observed_at=now,
                )
            )
            session.add(
                FilmProfileState(
                    profile_id=LOCAL_PROFILE_ID,
                    film_id=FILM_ID,
                    favorite=True,
                    rating=5,
                    notes="A portable personal note.",
                    created_at=now,
                    updated_at=now,
                )
            )
            session.add(
                Viewing(
                    id="viewing_portable",
                    profile_id=LOCAL_PROFILE_ID,
                    film_id=FILM_ID,
                    watched_at=now,
                    watched_at_precision="timestamp",
                    source="manual",
                    source_record_id="manual:portable",
                    review_status="confirmed",
                    created_at=now,
                    updated_at=now,
                )
            )
            session.flush()
            qualifier_hash = assertion_qualifier_hash({})
            session.add(
                Assertion(
                    id="ast_portable",
                    subject_entity_id=FILM_ID,
                    predicate="HAS_THEME",
                    object_entity_id=CONCEPT_ID,
                    qualifiers={},
                    qualifier_hash=qualifier_hash,
                    assertion_key=assertion_semantic_key(
                        subject_entity_id=FILM_ID,
                        predicate="HAS_THEME",
                        object_entity_id=CONCEPT_ID,
                        qualifier_hash=qualifier_hash,
                    ),
                    source_scope="inferred",
                    review_status="accepted",
                    review_method="user",
                    rationale="User accepted this relationship.",
                    reviewed_by_profile_id=LOCAL_PROFILE_ID,
                    reviewed_at=now,
                    first_seen_at=now,
                    last_seen_at=now,
                    created_at=now,
                    updated_at=now,
                )
            )
            session.add(
                LibraryItem(
                    id="lib_private",
                    profile_id=LOCAL_PROFILE_ID,
                    film_id=FILM_ID,
                    source_type="local",
                    source_instance_id="local",
                    source_item_key="C:/private/media/Portable Film/movie.mkv",
                    availability_status="available",
                    created_at=now,
                    updated_at=now,
                )
            )
            session.add(
                MediaAsset(
                    id="media_private",
                    library_item_id="lib_private",
                    asset_kind="video",
                    locator_kind="local_path",
                    locator="C:/private/media/Portable Film/movie.mkv",
                    normalized_locator_hash="a" * 64,
                    availability_status="present",
                    source="scanner",
                    created_at=now,
                    updated_at=now,
                )
            )
            session.add(Setting(key="provider_secret", value={"api_key": "secret-canary"}))
            session.commit()

    def test_repeated_exports_have_stable_digest_and_do_not_modify_database(self):
        before = hashlib.sha256(self.database_path.read_bytes()).hexdigest()
        first = export_package(
            self.root / "first.zip",
            database_engine=self.engine,
            exported_at="2026-08-27T01:00:00+00:00",
        )
        second = export_package(
            self.root / "second.zip",
            database_engine=self.engine,
            exported_at="2026-08-27T02:00:00+00:00",
        )
        self.engine.dispose()
        after = hashlib.sha256(self.database_path.read_bytes()).hexdigest()

        self.assertEqual(first["content_digest"], second["content_digest"])
        self.assertEqual(before, after)
        validated = validate_package(self.root / "first.zip")
        self.assertEqual(validated["status"], "passed")
        self.assertEqual(validated["schema_version"], 4)

    def test_package_excludes_media_settings_operational_state_and_source_refs(self):
        export_package(self.root / "portable.zip", database_engine=self.engine)
        with zipfile.ZipFile(self.root / "portable.zip") as package:
            payload = json.loads(package.read("library.json"))
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        self.assertNotIn("C:/private", serialized)
        self.assertNotIn("secret-canary", serialized)
        for forbidden in ("locator", "source_item_key", "origin_ref", "workflow", "job", "event"):
            self.assertNotIn(f'"{forbidden}"', serialized)
        self.assertEqual(payload["profile_states"][0]["notes"], "A portable personal note.")
        self.assertEqual(payload["assertion_decisions"][0]["review_status"], "accepted")
        self.assertEqual(payload["decision_entities"]["concepts"][0]["id"], CONCEPT_ID)

    def test_corrupt_digest_and_unsafe_zip_member_are_rejected(self):
        package_path = self.root / "valid.zip"
        export_package(package_path, database_engine=self.engine)
        corrupt_path = self.root / "corrupt.zip"
        with zipfile.ZipFile(package_path) as source, zipfile.ZipFile(corrupt_path, "w") as target:
            target.writestr("manifest.json", source.read("manifest.json"))
            target.writestr("library.json", source.read("library.json") + b" ")
        with self.assertRaisesRegex(PortabilityError, "digest"):
            validate_package(corrupt_path)

        unsafe_path = self.root / "unsafe.zip"
        with zipfile.ZipFile(unsafe_path, "w") as package:
            package.writestr("../manifest.json", b"{}")
            package.writestr("library.json", b"{}")
        with self.assertRaises(PortabilityError):
            validate_package(unsafe_path)

    def test_export_refuses_overwrite_and_non_zip_output(self):
        output = self.root / "existing.zip"
        output.write_bytes(b"existing")
        with self.assertRaisesRegex(PortabilityError, "already exists"):
            export_package(output, database_engine=self.engine)
        with self.assertRaisesRegex(PortabilityError, r"\.zip"):
            export_package(self.root / "portable.json", database_engine=self.engine)


if __name__ == "__main__":
    unittest.main()
