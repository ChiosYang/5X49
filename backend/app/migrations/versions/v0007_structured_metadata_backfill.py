from sqlalchemy import Connection

from app.migrations.runner import Migration
from app.services.structured_metadata_backfill import backfill_legacy_structured_metadata
from app.services.structured_metadata_vocab import VOCABULARY_SHA256, VOCABULARY_VERSION


CHECKSUM_MATERIAL = (
    "legacy_structured_metadata:v1:titles_countries_people_credits_reviews:"
    "no_film_concept_edges:source_scoped_people:"
    + VOCABULARY_VERSION
    + ":"
    + VOCABULARY_SHA256
)


def upgrade(connection: Connection) -> None:
    backfill_legacy_structured_metadata(connection, dry_run=False)


MIGRATION = Migration(
    version=7,
    name="legacy_structured_metadata_backfill",
    checksum_material=CHECKSUM_MATERIAL,
    upgrade=upgrade,
)
