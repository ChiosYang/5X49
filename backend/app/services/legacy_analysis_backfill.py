from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Connection, inspect, text
from sqlmodel import Session, select

from app.canonical_models import AnalysisRun, CanonicalBackfillRun, LegacyMovieAlias
from app.contracts.analysis_persistence import analysis_run_idempotency_key
from app.contracts.analysis_v2 import AnalysisV2Output
from app.contracts.structured_metadata import canonical_json_hash
from app.services.analysis_runtime import (
    ANALYSIS_APP_VERSION,
    ANALYSIS_KIND,
    ANALYSIS_POLICY_VERSION,
    ANALYSIS_RESOLVER_VERSION,
    AnalysisRuntimePersistence,
    ResolutionFailure,
)


LEGACY_ANALYSIS_BACKFILL_RUN_KEY = "legacy_analysis_v2.v1"
LEGACY_ANALYSIS_SCHEMA_VERSION = "legacy-genealogy.v1"
LEGACY_ANALYSIS_PROMPT_VERSION = "legacy-genealogy.v1"
_COUNTED_TABLES = (
    "analysis_run",
    "assertion",
    "assertion_provenance",
    "analysis_resolution_review",
)


@dataclass(frozen=True)
class LegacyAnalysisBackfillReport:
    dry_run: bool
    counts: dict[str, int]
    warning_count: int


@dataclass(frozen=True)
class ParsedLegacyAnalysis:
    output: AnalysisV2Output | None
    issue_count: int
    dropped_field_count: int


