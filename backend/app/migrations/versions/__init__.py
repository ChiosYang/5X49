from app.migrations.runner import Migration
from app.migrations.versions.v0001_fresh_canonical_baseline import MIGRATION as V0001


MIGRATIONS: tuple[Migration, ...] = (V0001,)

__all__ = ["MIGRATIONS"]
