from __future__ import annotations

import hashlib
from pathlib import Path

from sqlalchemy import Connection, text

from app.canonical_models import FRESH_SCHEMA_EPOCH
from app.contracts.analysis_persistence import predicate_seed_rows
from app.migrations.runner import Migration
from app.services.structured_metadata_vocab import STRUCTURED_METADATA_VOCABULARY


SEED_TIMESTAMP = "2026-08-26T00:00:00Z"
LOCAL_PROFILE_ID = "prof_321cebb247cb4fe895f11ab1965c3aeb"
GENRE_ENTITY_IDS = {
    12: "con_54eb0c4302e44644bd4b0b64dc68c93b",
    14: "con_802ccb31ebe242dd969e852de161d2a1",
    16: "con_2a1b77050b154b248c759217e916c345",
    18: "con_8a8c681effad494386d99472a6a903ac",
    27: "con_fb054726d41a41ebbc5e72e6d7698669",
    28: "con_3c852343efe4449d854756d704b2b7e5",
    35: "con_511eea9efcc840b797bda376488f3c4b",
    36: "con_c76348569df54e07a5c2ee850e143ecb",
    37: "con_f97fcd915e3e4ed6946140f113988bea",
    53: "con_38d25216594d46b8ad6e3fb66e58ac22",
    80: "con_21e50c81800d4263aed90b64764448f7",
    99: "con_ce5260c83ec84873b1d97e0a1500691d",
    878: "con_f1ce30534a9b4c6a8a9382401e6e7013",
    9648: "con_0832423529d84fa299f7999efef07475",
    10402: "con_970c0636d3794f2386a0e7000c5aa178",
    10749: "con_59171dd7145f40b0a418263d0f676b55",
    10751: "con_d96118b2efae4a9aa89d969046015dfe",
    10752: "con_1ba3a189168d4a94ba28c890a87e9727",
    10770: "con_a09d1e7921504bf59d423d79a2052d0e",
}

BASELINE_SQL_PATH = Path(__file__).resolve().parents[1] / "schema" / "fresh_canonical_v1.sql"
BASELINE_SQL = BASELINE_SQL_PATH.read_text(encoding="utf-8")
BASELINE_SQL_SHA256 = hashlib.sha256(BASELINE_SQL.encode("utf-8")).hexdigest()


def upgrade(connection: Connection) -> None:
    for statement in BASELINE_SQL.split(";\n\n"):
        ddl = statement.strip().removesuffix(";")
        if ddl:
            connection.execute(text(ddl))
    connection.execute(
        text(
            "INSERT INTO schema_metadata (id, epoch, created_at) "
            "VALUES (1, :epoch, :created_at)"
        ),
        {"epoch": FRESH_SCHEMA_EPOCH, "created_at": SEED_TIMESTAMP},
    )
    connection.execute(
        text(
            "INSERT INTO local_profile "
            "(id, profile_key, display_name, created_at, updated_at) "
            "VALUES (:id, 'local', NULL, :created_at, :updated_at)"
        ),
        {
            "id": LOCAL_PROFILE_ID,
            "created_at": SEED_TIMESTAMP,
            "updated_at": SEED_TIMESTAMP,
        },
    )
    for seed in predicate_seed_rows():
        row = {**seed, "created_at": SEED_TIMESTAMP, "updated_at": SEED_TIMESTAMP}
        connection.execute(
            text(
                "INSERT INTO assertion_predicate "
                "(key, vocabulary_version, subject_entity_type, object_entity_type, "
                "object_concept_kind, evidence_policy, created_at, updated_at) "
                "VALUES (:key, :vocabulary_version, :subject_entity_type, "
                ":object_entity_type, :object_concept_kind, :evidence_policy, "
                ":created_at, :updated_at)"
            ),
            row,
        )
    for definition in STRUCTURED_METADATA_VOCABULARY.genres:
        concept_id = GENRE_ENTITY_IDS[definition.tmdb_id]
        connection.execute(
            text(
                "INSERT INTO graph_entity "
                "(id, entity_type, lifecycle_status, merged_into_id, created_at, updated_at) "
                "VALUES (:id, 'concept', 'active', NULL, :created_at, :updated_at)"
            ),
            {"id": concept_id, "created_at": SEED_TIMESTAMP, "updated_at": SEED_TIMESTAMP},
        )
        connection.execute(
            text(
                "INSERT INTO concept "
                "(id, kind, canonical_key, canonical_name, description, lifecycle_status, "
                "merged_into_id, created_at, updated_at) "
                "VALUES (:id, 'genre', :canonical_key, :canonical_name, NULL, 'active', "
                "NULL, :created_at, :updated_at)"
            ),
            {
                "id": concept_id,
                "canonical_key": definition.canonical_key,
                "canonical_name": definition.canonical_name,
                "created_at": SEED_TIMESTAMP,
                "updated_at": SEED_TIMESTAMP,
            },
        )


MIGRATION = Migration(
    version=1,
    name="fresh_canonical_baseline",
    checksum_material=f"fresh-canonical-v1:ddl:{BASELINE_SQL_SHA256}",
    upgrade=upgrade,
)


__all__ = [
    "BASELINE_SQL_SHA256",
    "GENRE_ENTITY_IDS",
    "LOCAL_PROFILE_ID",
    "MIGRATION",
    "SEED_TIMESTAMP",
]