def backfill_legacy_analysis(
    connection: Connection,
    *,
    dry_run: bool = False,
) -> LegacyAnalysisBackfillReport:
    before = _table_counts(connection)
    savepoint = connection.begin_nested() if dry_run else None
    session = Session(bind=connection, expire_on_commit=False)
    runtime = AnalysisRuntimePersistence()
    films_scanned = 0
    succeeded = 0
    failed = 0
    issue_count = 0
    dropped_fields = 0
    try:
        movies = (
            {
                str(row["id"]): row
                for row in connection.execute(text("SELECT * FROM movie ORDER BY id")).mappings()
            }
            if "movie" in inspect(connection).get_table_names()
            else {}
        )
        aliases = session.exec(
            select(LegacyMovieAlias).order_by(LegacyMovieAlias.legacy_movie_id)
        ).all()
        selected_aliases: dict[str, LegacyMovieAlias] = {}
        for alias in aliases:
            selected_aliases.setdefault(alias.film_id, alias)

        for film_id, alias in sorted(selected_aliases.items()):
            movie = movies.get(alias.legacy_movie_id)
            if movie is None:
                continue
            raw = movie.get("analysis_data")
            if isinstance(raw, str):
                try:
                    decoded = json.loads(raw)
                except (TypeError, ValueError):
                    decoded = raw
                raw = decoded
            if raw is None and movie.get("analysis_status") != "completed":
                continue
            films_scanned += 1
            analysis_input = runtime.build_input(session, film_id)
            input_hash = canonical_json_hash(analysis_input.model_dump(mode="json"))
            idempotency_key = analysis_run_idempotency_key(
                film_id=film_id,
                analysis_kind=ANALYSIS_KIND,
                provider="legacy",
                model="unknown",
                prompt_version=LEGACY_ANALYSIS_PROMPT_VERSION,
                schema_version=LEGACY_ANALYSIS_SCHEMA_VERSION,
                resolver_version=ANALYSIS_RESOLVER_VERSION,
                policy_version=ANALYSIS_POLICY_VERSION,
                app_version=ANALYSIS_APP_VERSION,
                input_hash=input_hash,
            )
            existing = session.exec(
                select(AnalysisRun).where(AnalysisRun.idempotency_key == idempotency_key)
            ).first()
            if existing is not None:
                continue
            parsed = parse_legacy_analysis(raw, film_id)
            issue_count += parsed.issue_count
            dropped_fields += parsed.dropped_field_count
            now = _now()
            if parsed.output is None:
                run = AnalysisRun(
                    film_id=film_id,
                    analysis_kind=ANALYSIS_KIND,
                    provider="legacy",
                    model="unknown",
                    prompt_version=LEGACY_ANALYSIS_PROMPT_VERSION,
                    schema_version=LEGACY_ANALYSIS_SCHEMA_VERSION,
                    resolver_version=ANALYSIS_RESOLVER_VERSION,
                    policy_version=ANALYSIS_POLICY_VERSION,
                    app_version=ANALYSIS_APP_VERSION,
                    input_hash=input_hash,
                    idempotency_key=idempotency_key,
                    status="failed",
                    attempt_count=1,
                    started_at=now,
                    finished_at=now,
                    error_category="validation",
                    error_code="legacy_output_invalid",
                    error_message="Legacy analysis output was incompatible",
                    created_at=now,
                    updated_at=now,
                )
                session.add(run)
                session.flush()
                runtime._upsert_review(
                    session,
                    run=run,
                    predicate=None,
                    candidate_kind="output",
                    reason_code="invalid_candidate",
                    candidate_summary={},
                    now=now,
                )
                failed += 1
                continue

            output = parsed.output
            run = AnalysisRun(
                film_id=film_id,
                analysis_kind=ANALYSIS_KIND,
                provider="legacy",
                model="unknown",
                prompt_version=LEGACY_ANALYSIS_PROMPT_VERSION,
                schema_version=LEGACY_ANALYSIS_SCHEMA_VERSION,
                resolver_version=ANALYSIS_RESOLVER_VERSION,
                policy_version=ANALYSIS_POLICY_VERSION,
                app_version=ANALYSIS_APP_VERSION,
                input_hash=input_hash,
                output_hash=canonical_json_hash(output.model_dump(mode="json")),
                idempotency_key=idempotency_key,
                status="succeeded",
                attempt_count=1,
                result_summary=output.summary,
                started_at=now,
                finished_at=now,
                created_at=now,
                updated_at=now,
            )
            session.add(run)
            session.flush()
            for candidate in output.assertions:
                try:
                    target_id = runtime._resolve_target(session, candidate, None, None, now)
                    subject_id, object_id = (
                        (film_id, target_id)
                        if candidate.direction == "subject_to_target"
                        else (target_id, film_id)
                    )
                    if subject_id == object_id:
                        raise ResolutionFailure("invalid_candidate")
                    runtime._upsert_assertion(
                        session,
                        run=run,
                        candidate=candidate,
                        subject_id=subject_id,
                        object_id=object_id,
                        now=now,
                    )
                except ResolutionFailure as exc:
                    runtime._upsert_review(
                        session,
                        run=run,
                        predicate=candidate.predicate.value,
                        candidate_kind="assertion",
                        reason_code=exc.reason_code,
                        candidate_summary=runtime._assertion_summary(candidate),
                        now=now,
                    )
            if parsed.issue_count:
                runtime._upsert_review(
                    session,
                    run=run,
                    predicate=None,
                    candidate_kind="output",
                    reason_code="invalid_candidate",
                    candidate_summary={},
                    now=now,
                )
            succeeded += 1

        session.flush()
        after = _table_counts(connection)
        counts = {
            "films_scanned": films_scanned,
            "runs_succeeded": succeeded,
            "runs_failed": failed,
            "runs_created": max(0, after["analysis_run"] - before["analysis_run"]),
            "assertions_created": max(0, after["assertion"] - before["assertion"]),
            "provenance_created": max(
                0,
                after["assertion_provenance"] - before["assertion_provenance"],
            ),
            "reviews_created": max(
                0,
                after["analysis_resolution_review"] - before["analysis_resolution_review"],
            ),
            "dropped_fields": dropped_fields,
        }
        warning_count = max(issue_count, counts["reviews_created"])
        report = LegacyAnalysisBackfillReport(dry_run, counts, warning_count)
        if not dry_run and session.get(CanonicalBackfillRun, LEGACY_ANALYSIS_BACKFILL_RUN_KEY) is None:
            now = _now()
            session.add(
                CanonicalBackfillRun(
                    run_key=LEGACY_ANALYSIS_BACKFILL_RUN_KEY,
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


def parse_legacy_analysis(raw: Any, film_id: str) -> ParsedLegacyAnalysis:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (TypeError, ValueError):
            return ParsedLegacyAnalysis(None, 1, 0)
    if not isinstance(raw, dict):
        return ParsedLegacyAnalysis(None, 1, 0)
    allowed = {"micro_genre", "influence_impact", "ancestors", "descendants", "tmdb_metadata"}
    dropped = len(set(raw) - allowed)
    summary = _bounded_text(raw.get("influence_impact"), 1200)
    if not summary:
        return ParsedLegacyAnalysis(None, 1, dropped)
    assertions: list[dict[str, Any]] = []
    issues = 0
    micro_genre = _bounded_text(raw.get("micro_genre"), 900)
    if micro_genre:
        name, definition = _split_micro_genre(micro_genre)
        if name:
            assertions.append(
                {
                    "predicate": "HAS_MICRO_GENRE",
                    "target": {"entity_type": "concept", "display_name": name[:300]},
                    "rationale": (definition or name)[:600],
                }
            )
    for field, direction in (
        ("ancestors", "subject_to_target"),
        ("descendants", "target_to_subject"),
    ):
        values = raw.get(field, [])
        if not isinstance(values, list):
            issues += 1
            continue
        for item in values[:24]:
            if not isinstance(item, dict):
                issues += 1
                continue
            title = _bounded_text(item.get("title"), 300)
            reason = _bounded_text(item.get("reason"), 600)
            relation_type = _bounded_text(item.get("type") or item.get("relation_type"), 80)
            try:
                year = int(item.get("year"))
            except (TypeError, ValueError):
                year = 0
            if not title or not reason or not 1888 <= year <= 2200:
                issues += 1
                continue
            assertions.append(
                {
                    "predicate": "INFLUENCED_BY",
                    "direction": direction,
                    "target": {
                        "entity_type": "film",
                        "display_name": title,
                        "release_year": year,
                    },
                    "rationale": reason,
                    "qualifiers": {"relationship_type": relation_type}
                    if relation_type
                    else None,
                }
            )
    try:
        output = AnalysisV2Output.model_validate(
            {
                "subject_film_id": film_id,
                "summary": summary,
                "assertions": assertions[:50],
            }
        )
    except Exception:
        return ParsedLegacyAnalysis(None, issues + 1, dropped)
    return ParsedLegacyAnalysis(output, issues, dropped)


def _split_micro_genre(value: str) -> tuple[str, str | None]:
    if " - " in value:
        name, definition = value.split(" - ", 1)
        return name.strip(), definition.strip() or None
    return value.strip(), None


def _bounded_text(value: Any, limit: int) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = " ".join(value.split()).strip()
    return normalized[:limit] or None


def _table_counts(connection: Connection) -> dict[str, int]:
    return {
        name: int(connection.execute(text(f"SELECT COUNT(*) FROM {name}")).scalar_one())
        for name in _COUNTED_TABLES
    }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


__all__ = [
    "LEGACY_ANALYSIS_BACKFILL_RUN_KEY",
    "LegacyAnalysisBackfillReport",
    "backfill_legacy_analysis",
    "parse_legacy_analysis",
]
