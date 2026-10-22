from app.migrations.runner import Migration
from app.migrations.versions.v0001_fresh_canonical_baseline import MIGRATION as V0001
from app.migrations.versions.v0002_cqrs_read_models import MIGRATION as V0002
from app.migrations.versions.v0003_durable_workflows import MIGRATION as V0003
from app.migrations.versions.v0004_factual_explore_read_models import MIGRATION as V0004
from app.migrations.versions.v0005_cinema_dna import MIGRATION as V0005
from app.migrations.versions.v0006_primary_edition import MIGRATION as V0006
from app.migrations.versions.v0007_identity_review_preview import MIGRATION as V0007
from app.migrations.versions.v0008_manual_metadata import MIGRATION as V0008
from app.migrations.versions.v0009_viewing_reviews import MIGRATION as V0009

from app.migrations.versions.v0010_video_health import MIGRATION as V0010
from app.migrations.versions.v0011_search_names import MIGRATION as V0011

MIGRATIONS: tuple[Migration, ...] = (V0001, V0002, V0003, V0004, V0005, V0006, V0007, V0008, V0009, V0010, V0011)

__all__ = ["MIGRATIONS"]
