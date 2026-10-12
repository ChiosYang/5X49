from sqlalchemy import Connection, text

from app.migrations.runner import Migration


def upgrade(connection: Connection) -> None:
    # Film-level reviews have no historical Viewing attribution. Add empty
    # columns only; never infer ownership or copy existing profile-state data.
    connection.execute(text(
        "ALTER TABLE viewing ADD COLUMN rating INTEGER "
        "CONSTRAINT ck_viewing_rating CHECK "
        "(rating IS NULL OR (typeof(rating) = 'integer' AND rating >= 1 AND rating <= 5))"
    ))
    connection.execute(text(
        "ALTER TABLE viewing ADD COLUMN notes VARCHAR(10000) "
        "CONSTRAINT ck_viewing_notes_length CHECK (notes IS NULL OR "
        "(typeof(notes) = 'text' AND instr(notes, char(0)) = 0 AND length(notes) <= 10000))"
    ))
    connection.execute(text("""CREATE TABLE viewing_write_receipt (
        profile_id VARCHAR NOT NULL REFERENCES local_profile(id) ON DELETE RESTRICT,
        idempotency_key VARCHAR NOT NULL,
        viewing_id VARCHAR NOT NULL REFERENCES viewing(id) ON DELETE CASCADE,
        request_hash VARCHAR NOT NULL, result_revision VARCHAR NOT NULL, created_at VARCHAR NOT NULL,
        PRIMARY KEY (profile_id, idempotency_key))"""))


MIGRATION = Migration(
    version=9,
    name="viewing_reviews",
    checksum_material="fresh-canonical-v9:nullable-viewing-reviews-and-write-receipts-no-backfill-v2",
    upgrade=upgrade,
)
