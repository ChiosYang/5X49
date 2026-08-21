from __future__ import annotations

import json
from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy import Connection, inspect, text


BACKFILL_RUN_KEY = "legacy_movie_user_state_to_viewing.v1"
SOURCE = "legacy_movie_user_state"


@dataclass(frozen=True)
class ViewingBackfillReport:
    counts: dict[str, int]
    issue_count: int


def backfill_legacy_user_states(connection: Connection) -> ViewingBackfillReport:
    counts = {
        "states_scanned": 0,
        "states_skipped": 0,
        "empty_states_skipped": 0,
        "orphaned_states": 0,
        "film_profile_states_upserted": 0,
        "viewings_created": 0,
        "confirmed_viewings_created": 0,
        "needs_review_viewings_created": 0,
    }
    issue_count = 0
    if "movie_user_state" not in inspect(connection).get_table_names():
        report = ViewingBackfillReport(counts=counts, issue_count=0)
        _store_report(connection, report)
        return report

    profile_id = connection.execute(
        text("SELECT id FROM local_profile WHERE profile_key = 'local'")
    ).scalar_one()
    now = str(connection.execute(text("SELECT strftime('%Y-%m-%dT%H:%M:%fZ', 'now')")).scalar_one())
    states = connection.execute(
        text(
            "SELECT s.*, a.film_id FROM movie_user_state s "
            "LEFT JOIN legacy_movie_alias a ON a.legacy_movie_id = s.movie_id "
            "ORDER BY s.movie_id"
        )
    ).mappings().all()
    existing_sources = {
        str(value)
        for value in connection.execute(
            text(
                "SELECT source_record_id FROM viewing "
                "WHERE profile_id = :profile AND source = :source "
                "AND source_record_id IS NOT NULL"
            ),
            {"profile": profile_id, "source": SOURCE},
        ).scalars()
    }

    for state in states:
        counts["states_scanned"] += 1
        movie_id = str(state["movie_id"])
        film_id = state.get("film_id")
        if not film_id:
            counts["orphaned_states"] += 1
            issue_count += 1
            continue

        favorite = bool(state.get("favorite"))
        watched = bool(state.get("watched"))
        watched_at = _clean_text(state.get("watched_at"))
        review = _clean_text(state.get("notes"))
        rating = state.get("rating")
        if rating is not None and not 1 <= int(rating) <= 5:
            rating = None
            issue_count += 1
        meaningful = favorite or watched or watched_at is not None or rating is not None or review is not None
        if not meaningful:
            counts["empty_states_skipped"] += 1
            continue

        updated_at = _clean_text(state.get("updated_at")) or now
        _upsert_film_profile_state(
            connection,
            profile_id=str(profile_id),
            film_id=str(film_id),
            favorite=favorite,
            timestamp=updated_at,
        )
        counts["film_profile_states_upserted"] += 1

        should_create_viewing = watched or watched_at is not None or rating is not None or review is not None
        if not should_create_viewing:
            continue
        if movie_id in existing_sources:
            counts["states_skipped"] += 1
            continue

        review_status = "confirmed" if watched or watched_at is not None else "needs_review"
        connection.execute(
            text(
                "INSERT INTO viewing "
                "(id, profile_id, film_id, watched_at, watched_at_precision, rating, review, "
                "source, source_record_id, review_status, created_at, updated_at) VALUES "
                "(:id, :profile, :film, :watched_at, :precision, :rating, :review, "
                ":source, :source_record_id, :review_status, :created_at, :updated_at)"
            ),
            {
                "id": f"view_{uuid4().hex}",
                "profile": profile_id,
                "film": film_id,
                "watched_at": watched_at,
                "precision": _watched_at_precision(watched_at),
                "rating": int(rating) if rating is not None else None,
                "review": review,
                "source": SOURCE,
                "source_record_id": movie_id,
                "review_status": review_status,
                "created_at": updated_at,
                "updated_at": updated_at,
            },
        )
        existing_sources.add(movie_id)
        counts["viewings_created"] += 1
        counts[f"{review_status}_viewings_created"] += 1

    report = ViewingBackfillReport(counts=counts, issue_count=issue_count)
    _store_report(connection, report)
    return report


def _upsert_film_profile_state(
    connection: Connection,
    *,
    profile_id: str,
    film_id: str,
    favorite: bool,
    timestamp: str,
) -> None:
    connection.execute(
        text(
            "INSERT INTO film_profile_state "
            "(profile_id, film_id, favorite, created_at, updated_at) "
            "VALUES (:profile, :film, :favorite, :timestamp, :timestamp) "
            "ON CONFLICT(profile_id, film_id) DO UPDATE SET "
            "favorite = CASE WHEN film_profile_state.favorite OR excluded.favorite THEN 1 ELSE 0 END, "
            "updated_at = CASE WHEN excluded.updated_at > film_profile_state.updated_at "
            "THEN excluded.updated_at ELSE film_profile_state.updated_at END"
        ),
        {
            "profile": profile_id,
            "film": film_id,
            "favorite": favorite,
            "timestamp": timestamp,
        },
    )


def _watched_at_precision(value: str | None) -> str:
    if value is None:
        return "unknown"
    if len(value) == 4 and value.isdigit():
        return "year"
    if len(value) == 10 and value[4:5] == "-" and value[7:8] == "-":
        return "date"
    return "timestamp"


def _store_report(connection: Connection, report: ViewingBackfillReport) -> None:
    now = str(connection.execute(text("SELECT strftime('%Y-%m-%dT%H:%M:%fZ', 'now')")).scalar_one())
    connection.execute(
        text(
            "INSERT INTO canonical_backfill_run "
            "(run_key, status, counts, warning_count, conflict_count, started_at, finished_at) "
            "VALUES (:run_key, 'succeeded', :counts, :issues, 0, :now, :now) "
            "ON CONFLICT(run_key) DO NOTHING"
        ),
        {
            "run_key": BACKFILL_RUN_KEY,
            "counts": json.dumps(report.counts, sort_keys=True),
            "issues": report.issue_count,
            "now": now,
        },
    )


def _clean_text(value) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None
