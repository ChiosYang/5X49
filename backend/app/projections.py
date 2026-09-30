from __future__ import annotations

import argparse
import json
import os
import sqlite3
from pathlib import Path
from typing import Sequence

from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, create_engine

from app.migrations.backup import BackupValidationError
from app.migrations.runner import MigrationError
from app.services.projections import ProjectionVerificationError, projection_coordinator


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify or rebuild synchronous read models")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("verify", help="Verify projection versions, hashes, and digests")
    rebuild = subparsers.add_parser("rebuild", help="Rebuild read models transactionally")
    target = rebuild.add_mutually_exclusive_group(required=True)
    target.add_argument("--all", action="store_true", help="Rebuild every read model")
    target.add_argument("--film", metavar="FILM_ID", help="Rebuild one Film")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    verification_engine = None
    try:
        if args.command == "verify":
            # Diagnostics must not migrate, bootstrap, or repair the database.
            path = Path(os.environ.get("SQLITE_DB_PATH", "data/library.db")).resolve()
            verification_engine = create_engine(
                "sqlite://",
                creator=lambda: sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True, timeout=1),
            )
            with Session(verification_engine) as session:
                report = projection_coordinator.verify_session(session)
        else:
            from app.database import create_db_and_tables, engine

            create_db_and_tables(initialize_projections=False)
            with Session(engine) as session:
                if args.all:
                    report = projection_coordinator.rebuild_all(session)
                else:
                    session.info["skip_projection_hook"] = True
                    try:
                        projection_coordinator.refresh_film(session, args.film)
                        report = projection_coordinator.verify_session(session)
                    finally:
                        session.info.pop("skip_projection_hook", None)
                session.commit()
    except (ProjectionVerificationError, SQLAlchemyError, sqlite3.Error, OSError, MigrationError, BackupValidationError):
        print(json.dumps({"status": "failed", "code": "projection_verification_failed" if args.command == "verify" else "projection_rebuild_failed"}))
        return 2
    finally:
        if verification_engine is not None:
            verification_engine.dispose()
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
