from sqlalchemy import Connection

from app.migrations.runner import Migration
from app.services.legacy_analysis_backfill import backfill_legacy_analysis


CHECKSUM_MATERIAL = (
    "legacy_analysis_v2:v1:canonical_input_hash:bounded_summary:"
    "directional_influence:local_resolution:no_network:no_raw_artifact"
)


def upgrade(connection: Connection) -> None:
    backfill_legacy_analysis(connection, dry_run=False)


MIGRATION = Migration(
    version=10,
    name="legacy_analysis_transition",
    checksum_material=CHECKSUM_MATERIAL,
    upgrade=upgrade,
)
