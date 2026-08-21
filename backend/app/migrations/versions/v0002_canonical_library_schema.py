from __future__ import annotations

from uuid import uuid4

from sqlalchemy import Connection, text

from app.migrations.runner import Migration


SCHEMA_STATEMENTS = (
    """CREATE TABLE IF NOT EXISTS graph_entity (
        id VARCHAR PRIMARY KEY NOT NULL,
        entity_type VARCHAR NOT NULL CHECK (entity_type IN ('film', 'person', 'concept')),
        lifecycle_status VARCHAR NOT NULL DEFAULT 'active'
            CHECK (lifecycle_status IN ('active', 'merged', 'tombstoned')),
        merged_into_id VARCHAR REFERENCES graph_entity(id) ON DELETE RESTRICT,
        created_at VARCHAR NOT NULL,
        updated_at VARCHAR NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS ix_graph_entity_entity_type ON graph_entity(entity_type)",
    "CREATE INDEX IF NOT EXISTS ix_graph_entity_lifecycle_status ON graph_entity(lifecycle_status)",
    """CREATE TABLE IF NOT EXISTS local_profile (
        id VARCHAR PRIMARY KEY NOT NULL,
        profile_key VARCHAR NOT NULL UNIQUE,
        display_name VARCHAR,
        created_at VARCHAR NOT NULL,
        updated_at VARCHAR NOT NULL
    )""",
    "CREATE UNIQUE INDEX IF NOT EXISTS ix_local_profile_profile_key ON local_profile(profile_key)",
    """CREATE TABLE IF NOT EXISTS film (
        id VARCHAR PRIMARY KEY NOT NULL REFERENCES graph_entity(id) ON DELETE RESTRICT,
        canonical_title VARCHAR NOT NULL,
        original_title VARCHAR,
        release_date VARCHAR,
        release_year INTEGER,
        runtime_minutes INTEGER,
        overview VARCHAR,
        lifecycle_status VARCHAR NOT NULL DEFAULT 'active'
            CHECK (lifecycle_status IN ('active', 'merged', 'tombstoned')),
        merged_into_id VARCHAR REFERENCES film(id) ON DELETE RESTRICT,
        created_at VARCHAR NOT NULL,
        updated_at VARCHAR NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS ix_film_canonical_title ON film(canonical_title)",
    "CREATE INDEX IF NOT EXISTS ix_film_release_year ON film(release_year)",
    "CREATE INDEX IF NOT EXISTS ix_film_release_title ON film(release_year, canonical_title)",
    "CREATE INDEX IF NOT EXISTS ix_film_merged_into_id ON film(merged_into_id)",
    """CREATE TABLE IF NOT EXISTS external_identity (
        id VARCHAR PRIMARY KEY NOT NULL,
        entity_id VARCHAR NOT NULL REFERENCES graph_entity(id) ON DELETE RESTRICT,
        provider VARCHAR NOT NULL,
        external_id VARCHAR NOT NULL,
        identity_status VARCHAR NOT NULL DEFAULT 'active'
            CHECK (identity_status IN ('active', 'deprecated', 'disputed')),
        verified_at VARCHAR,
        provenance_kind VARCHAR NOT NULL,
        provenance_ref VARCHAR,
        created_at VARCHAR NOT NULL,
        updated_at VARCHAR NOT NULL,
        CONSTRAINT uq_external_identity_provider_id UNIQUE(provider, external_id)
    )""",
    "CREATE INDEX IF NOT EXISTS ix_external_identity_entity_provider ON external_identity(entity_id, provider)",
    "CREATE INDEX IF NOT EXISTS ix_external_identity_provider_status ON external_identity(provider, identity_status)",
    """CREATE TABLE IF NOT EXISTS library_item (
        id VARCHAR PRIMARY KEY NOT NULL,
        profile_id VARCHAR NOT NULL REFERENCES local_profile(id) ON DELETE RESTRICT,
        film_id VARCHAR NOT NULL REFERENCES film(id) ON DELETE RESTRICT,
        source_type VARCHAR NOT NULL,
        source_instance_id VARCHAR NOT NULL,
        source_item_key VARCHAR NOT NULL,
        display_name VARCHAR,
        availability_status VARCHAR NOT NULL DEFAULT 'available'
            CHECK (availability_status IN ('available', 'missing', 'ignored', 'retired')),
        resolution_status VARCHAR NOT NULL DEFAULT 'unresolved'
            CHECK (resolution_status IN ('unresolved', 'matched', 'review_required', 'failed')),
        added_at VARCHAR,
        last_seen_at VARCHAR,
        missing_since VARCHAR,
        retired_at VARCHAR,
        metadata_source VARCHAR,
        metadata_updated_at VARCHAR,
        scrape_status VARCHAR NOT NULL DEFAULT 'pending',
        scrape_error VARCHAR,
        scraped_at VARCHAR,
        match_confidence FLOAT,
        created_at VARCHAR NOT NULL,
        updated_at VARCHAR NOT NULL
    )""",
    """CREATE UNIQUE INDEX IF NOT EXISTS uq_library_item_active_source
        ON library_item(source_instance_id, source_item_key)
        WHERE availability_status <> 'retired'""",
    "CREATE INDEX IF NOT EXISTS ix_library_item_film_id ON library_item(film_id)",
    "CREATE INDEX IF NOT EXISTS ix_library_item_profile_availability_added ON library_item(profile_id, availability_status, added_at)",
    "CREATE INDEX IF NOT EXISTS ix_library_item_source_resolution ON library_item(source_instance_id, resolution_status)",
    """CREATE TABLE IF NOT EXISTS library_item_locator_history (
        id VARCHAR PRIMARY KEY NOT NULL,
        library_item_id VARCHAR NOT NULL REFERENCES library_item(id) ON DELETE RESTRICT,
        source_instance_id VARCHAR NOT NULL,
        source_item_key VARCHAR NOT NULL,
        observed_from VARCHAR NOT NULL,
        observed_to VARCHAR,
        reason VARCHAR NOT NULL,
        CONSTRAINT uq_library_item_locator_history
            UNIQUE(library_item_id, source_instance_id, source_item_key)
    )""",
    "CREATE INDEX IF NOT EXISTS ix_library_item_locator_history_item ON library_item_locator_history(library_item_id)",
    """CREATE TABLE IF NOT EXISTS media_asset (
        id VARCHAR PRIMARY KEY NOT NULL,
        library_item_id VARCHAR REFERENCES library_item(id) ON DELETE RESTRICT,
        film_id VARCHAR REFERENCES film(id) ON DELETE RESTRICT,
        asset_kind VARCHAR NOT NULL,
        locator_kind VARCHAR NOT NULL,
        locator VARCHAR NOT NULL,
        normalized_locator_hash VARCHAR NOT NULL,
        availability_status VARCHAR NOT NULL DEFAULT 'unknown'
            CHECK (availability_status IN ('present', 'missing', 'unknown', 'retired')),
        file_size INTEGER,
        file_mtime FLOAT,
        content_fingerprint VARCHAR,
        width INTEGER,
        height INTEGER,
        codec VARCHAR,
        bitrate INTEGER,
        duration_seconds FLOAT,
        fps FLOAT,
        dynamic_range VARCHAR,
        bit_depth INTEGER,
        stream_metadata JSON,
        source VARCHAR NOT NULL,
        last_observed_at VARCHAR,
        missing_since VARCHAR,
        created_at VARCHAR NOT NULL,
        updated_at VARCHAR NOT NULL,
        CONSTRAINT ck_media_asset_owner_xor
            CHECK ((library_item_id IS NULL) <> (film_id IS NULL))
    )""",
    """CREATE UNIQUE INDEX IF NOT EXISTS uq_media_asset_library_owner_locator
        ON media_asset(library_item_id, asset_kind, normalized_locator_hash)
        WHERE library_item_id IS NOT NULL""",
    """CREATE UNIQUE INDEX IF NOT EXISTS uq_media_asset_film_owner_locator
        ON media_asset(film_id, asset_kind, normalized_locator_hash)
        WHERE film_id IS NOT NULL""",
    "CREATE INDEX IF NOT EXISTS ix_media_asset_library_kind_availability ON media_asset(library_item_id, asset_kind, availability_status)",
    "CREATE INDEX IF NOT EXISTS ix_media_asset_content_fingerprint ON media_asset(content_fingerprint)",
    """CREATE TABLE IF NOT EXISTS legacy_movie_alias (
        legacy_movie_id VARCHAR PRIMARY KEY NOT NULL,
        film_id VARCHAR NOT NULL REFERENCES film(id) ON DELETE RESTRICT,
        library_item_id VARCHAR NOT NULL UNIQUE REFERENCES library_item(id) ON DELETE RESTRICT,
        legacy_library_status VARCHAR,
        created_at VARCHAR NOT NULL,
        updated_at VARCHAR NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS ix_legacy_movie_alias_film_id ON legacy_movie_alias(film_id)",
    """CREATE TABLE IF NOT EXISTS identity_review (
        id VARCHAR PRIMARY KEY NOT NULL,
        legacy_movie_id VARCHAR NOT NULL,
        tmdb_film_id VARCHAR REFERENCES film(id) ON DELETE RESTRICT,
        imdb_film_id VARCHAR REFERENCES film(id) ON DELETE RESTRICT,
        reason VARCHAR NOT NULL,
        status VARCHAR NOT NULL DEFAULT 'open'
            CHECK (status IN ('open', 'resolved', 'dismissed')),
        created_at VARCHAR NOT NULL,
        updated_at VARCHAR NOT NULL,
        CONSTRAINT uq_identity_review_legacy_reason UNIQUE(legacy_movie_id, reason)
    )""",
    "CREATE INDEX IF NOT EXISTS ix_identity_review_legacy_movie_id ON identity_review(legacy_movie_id)",
    "CREATE INDEX IF NOT EXISTS ix_identity_review_status ON identity_review(status)",
    """CREATE TABLE IF NOT EXISTS canonical_backfill_run (
        run_key VARCHAR PRIMARY KEY NOT NULL,
        status VARCHAR NOT NULL,
        counts JSON NOT NULL,
        warning_count INTEGER NOT NULL DEFAULT 0,
        conflict_count INTEGER NOT NULL DEFAULT 0,
        started_at VARCHAR NOT NULL,
        finished_at VARCHAR
    )""",
)

CHECKSUM_MATERIAL = "\n-- statement --\n".join(SCHEMA_STATEMENTS) + "\nlocal-profile:v1"


def upgrade(connection: Connection) -> None:
    for statement in SCHEMA_STATEMENTS:
        connection.execute(text(statement))

    existing = connection.execute(
        text("SELECT id FROM local_profile WHERE profile_key = 'local'")
    ).scalar_one_or_none()
    if existing is None:
        now = _utc_now(connection)
        connection.execute(
            text(
                "INSERT INTO local_profile "
                "(id, profile_key, display_name, created_at, updated_at) "
                "VALUES (:id, 'local', 'Local', :now, :now)"
            ),
            {"id": f"profile_{uuid4().hex}", "now": now},
        )


def _utc_now(connection: Connection) -> str:
    return str(connection.execute(text("SELECT strftime('%Y-%m-%dT%H:%M:%fZ', 'now')")).scalar_one())


MIGRATION = Migration(
    version=2,
    name="canonical_library_schema",
    checksum_material=CHECKSUM_MATERIAL,
    upgrade=upgrade,
)
