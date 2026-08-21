from sqlalchemy import Connection

from app.migrations.runner import Migration
from app.services.canonical_backfill import backfill_legacy_movies


CHECKSUM_MATERIAL = "legacy_movie_to_canonical:v1:tmdb_then_imdb:no_title_merge:assets_and_aliases"


def upgrade(connection: Connection) -> None:
    backfill_legacy_movies(connection, dry_run=False)


MIGRATION = Migration(
    version=3,
    name="legacy_movie_canonical_backfill",
    checksum_material=CHECKSUM_MATERIAL,
    upgrade=upgrade,
)
