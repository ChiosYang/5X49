from sqlalchemy import Connection
from app.migrations.runner import Migration

def upgrade(connection:Connection):
    from app.metadata_source_models import FilmMetadataSourceSnapshot
    FilmMetadataSourceSnapshot.__table__.create(connection,checkfirst=True)

MIGRATION=Migration(version=12,name='metadata_source_snapshots',
    checksum_material='fresh-canonical-v12:source-owned-language-and-complete-cast-v1',upgrade=upgrade)
