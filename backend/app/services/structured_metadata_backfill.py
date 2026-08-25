from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Connection, inspect, text
from sqlmodel import Session, select

from app.canonical_models import CanonicalBackfillRun, LegacyMovieAlias
from app.contracts.structured_metadata import (
    CountryObservation,
    CreditObservation,
    GenreObservation,
    ObservationIssue,
    StructuredMetadataObservation,
    TitleObservation,
    normalize_metadata_text,
)
from app.services.structured_metadata_sync import structured_metadata_synchronizer


BACKFILL_RUN_KEY = "legacy_structured_metadata.v1"
SOURCE_INSTANCE_ID = "legacy.local"
_DIRECTOR_SEPARATOR = re.compile(r"\s+(?:/|;|\|)\s+")
_COUNTED_TABLES = (
    "person",
    "credit",
    "credit_provenance",
    "concept",
    "concept_alias",
    "film_title",
    "film_country",
    "film_country_provenance",
    "structured_metadata_review",
)


@dataclass(frozen=True)
class StructuredMetadataBackfillReport:
    dry_run: bool
    counts: dict[str, int]
    issue_count: int


def backfill_legacy_structured_metadata(
    connection: Connection,
    *,
    dry_run: bool = False,
) -> StructuredMetadataBackfillReport:
    before = _table_counts(connection)
    savepoint = connection.begin_nested() if dry_run else None
    session = Session(bind=connection, expire_on_commit=False)
    movies_scanned = 0
    source_issues = 0
    try:
        structured_metadata_synchronizer.ensure_genre_vocabulary(session)
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
            observation = legacy_movie_observation(movie, alias.library_item_id)
            source_issues += len(observation.issues)
            structured_metadata_synchronizer.sync(
                session,
                film_id=alias.film_id,
                library_item_id=alias.library_item_id,
                observation=observation,
                materialize_genre_assertions=False,
            )
            movies_scanned += 1
        session.flush()
        after = _table_counts(connection)
        counts = {
            "movies_scanned": movies_scanned,
            **{
                f"{name}_created": max(0, after[name] - before[name])
                for name in _COUNTED_TABLES
            },
        }
        issue_count = max(0, after["structured_metadata_review"] - before["structured_metadata_review"])
        report = StructuredMetadataBackfillReport(
            dry_run=dry_run,
            counts=counts,
            issue_count=max(issue_count, source_issues),
        )
        if not dry_run:
            existing = session.get(CanonicalBackfillRun, BACKFILL_RUN_KEY)
            if existing is None:
                now = _now()
                session.add(
                    CanonicalBackfillRun(
                        run_key=BACKFILL_RUN_KEY,
                        status="succeeded",
                        counts=counts,
                        warning_count=report.issue_count,
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


def legacy_movie_observation(movie: Any, library_item_id: str) -> StructuredMetadataObservation:
    issues: list[ObservationIssue] = []
    title = str(movie["title"]).strip()
    localized_value = movie.get("title_cn")
    localized = str(localized_value).strip() if localized_value else None
    titles = [TitleObservation(title=title, title_type="original", locale="und")]
    if localized and normalize_metadata_text(localized) != normalize_metadata_text(title):
        titles.append(TitleObservation(title=localized, title_type="localized", locale="zh-CN"))
    titles.append(
        TitleObservation(
            title=localized or title,
            title_type="canonical",
            locale="zh-CN" if localized else "und",
        )
    )

    countries: list[CountryObservation] = []
    movie_countries = _json_value(movie.get("countries"))
    if movie_countries is not None:
        if isinstance(movie_countries, list):
            for index, value in enumerate(movie_countries):
                if isinstance(value, str) and value.strip():
                    countries.append(CountryObservation(value.strip()))
                else:
                    issues.append(
                        ObservationIssue(
                            "country",
                            "country_invalid",
                            {"index": index, "value_type": type(value).__name__},
                        )
                    )
        else:
            issues.append(
                ObservationIssue(
                    "country",
                    "country_invalid",
                    {"value_type": type(movie_countries).__name__},
                )
            )

    credits: list[CreditObservation] = []
    for order, director in enumerate(split_legacy_directors(movie.get("director"))):
        credits.append(
            CreditObservation(
                name=director,
                department="Directing",
                job="Director",
                billing_order=order,
            )
        )
    movie_actors = _json_value(movie.get("actors"))
    if movie_actors is not None:
        if isinstance(movie_actors, list):
            for index, actor in enumerate(movie_actors):
                if not isinstance(actor, dict):
                    issues.append(
                        ObservationIssue(
                            "credit",
                            "credit_invalid",
                            {"index": index, "value_type": type(actor).__name__},
                        )
                    )
                    continue
                name = actor.get("name")
                role = actor.get("role") or ""
                if not isinstance(name, str) or not name.strip() or not isinstance(role, str):
                    issues.append(
                        ObservationIssue(
                            "credit",
                            "credit_invalid",
                            {
                                "index": index,
                                "has_name": isinstance(name, str) and bool(name.strip()),
                                "role_type": type(role).__name__,
                            },
                        )
                    )
                    continue
                credits.append(
                    CreditObservation(
                        name=name.strip(),
                        department="Acting",
                        job="Actor",
                        character=role.strip(),
                        billing_order=index,
                    )
                )
        else:
            issues.append(
                ObservationIssue(
                    "credit",
                    "credit_invalid",
                    {"value_type": type(movie_actors).__name__},
                )
            )

    genres: list[GenreObservation] = []
    movie_genres = _json_value(movie.get("genres"))
    if movie_genres is not None:
        if isinstance(movie_genres, list):
            for index, value in enumerate(movie_genres):
                if isinstance(value, str) and value.strip():
                    genres.append(GenreObservation(value=value.strip()))
                else:
                    issues.append(
                        ObservationIssue(
                            "concept",
                            "genre_invalid",
                            {"index": index, "value_type": type(value).__name__},
                        )
                    )
        else:
            issues.append(
                ObservationIssue(
                    "concept",
                    "genre_invalid",
                    {"value_type": type(movie_genres).__name__},
                )
            )

    observed_at = next(
        (
            value
            for value in (
                movie.get("metadata_updated_at"),
                movie.get("scraped_at"),
                movie.get("last_seen_at"),
                movie.get("added_at"),
            )
            if isinstance(value, str) and value.strip()
        ),
        "1970-01-01T00:00:00+00:00",
    )
    return StructuredMetadataObservation(
        origin_kind="legacy_movie",
        origin_ref=library_item_id,
        source_instance_id=SOURCE_INSTANCE_ID,
        observed_at=observed_at,
        titles=tuple(titles),
        countries=tuple(countries),
        credits=tuple(credits),
        genres=tuple(genres),
        issues=tuple(issues),
    )


def split_legacy_directors(value: str | None) -> tuple[str, ...]:
    if not isinstance(value, str) or not value.strip():
        return ()
    return tuple(part.strip() for part in _DIRECTOR_SEPARATOR.split(value.strip()) if part.strip())


def _json_value(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if not stripped or stripped[:1] not in {"[", "{"}:
        return value
    import json

    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return value


def _table_counts(connection: Connection) -> dict[str, int]:
    return {
        name: int(connection.execute(text(f"SELECT COUNT(*) FROM {name}")).scalar_one())
        for name in _COUNTED_TABLES
    }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


__all__ = [
    "BACKFILL_RUN_KEY",
    "SOURCE_INSTANCE_ID",
    "StructuredMetadataBackfillReport",
    "backfill_legacy_structured_metadata",
    "legacy_movie_observation",
    "split_legacy_directors",
]
