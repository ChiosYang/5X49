"""Regenerate the immutable Schema v3 durable-workflow DDL snapshot."""

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


OUTPUT = BACKEND_ROOT / "app" / "migrations" / "schema" / "durable_workflows_v3.sql"


def _clean(statement: str) -> str:
    return "\n".join(line.rstrip() for line in statement.strip().splitlines())


def main() -> None:
    dialect = sqlite.dialect()
    statements: list[str] = []
    for name in ("workflow_run", "workflow_step"):
        table = SQLModel.metadata.tables[name]
        statements.append(_clean(str(CreateTable(table).compile(dialect=dialect))))
        for index in sorted(table.indexes, key=lambda item: item.name or ""):
            statements.append(_clean(str(CreateIndex(index).compile(dialect=dialect))))
    statements.extend(
        [
            "ALTER TABLE job ADD COLUMN workflow_run_id VARCHAR REFERENCES workflow_run(id) ON DELETE RESTRICT",
            "ALTER TABLE job ADD COLUMN workflow_step_id VARCHAR REFERENCES workflow_step(id) ON DELETE RESTRICT",
            "CREATE INDEX ix_job_workflow_run_id ON job (workflow_run_id)",
            "CREATE INDEX ix_job_workflow_step_id ON job (workflow_step_id)",
        ]
    )
    OUTPUT.write_text(";\n\n".join(statements) + ";\n", encoding="utf-8")


if __name__ == "__main__":
    main()
