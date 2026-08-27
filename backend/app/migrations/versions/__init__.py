from app.migrations.runner import Migration
from app.migrations.versions.v0001_fresh_canonical_baseline import MIGRATION as V0001
from app.migrations.versions.v0002_cqrs_read_models import MIGRATION as V0002
from app.migrations.versions.v0003_durable_workflows import MIGRATION as V0003


MIGRATIONS: tuple[Migration, ...] = (V0001, V0002, V0003)

__all__ = ["MIGRATIONS"]
