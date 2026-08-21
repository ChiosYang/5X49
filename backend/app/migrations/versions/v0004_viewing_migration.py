from __future__ import annotations

from sqlalchemy import Connection, text

from app.migrations.runner import Migration
from app.services.viewing_backfill import backfill_legacy_user_states


SCHEMA_STATEMENTS = (
    """CREATE TABLE IF NOT EXISTS film_profile_state (
        profile_id VARCHAR NOT NULL REFERENCES local_profile(id) ON DELETE RESTRICT,
        film_id VARCHAR NOT NULL REFERENCES film(id) ON DELETE RESTRICT,
        favorite BOOLEAN NOT NULL DEFAULT 0,
        created_at VARCHAR NOT NULL,
        updated_at VARCHAR NOT NULL,
        PRIMARY KEY(profile_id, film_id)
    )""",
    "CREATE INDEX IF NOT EXISTS ix_film_profile_state_favorite ON film_profile_state(favorite)",
    """CREATE TABLE IF NOT EXISTS viewing (
        id VARCHAR PRIMARY KEY NOT NULL,
        profile_id VARCHAR NOT NULL REFERENCES local_profile(id) ON DELETE RESTRICT,
        film_id VARCHAR NOT NULL REFERENCES film(id) ON DELETE RESTRICT,
        watched_at VARCHAR,
        watched_at_precision VARCHAR NOT NULL DEFAULT 'unknown'
            CHECK (watched_at_precision IN ('timestamp', 'date', 'year', 'unknown')),
        rating INTEGER CHECK (rating IS NULL OR (rating >= 1 AND rating <= 5)),
        review VARCHAR,
        tags JSON,
        mood VARCHAR,
        favorite_scene VARCHAR,
        source VARCHAR NOT NULL,
        source_record_id VARCHAR,
        review_status VARCHAR NOT NULL DEFAULT 'confirmed'
            CHECK (review_status IN ('confirmed', 'needs_review', 'rejected')),
        created_at VARCHAR NOT NULL,
        updated_at VARCHAR NOT NULL,
        deleted_at VARCHAR,
        CONSTRAINT uq_viewing_source_record UNIQUE(profile_id, source, source_record_id)
    )""",
    "CREATE INDEX IF NOT EXISTS ix_viewing_profile_watched_at ON viewing(profile_id, watched_at)",
    "CREATE INDEX IF NOT EXISTS ix_viewing_profile_film_watched_at ON viewing(profile_id, film_id, watched_at)",
    "CREATE INDEX IF NOT EXISTS ix_viewing_film_id ON viewing(film_id)",
    "CREATE INDEX IF NOT EXISTS ix_viewing_review_status ON viewing(review_status)",
    "CREATE INDEX IF NOT EXISTS ix_viewing_deleted_at ON viewing(deleted_at)",
)

CHECKSUM_MATERIAL = "\n-- statement --\n".join(SCHEMA_STATEMENTS) + "\nlegacy-user-state:v1"


def upgrade(connection: Connection) -> None:
    for statement in SCHEMA_STATEMENTS:
        connection.execute(text(statement))
    backfill_legacy_user_states(connection)


MIGRATION = Migration(
    version=4,
    name="legacy_user_state_to_viewing",
    checksum_material=CHECKSUM_MATERIAL,
    upgrade=upgrade,
)
