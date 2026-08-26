"""Regenerate the immutable fresh-canonical-v1 SQLite DDL snapshot.

Run this script only while authoring the v1 baseline. Future model changes must
be delivered as v2+ migrations instead of regenerating this file.
"""

from __future__ import annotations

from pathlib import Path
import sys

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy.schema import CreateIndex, CreateTable
from sqlalchemy.dialects import sqlite
from sqlmodel import SQLModel

import app.models  # noqa: F401


OUTPUT = BACKEND_ROOT / "app" / "migrations" / "schema" / "fresh_canonical_v1.sql"


def _clean_statement(statement: str) -> str:
    return "\n".join(line.rstrip() for line in statement.strip().splitlines())


def main() -> None:
    dialect = sqlite.dialect()
    statements: list[str] = []
    for table in SQLModel.metadata.sorted_tables:
        statements.append(_clean_statement(str(CreateTable(table).compile(dialect=dialect))))
    for table in sorted(SQLModel.metadata.tables.values(), key=lambda item: item.name):
        for index in sorted(table.indexes, key=lambda item: item.name or ""):
            statements.append(_clean_statement(str(CreateIndex(index).compile(dialect=dialect))))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(";\n\n".join(statements) + ";\n", encoding="utf-8")


if __name__ == "__main__":
    main()
