from sqlalchemy import Connection, text

from app.migrations.runner import Migration


def upgrade(connection: Connection) -> None:
    # Historical hashes cannot recover the original candidates. Leave them null.
    connection.execute(text("ALTER TABLE identity_review ADD COLUMN candidate_snapshot JSON"))
    connection.execute(text("ALTER TABLE identity_review ADD COLUMN decision JSON"))


MIGRATION = Migration(
    version=7,
    name="identity_review_preview",
    checksum_material="fresh-canonical-v7:nullable-bounded-identity-review-evidence-decision-v2",
    upgrade=upgrade,
)
