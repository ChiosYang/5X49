from app.migrations.runner import Migration
from app.migrations.versions.v0001_legacy_columns import MIGRATION as V0001
from app.migrations.versions.v0002_canonical_library_schema import MIGRATION as V0002
from app.migrations.versions.v0003_legacy_movie_backfill import MIGRATION as V0003


MIGRATIONS: tuple[Migration, ...] = (V0001, V0002, V0003)

__all__ = ["MIGRATIONS"]
