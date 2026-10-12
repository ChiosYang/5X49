from sqlalchemy import Connection, text

from app.migrations.runner import Migration


def upgrade(connection: Connection) -> None:
    connection.execute(text('''CREATE TABLE film_metadata_override (
        film_id VARCHAR NOT NULL PRIMARY KEY REFERENCES film(id) ON DELETE CASCADE,
        "values" JSON NOT NULL, revision INTEGER NOT NULL,
        updated_at VARCHAR NOT NULL)'''))
    connection.execute(text('''CREATE TABLE film_metadata_edit (
        id VARCHAR NOT NULL PRIMARY KEY,
        film_id VARCHAR NOT NULL REFERENCES film(id) ON DELETE CASCADE,
        idempotency_key VARCHAR NOT NULL, request_hash VARCHAR NOT NULL,
        before_values JSON NOT NULL, after_values JSON NOT NULL,
        automatic_snapshot JSON NOT NULL, created_at VARCHAR NOT NULL,
        CONSTRAINT uq_film_metadata_retry UNIQUE (film_id, idempotency_key))'''))
    connection.execute(text('CREATE INDEX ix_film_metadata_edit_film_id ON film_metadata_edit (film_id)'))


MIGRATION = Migration(version=8, name="manual_metadata",
    checksum_material="fresh-canonical-v8:film-metadata-overlay-and-edit-receipts-v1", upgrade=upgrade)
