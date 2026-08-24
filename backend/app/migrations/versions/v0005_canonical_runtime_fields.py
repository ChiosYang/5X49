from __future__ import annotations

from sqlalchemy import Connection, inspect, text

from app.migrations.runner import Migration


MEDIA_ASSET_COLUMNS = {
    "platform_file_id": "VARCHAR",
    "content_hash": "VARCHAR",
}

INDEX_STATEMENTS = (
    "CREATE INDEX IF NOT EXISTS ix_media_asset_platform_file_id "
    "ON media_asset(platform_file_id)",
    "CREATE INDEX IF NOT EXISTS ix_media_asset_content_hash "
    "ON media_asset(content_hash)",
)

CHECKSUM_MATERIAL = "|".join(
    [
        *(f"media_asset:{name}={definition}" for name, definition in MEDIA_ASSET_COLUMNS.items()),
        *INDEX_STATEMENTS,
    ]
)


def upgrade(connection: Connection) -> None:
    inspector = inspect(connection)
    if "media_asset" not in inspector.get_table_names():
        return

    existing = {column["name"] for column in inspector.get_columns("media_asset")}
    for name, definition in MEDIA_ASSET_COLUMNS.items():
        if name not in existing:
            connection.execute(
                text(f'ALTER TABLE "media_asset" ADD COLUMN "{name}" {definition}')
            )
    for statement in INDEX_STATEMENTS:
        connection.execute(text(statement))


MIGRATION = Migration(
    version=5,
    name="canonical_runtime_media_identity",
    checksum_material=CHECKSUM_MATERIAL,
    upgrade=upgrade,
)
