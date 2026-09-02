from __future__ import annotations

import hashlib
from pathlib import Path

from sqlalchemy import Connection, text

from app.migrations.runner import Migration


SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schema" / "factual_explore_v4.sql"
SCHEMA_SQL = SCHEMA_PATH.read_text(encoding="utf-8")
SCHEMA_SHA256 = hashlib.sha256(SCHEMA_SQL.encode("utf-8")).hexdigest()


def upgrade(connection: Connection) -> None:
    for statement in SCHEMA_SQL.split(";\n\n"):
        ddl = statement.strip().removesuffix(";")
        if ddl:
            connection.execute(text(ddl))


MIGRATION = Migration(
    version=4,
    name="factual_explore_read_models",
    checksum_material=f"fresh-canonical-v4:explore-ddl:{SCHEMA_SHA256}",
    upgrade=upgrade,
)


__all__ = ["MIGRATION", "SCHEMA_SHA256"]
