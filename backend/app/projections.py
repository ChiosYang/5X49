from __future__ import annotations

import argparse
import json
from typing import Sequence

from sqlmodel import Session

from app.database import create_db_and_tables, engine
from app.services.projections import projection_coordinator


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
    create_db_and_tables()
    with Session(engine) as session:
        if args.command == "verify":
            report = projection_coordinator.verify_session(session)
        elif args.all:
            report = projection_coordinator.rebuild_all(session)
            session.commit()
        else:
            session.info["skip_projection_hook"] = True
            try:
                projection_coordinator.refresh_film(session, args.film)
                report = projection_coordinator.verify_session(session)
                session.commit()
            finally:
                session.info.pop("skip_projection_hook", None)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
