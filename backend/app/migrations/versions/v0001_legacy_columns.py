from __future__ import annotations

from sqlalchemy import Connection, inspect, text

from app.migrations.runner import Migration


MOVIE_SCHEMA_COLUMNS = {
    "media_path": "VARCHAR",
    "folder_path": "VARCHAR",
    "file_size": "INTEGER",
    "file_mtime": "FLOAT",
    "video_width": "INTEGER",
    "video_height": "INTEGER",
    "video_codec": "VARCHAR",
    "video_bitrate": "INTEGER",
    "video_duration": "FLOAT",
    "video_fps": "FLOAT",
    "video_dynamic_range": "VARCHAR",
    "video_bit_depth": "INTEGER",
    "nfo_file": "VARCHAR",
    "nfo_path": "VARCHAR",
    "nfo_size": "INTEGER",
    "nfo_mtime": "FLOAT",
    "nfo_fingerprint": "VARCHAR",
    "added_at": "VARCHAR",
    "last_seen_at": "VARCHAR",
    "missing_since": "VARCHAR",
    "library_status": "VARCHAR DEFAULT 'available'",
    "metadata_updated_at": "VARCHAR",
    "metadata_source": "VARCHAR",
    "scrape_status": "VARCHAR DEFAULT 'pending'",
    "scrape_error": "VARCHAR",
    "scraped_at": "VARCHAR",
    "tmdb_confidence": "FLOAT",
    "countries": "JSON",
    "audio_tracks": "JSON",
    "poster_thumb_local": "VARCHAR",
    "backdrop_thumb_local": "VARCHAR",
    "external_scores": "JSON",
    "external_scores_updated_at": "VARCHAR",
    "external_scores_error": "VARCHAR",
}

JOB_SCHEMA_COLUMNS = {
    "result_summary": "VARCHAR",
    "priority": "INTEGER DEFAULT 0",
    "dedupe_key": "VARCHAR",
    "cancel_requested": "BOOLEAN DEFAULT 0",
}

CHECKSUM_MATERIAL = "|".join(
    (
        "movie:" + ",".join(f"{name}={value}" for name, value in MOVIE_SCHEMA_COLUMNS.items()),
        "job:" + ",".join(f"{name}={value}" for name, value in JOB_SCHEMA_COLUMNS.items()),
        "backfill:movie.library_status=available",
        "backfill:movie.scrape_status=pending",
        "backfill:movie.added_at=coalesce(metadata_updated_at,last_seen_at)",
        "backfill:job.priority=0",
        "backfill:job.cancel_requested=0",
    )
)


def upgrade(connection: Connection) -> None:
    movie_missing = _add_missing_columns(connection, "movie", MOVIE_SCHEMA_COLUMNS)
    job_missing = _add_missing_columns(connection, "job", JOB_SCHEMA_COLUMNS)

    if "library_status" in movie_missing:
        connection.execute(
            text("UPDATE movie SET library_status = 'available' WHERE library_status IS NULL")
        )
    if "scrape_status" in movie_missing:
        connection.execute(
            text("UPDATE movie SET scrape_status = 'pending' WHERE scrape_status IS NULL")
        )
    if "added_at" in movie_missing:
        connection.execute(
            text(
                "UPDATE movie SET added_at = COALESCE(metadata_updated_at, last_seen_at) "
                "WHERE added_at IS NULL"
            )
        )
    if "priority" in job_missing:
        connection.execute(text("UPDATE job SET priority = 0 WHERE priority IS NULL"))
    if "cancel_requested" in job_missing:
        connection.execute(
            text("UPDATE job SET cancel_requested = 0 WHERE cancel_requested IS NULL")
        )


def _add_missing_columns(
    connection: Connection,
    table_name: str,
    definitions: dict[str, str],
) -> set[str]:
    inspector = inspect(connection)
    if table_name not in inspector.get_table_names():
        return set()

    existing = {column["name"] for column in inspector.get_columns(table_name)}
    missing = {name for name in definitions if name not in existing}
    for name, column_type in definitions.items():
        if name in missing:
            connection.execute(
                text(f'ALTER TABLE "{table_name}" ADD COLUMN "{name}" {column_type}')
            )
    return missing


MIGRATION = Migration(
    version=1,
    name="legacy_movie_and_job_columns",
    checksum_material=CHECKSUM_MATERIAL,
    upgrade=upgrade,
)
