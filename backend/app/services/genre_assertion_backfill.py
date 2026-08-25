from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import Connection, inspect, text
from sqlmodel import Session, select

from app.canonical_models import CanonicalBackfillRun, LegacyMovieAlias
from app.contracts.structured_metadata import StructuredMetadataObservation
from app.services.genre_assertion_sync import GENRE_ASSERTION_BACKFILL_RUN_KEY
from app.services.structured_metadata_backfill import legacy_movie_observation
from app.services.structured_metadata_sync import structured_metadata_synchronizer
from app.services.structured_metadata_vocab import STRUCTURED_METADATA_VOCABULARY


_COUNTED_TABLES = (
    "assertion",
    "assertion_provenance",
    "structured_metadata_review",
)


@dataclass(frozen=True)
class GenreAssertionBackfillReport:
    dry_run: bool
    counts: dict[str, int]
    warning_count: int


def backfill_factual_genre_assertions(
    connection: Connection,
    *,
    dry_run: bool = False,
) -> GenreAssertionBackfillReport:
    before = _table_counts(connection)
    savepoint = connection.begin_nested() if dry_run else None
    session = Session(bind=connection, expire_on_commit=False)
    films_scanned = 0
    resolved_observations = 0
    source_issues = 0
    try:
        aliases = session.exec(
            select(LegacyMovieAlias).order_by(LegacyMovieAlias.legacy_movie_id)
        ).all()
        movies = (
            {
                str(row["id"]): row
                for row in connection.execute(text("SELECT * FROM movie ORDER BY id")).mappings()
            }
            if "movie" in inspect(connection).get_table_names()
            else {}
        )
        for alias in aliases:
            movie = movies.get(alias.legacy_movie_id)
            if movie is None:
                continue
            legacy_observation = legacy_movie_observation(movie, alias.library_item_id)
            concept_issues = tuple(
                issue for issue in legacy_observation.issues if issue.field_kind == "concept"
            )
            observation = StructuredMetadataObservation(
                origin_kind=legacy_observation.origin_kind,
                origin_ref=legacy_observation.origin_ref,
                source_instance_id=legacy_observation.source_instance_id,
                observed_at=legacy_observation.observed_at,
                complete_fields=frozenset({"genres"}),
                genres=legacy_observation.genres,
                issues=concept_issues,
            )
            structured_metadata_synchronizer.sync(
                session,
                film_id=alias.film_id,
                library_item_id=alias.library_item_id,
                observation=observation,
                materialize_genre_assertions=True,
            )
            films_scanned += 1
            resolved_observations += len(
                {
                    resolved.canonical_key
                    for item in observation.genres
                    if (
                        resolved := STRUCTURED_METADATA_VOCABULARY.resolve_genre(
                            item.tmdb_id if item.tmdb_id is not None else item.value
                        )
                    )
                    is not None
                }
            )
            source_issues += len(concept_issues)

        session.flush()
        after = _table_counts(connection)
        counts = {
            "films_scanned": films_scanned,
            "resolved_observations": resolved_observations,
            "assertions_created": max(0, after["assertion"] - before["assertion"]),
            "provenance_created": max(
                0,
                after["assertion_provenance"] - before["assertion_provenance"],
            ),
            "reviews_created": max(
                0,
                after["structured_metadata_review"]
                - before["structured_metadata_review"],
            ),
        }
        warning_count = max(counts["reviews_created"], source_issues)
        report = GenreAssertionBackfillReport(
            dry_run=dry_run,
            counts=counts,
            warning_count=warning_count,
        )
        if not dry_run and session.get(CanonicalBackfillRun, GENRE_ASSERTION_BACKFILL_RUN_KEY) is None:
            now = _now()
            session.add(
                CanonicalBackfillRun(
                    run_key=GENRE_ASSERTION_BACKFILL_RUN_KEY,
                    status="succeeded",
                    counts=counts,
                    warning_count=warning_count,
                    conflict_count=0,
                    started_at=now,
                    finished_at=now,
                )
            )
            session.flush()
        return report
    finally:
        session.close()
        if savepoint is not None and savepoint.is_active:
            savepoint.rollback()


def _table_counts(connection: Connection) -> dict[str, int]:
    return {
        name: int(connection.execute(text(f"SELECT COUNT(*) FROM {name}")).scalar_one())
        for name in _COUNTED_TABLES
    }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


__all__ = [
    "GenreAssertionBackfillReport",
    "backfill_factual_genre_assertions",
]
