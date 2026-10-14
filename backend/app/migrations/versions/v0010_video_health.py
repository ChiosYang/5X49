from sqlalchemy import Connection, text
from app.migrations.runner import Migration


def upgrade(connection: Connection) -> None:
    connection.execute(text("""CREATE TABLE video_health (
        id VARCHAR NOT NULL PRIMARY KEY,
        asset_id VARCHAR NOT NULL REFERENCES media_asset(id) ON DELETE CASCADE,
        version_key VARCHAR NOT NULL, version JSON NOT NULL, asset_snapshot VARCHAR NOT NULL,
        status VARCHAR NOT NULL, container_status VARCHAR NOT NULL,
        error_code VARCHAR, error_summary VARCHAR, observed_at FLOAT NOT NULL,
        checked_at FLOAT, passed_at FLOAT, next_attempt_at FLOAT NOT NULL, attempts INTEGER NOT NULL,
        priority INTEGER NOT NULL, decoded_seconds FLOAT NOT NULL, duration_seconds FLOAT,
        cancel_requested BOOLEAN NOT NULL, notified BOOLEAN NOT NULL, acknowledged BOOLEAN NOT NULL,
        CONSTRAINT uq_video_health_version UNIQUE(asset_id, version_key),
        CONSTRAINT ck_video_health_status CHECK(status IN
            ('unchecked','queued','checking','passed','abnormal','incomplete','unsupported')))
    """))
    connection.execute(text('CREATE INDEX ix_video_health_asset_id ON video_health(asset_id)'))
    connection.execute(text('CREATE INDEX ix_video_health_status ON video_health(status)'))


MIGRATION = Migration(version=10, name="video_health",
    checksum_material="fresh-canonical-v10:per-asset-stat-version-health-queue-v2-retained-pass", upgrade=upgrade)
