from app.migrations.runner import Migration
from app.migrations.versions.v0001_legacy_columns import MIGRATION as V0001
from app.migrations.versions.v0002_canonical_library_schema import MIGRATION as V0002
from app.migrations.versions.v0003_legacy_movie_backfill import MIGRATION as V0003
from app.migrations.versions.v0004_viewing_migration import MIGRATION as V0004
from app.migrations.versions.v0005_canonical_runtime_fields import MIGRATION as V0005
from app.migrations.versions.v0006_structured_metadata_schema import MIGRATION as V0006
from app.migrations.versions.v0007_structured_metadata_backfill import MIGRATION as V0007


MIGRATIONS: tuple[Migration, ...] = (V0001, V0002, V0003, V0004, V0005, V0006, V0007)

__all__ = ["MIGRATIONS"]
