"""Regenerate the immutable Schema v2 CQRS read-model DDL snapshot."""

from __future__ import annotations

from pathlib import Path
import sys

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy.dialects import sqlite
from sqlalchemy.schema import CreateIndex, CreateTable
from sqlmodel import SQLModel

import app.models  # noqa: F401


TABLE_NAMES = (
    "projection_state",
    "library_film_read_model",
    "film_detail_read_model",
    "film_search_read_model",
    "graph_node_read_model",
    "graph_edge_read_model",
)
OUTPUT = BACKEND_ROOT / "app" / "migrations" / "schema" / "cqrs_read_models_v2.sql"


def _clean(statement: str) -> str:
    return "\n".join(line.rstrip() for line in statement.strip().splitlines())


def main() -> None:
    dialect = sqlite.dialect()
    statements: list[str] = []
    for name in TABLE_NAMES:
        table = SQLModel.metadata.tables[name]
        statements.append(_clean(str(CreateTable(table).compile(dialect=dialect))))
        for index in sorted(table.indexes, key=lambda item: item.name or ""):
            statements.append(_clean(str(CreateIndex(index).compile(dialect=dialect))))
    OUTPUT.write_text(";\n\n".join(statements) + ";\n", encoding="utf-8")


if __name__ == "__main__":
    main()
