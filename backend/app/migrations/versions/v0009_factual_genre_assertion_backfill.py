from sqlalchemy import Connection

from app.contracts.analysis_persistence import STRUCTURED_GENRE_IMPORT_POLICY_VERSION
from app.migrations.runner import Migration
from app.services.genre_assertion_backfill import backfill_factual_genre_assertions
from app.services.structured_metadata_vocab import VOCABULARY_SHA256, VOCABULARY_VERSION


CHECKSUM_MATERIAL = (
    "factual_genre_assertions:v1:legacy_alias_order:empty_qualifiers:"
    "source_scoped_provenance:preserve_user_review:"
    + STRUCTURED_GENRE_IMPORT_POLICY_VERSION
    + ":"
    + VOCABULARY_VERSION
    + ":"
    + VOCABULARY_SHA256
)


def upgrade(connection: Connection) -> None:
    backfill_factual_genre_assertions(connection, dry_run=False)


MIGRATION = Migration(
    version=9,
    name="factual_genre_assertion_backfill",
    checksum_material=CHECKSUM_MATERIAL,
    upgrade=upgrade,
)
