from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import shutil
import sqlite3
import sys
from contextlib import closing, contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any, Sequence


REPORT_SCHEMA_VERSION = 1
FIXTURE_VERSION = "tmdb-movie-response:v1"
_STRUCTURED_TABLES = (
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
_PRIVACY_CANARIES = {
    "sk-w3-synthetic-secret-canary",
    "C:\\W3Private\\recorded-response.json",
    "<movie><title>W3 source document canary</title></movie>",
}


class StructuredMetadataValidationError(RuntimeError):
    pass


def preflight_rehearsal(input_dir: Path, run_dir: Path) -> dict[str, Any]:
    input_dir = input_dir.resolve()
    run_dir = run_dir.resolve()
    if input_dir.name != "input" or input_dir.parent.name != "gate-a":
        raise StructuredMetadataValidationError("Input must use data/gate-a/input")
    data_root = input_dir.parent.parent.resolve()
    runs_root = (data_root / "structured-metadata" / "runs").resolve()
    if run_dir == runs_root or not run_dir.is_relative_to(runs_root):
        raise StructuredMetadataValidationError("Run directory is outside the isolated W3 runs root")
    if run_dir.exists():
        raise StructuredMetadataValidationError("Run directory already exists")
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,80}", run_dir.name):
        raise StructuredMetadataValidationError("Run identifier is invalid")

    source_database = input_dir / "library.db"
    media_root_file = input_dir / "media-root.txt"
    if not source_database.is_file() or not media_root_file.is_file():
        raise StructuredMetadataValidationError("W3 input is incomplete")
    application_database = (data_root / "library.db").resolve()
    if source_database.resolve() == application_database:
        raise StructuredMetadataValidationError("Input cannot be the application database")
    if any(Path(f"{source_database}{suffix}").exists() for suffix in ("-wal", "-shm")):
        raise StructuredMetadataValidationError("Input must be an offline SQLite copy without sidecars")

    try:
        media_root = Path(media_root_file.read_text(encoding="utf-8").strip()).resolve()
    except OSError as exc:
        raise StructuredMetadataValidationError("Media root contract cannot be read") from exc
    if not media_root.is_absolute() or not media_root.is_dir():
        raise StructuredMetadataValidationError("Media root must be an existing absolute directory")
    if run_dir.is_relative_to(media_root):
        raise StructuredMetadataValidationError("Run directory cannot be inside the media root")

    uri = f"{source_database.resolve().as_uri()}?mode=ro"
    try:
        with closing(sqlite3.connect(uri, uri=True, timeout=30)) as connection:
            integrity = [row[0] for row in connection.execute("PRAGMA integrity_check")]
            foreign_key_issues = connection.execute("PRAGMA foreign_key_check").fetchall()
    except sqlite3.DatabaseError as exc:
        raise StructuredMetadataValidationError("Input is not a readable SQLite database") from exc
    if integrity != ["ok"] or foreign_key_issues:
        raise StructuredMetadataValidationError("Input failed SQLite integrity validation")

    required_free = max(source_database.stat().st_size * 4, 16 * 1024 * 1024)
    runs_root.parent.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(runs_root.parent).free < required_free:
        raise StructuredMetadataValidationError("W3 runs root does not have enough free disk space")
    return {
        "source_database": source_database.resolve(),
        "media_root": media_root,
        "run_dir": run_dir,
        "source_fingerprint": _sha256(source_database)[:16],
    }


def run_rehearsal(input_dir: Path, run_dir: Path) -> dict[str, Any]:
    gate_input = preflight_rehearsal(input_dir, run_dir)
    source_database: Path = gate_input["source_database"]
    media_root: Path = gate_input["media_root"]
    run_dir = gate_input["run_dir"]
    run_dir.mkdir(parents=True, exist_ok=False)
    source_hash = _sha256(source_database)
    source_size = source_database.stat().st_size
    source_sidecars = _sidecar_state(source_database)
    checks: list[dict[str, Any]] = []
    phases = {
        "preflight": "passed",
        "upgrade": "blocked",
        "backfill": "blocked",
        "consistency": "blocked",
        "runtime": "blocked",
        "lifecycle": "blocked",
        "privacy": "blocked",
    }

    try:
        from sqlalchemy import create_engine
        from sqlmodel import SQLModel

        import app.models  # noqa: F401
        from app.database import configure_sqlite_engine
        from app.migrations.backup import create_verified_backup
        from app.migrations.runner import run_migrations
        from app.migrations.versions import MIGRATIONS
        from app.services.compatibility_projection import rebuild_legacy_compatibility_projections
        from app.services.structured_metadata_backfill import backfill_legacy_structured_metadata
        from app.services.structured_metadata_vocab import STRUCTURED_METADATA_VOCABULARY

        backup = create_verified_backup(
            source_database,
            run_dir / "backups" / "source",
            app_version="structured-metadata-w3",
            source_schema_version=_schema_version(source_database),
            target_schema_version=MIGRATIONS[-1].version,
        )
        work_dir = run_dir / "work"
        work_dir.mkdir(parents=True)
        working_database = work_dir / "library.db"
        shutil.copy2(backup.database_path, working_database)
        engine = create_engine(f"sqlite:///{working_database}", connect_args={"timeout": 30})
        configure_sqlite_engine(engine)
        try:
            migration = run_migrations(
                engine,
                working_database,
                app_version="structured-metadata-w3",
                backup_required=False,
            )
            SQLModel.metadata.create_all(engine)
            rebuild_legacy_compatibility_projections(engine)
            phases["upgrade"] = "passed"
            checks.append(
                _check(
                    "schema-upgraded-to-v7",
                    migration.current_version == 7 == MIGRATIONS[-1].version,
                    {"version_equal": migration.current_version == 7 == MIGRATIONS[-1].version},
                )
            )

            before_second_backfill = _table_counts(engine, _STRUCTURED_TABLES)
            with engine.begin() as connection:
                second_backfill = backfill_legacy_structured_metadata(connection)
            after_second_backfill = _table_counts(engine, _STRUCTURED_TABLES)
            backfill_equal = before_second_backfill == after_second_backfill
            checks.append(
                _check(
                    "legacy-backfill-rerun-idempotent",
                    backfill_equal,
                    {
                        "counts_equal": backfill_equal,
                        "movies_revisited": second_backfill.counts["movies_scanned"] >= 0,
                    },
                )
            )
            phases["backfill"] = "passed" if backfill_equal else "failed"

            consistency = _consistency_checks(engine)
            checks.extend(consistency)
            phases["consistency"] = _phase_status(consistency)

            runtime_checks, captured_console = _runtime_checks(
                engine,
                working_database,
                media_root,
                run_dir,
            )
            checks.extend(runtime_checks)
            phases["runtime"] = _phase_status(runtime_checks)

            lifecycle_checks = _lifecycle_checks(engine, working_database, run_dir)
            checks.extend(lifecycle_checks)
            phases["lifecycle"] = _phase_status(lifecycle_checks)

            provisional_report = {
                "schema_version": REPORT_SCHEMA_VERSION,
                "run_id": run_dir.name,
                "source_fingerprint": gate_input["source_fingerprint"],
                "vocabulary_version": STRUCTURED_METADATA_VOCABULARY.version,
                "fixture_version": FIXTURE_VERSION,
                "checks": checks,
                "phases": phases,
                "counts": _table_counts(engine, _STRUCTURED_TABLES),
            }
            privacy_checks = _privacy_checks(
                engine,
                provisional_report,
                captured_console,
                _source_canaries(source_database, media_root),
            )
            checks.extend(privacy_checks)
            phases["privacy"] = _phase_status(privacy_checks)
        finally:
            engine.dispose()
    except StructuredMetadataValidationError:
        raise
    except Exception as exc:
        raise StructuredMetadataValidationError(
            "W3 rehearsal failed inside the isolated working copy"
        ) from exc

    source_unchanged = (
        _sha256(source_database) == source_hash
        and source_database.stat().st_size == source_size
        and _sidecar_state(source_database) == source_sidecars
    )
    checks.append(
        _check(
            "source-input-unchanged",
            source_unchanged,
            {
                "hash_equal": _sha256(source_database) == source_hash,
                "size_equal": source_database.stat().st_size == source_size,
                "sidecars_equal": _sidecar_state(source_database) == source_sidecars,
            },
        )
    )
    overall_status = "passed" if all(item["status"] == "passed" for item in checks) else "failed"
    report = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "run_id": run_dir.name,
        "source_fingerprint": gate_input["source_fingerprint"],
        "vocabulary_version": STRUCTURED_METADATA_VOCABULARY.version,
        "fixture_version": FIXTURE_VERSION,
        "checks": checks,
        "phases": phases,
        "counts": _table_counts_from_database(working_database, _STRUCTURED_TABLES),
        "overall_status": overall_status,
    }
    (run_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def _consistency_checks(engine) -> list[dict[str, Any]]:
    from sqlalchemy import text

    from app.contracts.structured_metadata import credit_semantic_key, structured_metadata_review_key
    from app.services.structured_metadata_backfill import legacy_movie_observation
    from app.services.structured_metadata_vocab import STRUCTURED_METADATA_VOCABULARY

    with engine.connect() as connection:
        foreign_keys = connection.execute(text("PRAGMA foreign_key_check")).all()
        visible_without_title = connection.execute(
            text(
                "SELECT COUNT(*) FROM legacy_movie_alias a "
                "JOIN library_item li ON li.id=a.library_item_id "
                "JOIN film f ON f.id=a.film_id "
                "WHERE li.availability_status <> 'retired' "
                "AND (f.canonical_title IS NULL OR length(trim(f.canonical_title))=0)"
            )
        ).scalar_one()
        graph_type_issues = connection.execute(
            text(
                "SELECT COUNT(*) FROM ("
                "SELECT p.id FROM person p JOIN graph_entity g ON g.id=p.id "
                "WHERE g.entity_type <> 'person' UNION ALL "
                "SELECT c.id FROM concept c JOIN graph_entity g ON g.id=c.id "
                "WHERE g.entity_type <> 'concept')"
            )
        ).scalar_one()
        identity_conflicts = connection.execute(
            text(
                "SELECT COUNT(*) FROM (SELECT provider, external_id FROM external_identity "
                "WHERE identity_status='active' GROUP BY provider, external_id HAVING COUNT(*) > 1)"
            )
        ).scalar_one()
        credits = connection.execute(
            text(
                "SELECT id, film_id, person_id, department, job, character, semantic_key "
                "FROM credit"
            )
        ).mappings().all()
        credit_provenance_counts = {
            str(row[0]): int(row[1])
            for row in connection.execute(
                text("SELECT credit_id, COUNT(*) FROM credit_provenance GROUP BY credit_id")
            ).all()
        }
        countries = connection.execute(
            text("SELECT id, iso_3166_1 FROM film_country")
        ).all()
        country_active_provenance = {
            str(row[0]): int(row[1])
            for row in connection.execute(
                text(
                    "SELECT film_country_id, COUNT(*) FROM film_country_provenance "
                    "WHERE superseded_at IS NULL GROUP BY film_country_id"
                )
            ).all()
        }
        aliases = connection.execute(
            text(
                "SELECT a.film_id, a.library_item_id, m.* FROM legacy_movie_alias a "
                "JOIN movie m ON m.id=a.legacy_movie_id ORDER BY a.legacy_movie_id"
            )
        ).mappings().all()
        review_rows = connection.execute(
            text(
                "SELECT review_key, status FROM structured_metadata_review "
                "WHERE origin_kind='legacy_movie'"
            )
        ).all()
        review_status = {str(row[0]): str(row[1]) for row in review_rows}

    semantic_issues = sum(
        credit_semantic_key(
            str(row["film_id"]),
            str(row["person_id"]),
            str(row["department"]),
            str(row["job"]),
            str(row["character"] or ""),
        )
        != row["semantic_key"]
        for row in credits
    )
    provenance_issues = sum(credit_provenance_counts.get(str(row["id"]), 0) == 0 for row in credits)
    country_code_issues = sum(
        STRUCTURED_METADATA_VOCABULARY.resolve_country(str(code)) != str(code)
        for _country_id, code in countries
    )
    active_country_issues = sum(
        country_active_provenance.get(str(country_id), 0) == 0
        for country_id, _code in countries
    )

    missing_reviews = 0
    for row in aliases:
        observation = legacy_movie_observation(row, str(row["library_item_id"]))
        expected_issues = list(observation.issues)
        for genre in observation.genres:
            if STRUCTURED_METADATA_VOCABULARY.resolve_genre(genre.value) is None:
                from app.contracts.structured_metadata import ObservationIssue

                expected_issues.append(ObservationIssue("concept", "genre_unmapped", genre.value))
        for country in observation.countries:
            if STRUCTURED_METADATA_VOCABULARY.resolve_country(country.value) is None:
                from app.contracts.structured_metadata import ObservationIssue

                expected_issues.append(ObservationIssue("country", "country_unmapped", country.value))
        for issue in expected_issues:
            review_key, _raw_hash = structured_metadata_review_key(
                film_id=str(row["film_id"]),
                field_kind=issue.field_kind,
                reason_code=issue.reason_code,
                origin_kind="legacy_movie",
                origin_ref=str(row["library_item_id"]),
                raw_value=issue.raw_value,
            )
            if review_status.get(review_key) != "open":
                missing_reviews += 1

    return [
        _check("w3-foreign-keys-valid", not foreign_keys, {"issue_count": len(foreign_keys)}),
        _check(
            "visible-aliases-have-selected-title",
            visible_without_title == 0,
            {"missing_count": int(visible_without_title)},
        ),
        _check(
            "structured-graph-types-match",
            graph_type_issues == 0,
            {"issue_count": int(graph_type_issues)},
        ),
        _check(
            "external-identities-do-not-conflict",
            identity_conflicts == 0,
            {"conflict_count": int(identity_conflicts)},
        ),
        _check(
            "credit-semantic-keys-recompute",
            semantic_issues == 0,
            {"issue_count": int(semantic_issues)},
        ),
        _check(
            "credits-have-provenance",
            provenance_issues == 0,
            {"issue_count": int(provenance_issues)},
        ),
        _check(
            "countries-are-valid-and-provenanced",
            country_code_issues == 0 and active_country_issues == 0,
            {
                "invalid_code_count": int(country_code_issues),
                "missing_active_provenance_count": int(active_country_issues),
            },
        ),
        _check(
            "legacy-unmapped-values-have-reviews",
            missing_reviews == 0,
            {"missing_review_count": missing_reviews},
        ),
    ]


def _runtime_checks(engine, working_database: Path, media_root: Path, run_dir: Path):
    from sqlalchemy import text
    from sqlmodel import Session

    from app.contracts.structured_metadata import StructuredMetadataObservation, TitleObservation
    from app.services.library_sync import library_sync_service
    from app.services.structured_metadata_observations import tmdb_structured_metadata_observation
    from app.services.structured_metadata_sync import structured_metadata_synchronizer

    captured = io.StringIO()
    with _runtime_bindings(engine, run_dir / "work" / "artwork-cache"), redirect_stdout(
        captured
    ), redirect_stderr(captured):
        first = library_sync_service.reconcile(str(media_root))
        first_counts = _table_counts(engine, _STRUCTURED_TABLES)
        second = library_sync_service.reconcile(str(media_root))
        second_counts = _table_counts(engine, _STRUCTURED_TABLES)

    with engine.connect() as connection:
        owner = connection.execute(
            text(
                "SELECT a.film_id, a.library_item_id FROM legacy_movie_alias a "
                "JOIN library_item li ON li.id=a.library_item_id "
                "WHERE li.availability_status <> 'retired' ORDER BY a.legacy_movie_id LIMIT 1"
            )
        ).mappings().first()
    replay_equal = False
    nfo_over_tmdb = False
    curated_over_nfo = False
    tmdb_provenance_preserved = False
    if owner is not None:
        fixture_path = Path(__file__).resolve().parents[2] / "fixtures" / "structured_metadata" / "tmdb_movie_v1.json"
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        tmdb_observation = tmdb_structured_metadata_observation(
            fixture,
            549999,
            language="en",
            observed_at="2026-08-25T00:00:00+00:00",
        )
        with Session(engine) as session:
            structured_metadata_synchronizer.sync(
                session,
                film_id=str(owner["film_id"]),
                library_item_id=str(owner["library_item_id"]),
                observation=tmdb_observation,
            )
            session.commit()
        replay_before = _table_counts(engine, _STRUCTURED_TABLES)
        with Session(engine) as session:
            structured_metadata_synchronizer.sync(
                session,
                film_id=str(owner["film_id"]),
                library_item_id=str(owner["library_item_id"]),
                observation=tmdb_observation,
            )
            session.commit()
        replay_equal = replay_before == _table_counts(engine, _STRUCTURED_TABLES)

        nfo_observation = StructuredMetadataObservation(
            origin_kind="nfo",
            origin_ref=str(owner["library_item_id"]),
            source_instance_id="legacy.local",
            observed_at="2026-08-25T00:01:00+00:00",
            complete_fields=frozenset({"titles"}),
            titles=(TitleObservation("W3 NFO priority value", "canonical", "en"),),
        )
        curated_observation = StructuredMetadataObservation(
            origin_kind="curated",
            origin_ref=f"curated:{owner['film_id']}",
            source_instance_id="local.curator",
            observed_at="2026-08-25T00:02:00+00:00",
            complete_fields=frozenset({"titles"}),
            titles=(TitleObservation("W3 curated priority value", "canonical", "en"),),
        )
        with Session(engine) as session:
            structured_metadata_synchronizer.sync(
                session,
                film_id=str(owner["film_id"]),
                library_item_id=str(owner["library_item_id"]),
                observation=nfo_observation,
            )
            session.commit()
        with engine.connect() as connection:
            selected = connection.execute(
                text("SELECT canonical_title FROM film WHERE id=:film_id"),
                {"film_id": owner["film_id"]},
            ).scalar_one()
            tmdb_provenance_preserved = connection.execute(
                text(
                    "SELECT COUNT(*) FROM film_title WHERE film_id=:film_id "
                    "AND origin_kind='tmdb' AND superseded_at IS NULL"
                ),
                {"film_id": owner["film_id"]},
            ).scalar_one() > 0
        nfo_over_tmdb = selected == "W3 NFO priority value"
        with Session(engine) as session:
            structured_metadata_synchronizer.sync(
                session,
                film_id=str(owner["film_id"]),
                library_item_id=str(owner["library_item_id"]),
                observation=curated_observation,
            )
            session.commit()
        with engine.connect() as connection:
            curated_over_nfo = connection.execute(
                text("SELECT canonical_title FROM film WHERE id=:film_id"),
                {"film_id": owner["film_id"]},
            ).scalar_one() == "W3 curated priority value"

    return [
        _check(
            "second-nfo-reconcile-is-idempotent",
            first_counts == second_counts
            and int(second.get("added") or 0) == 0
            and int(first.get("scanned") or 0) > 0,
            {
                "counts_equal": first_counts == second_counts,
                "second_added_zero": int(second.get("added") or 0) == 0,
                "first_scan_nonempty": int(first.get("scanned") or 0) > 0,
            },
        ),
        _check(
            "recorded-tmdb-refresh-is-idempotent",
            replay_equal,
            {"counts_equal": replay_equal, "fixture_available": owner is not None},
        ),
        _check(
            "source-priority-and-provenance-hold",
            nfo_over_tmdb and curated_over_nfo and tmdb_provenance_preserved,
            {
                "nfo_over_tmdb": nfo_over_tmdb,
                "curated_over_nfo": curated_over_nfo,
                "tmdb_provenance_preserved": tmdb_provenance_preserved,
            },
        ),
    ], captured.getvalue()


def _lifecycle_checks(engine, working_database: Path, run_dir: Path):
    from sqlalchemy import create_engine, text

    from app.database import configure_sqlite_engine
    from app.services.library import library_manager

    before_clear = _table_counts(engine, _STRUCTURED_TABLES)
    with _runtime_bindings(engine, run_dir / "work" / "ordinary-clear-artwork"):
        library_manager.clear_library()
    after_clear = _table_counts(engine, _STRUCTURED_TABLES)

    deep_database = run_dir / "work" / "deep-clear.db"
    with closing(sqlite3.connect(working_database, timeout=30)) as source, closing(
        sqlite3.connect(deep_database, timeout=30)
    ) as destination:
        source.backup(destination)
    deep_engine = create_engine(f"sqlite:///{deep_database}", connect_args={"timeout": 30})
    configure_sqlite_engine(deep_engine)
    try:
        with _runtime_bindings(deep_engine, run_dir / "work" / "deep-clear-artwork"):
            library_manager.clear_all_data()
        with deep_engine.connect() as connection:
            structured_empty = all(
                connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one() == 0
                for table in _STRUCTURED_TABLES
            )
            journal_preserved = connection.execute(
                text("SELECT COUNT(*) FROM schema_migrations")
            ).scalar_one() > 0
    finally:
        deep_engine.dispose()
    return [
        _check(
            "ordinary-clear-preserves-structured-metadata",
            before_clear == after_clear,
            {"counts_equal": before_clear == after_clear},
        ),
        _check(
            "deep-clear-removes-structured-metadata-only",
            structured_empty and journal_preserved,
            {
                "structured_empty": structured_empty,
                "migration_journal_preserved": journal_preserved,
            },
        ),
    ]


def _privacy_checks(
    engine,
    provisional_report: dict[str, Any],
    captured_console: str,
    source_canaries: set[str],
):
    from sqlalchemy import text

    from app.jobs.runtime import JobRuntime

    with engine.connect() as connection:
        reviews = connection.execute(
            text("SELECT raw_value FROM structured_metadata_review")
        ).scalars().all()
        events = connection.execute(text("SELECT payload, context FROM events")).all()
        jobs = connection.execute(text("SELECT * FROM job")).mappings().all()
    public_jobs = [JobRuntime.public_job(dict(row)) for row in jobs]
    sensitive_surfaces = {
        "report": provisional_report,
        "review": reviews,
        "event": events,
        "job_public": public_jobs,
        "console": captured_console,
    }
    leaking_layers = [
        layer
        for layer, value in sensitive_surfaces.items()
        if any(canary in json.dumps(value, ensure_ascii=False, default=str) for canary in _PRIVACY_CANARIES)
    ]
    source_leak_layers = [
        layer
        for layer, value in {
            "report": provisional_report,
            "console": captured_console,
        }.items()
        if any(canary in json.dumps(value, ensure_ascii=False, default=str) for canary in source_canaries)
    ]
    observation_in_events = any(
        _contains_key(value, "structured_metadata")
        for row in events
        for value in row
    )
    review_text = json.dumps(reviews, ensure_ascii=False, default=str)
    review_has_absolute_path = bool(
        re.search(r"(?:[A-Za-z]:[\\/]|file://|/(?:Users|home|media)/)", review_text)
    )
    internal_ids = re.findall(
        r"(?:film|person|concept|credit|title|country|review)_[0-9a-f]{32}",
        json.dumps(provisional_report, ensure_ascii=True, default=str),
    )
    return [
        _check(
            "structured-metadata-surfaces-are-redacted",
            not leaking_layers
            and not source_leak_layers
            and not internal_ids
            and not observation_in_events
            and not review_has_absolute_path,
            {
                "leaking_layers": leaking_layers,
                "source_leak_layers": source_leak_layers,
                "untruncated_identifier_count": len(internal_ids),
                "observation_in_events": observation_in_events,
                "review_has_absolute_path": review_has_absolute_path,
            },
        )
    ]


def _source_canaries(source_database: Path, media_root: Path) -> set[str]:
    canaries = {str(media_root.resolve())}
    uri = f"{source_database.resolve().as_uri()}?mode=ro"
    with closing(sqlite3.connect(uri, uri=True, timeout=30)) as connection:
        table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='movie'"
        ).fetchone()
        if table:
            columns = {
                str(row[1]) for row in connection.execute("PRAGMA table_info(movie)").fetchall()
            }
            selected = [
                name
                for name in ("title", "title_cn", "media_path", "folder_path", "nfo_path")
                if name in columns
            ]
            if selected:
                for row in connection.execute(f"SELECT {', '.join(selected)} FROM movie LIMIT 64"):
                    canaries.update(str(value) for value in row if value)
    return {value for value in canaries if len(value) >= 6}


def _contains_key(value: Any, target: str) -> bool:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return False
    if isinstance(value, dict):
        return target in value or any(_contains_key(item, target) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_key(item, target) for item in value)
    return False


@contextmanager
def _runtime_bindings(engine, artwork_cache_dir: Path):
    import app.services.artwork_cache as artwork_cache_module
    import app.services.event_store as event_store_module
    import app.services.library as library_module
    import app.services.user_state as user_state_module

    originals = (
        library_module.engine,
        event_store_module.engine,
        user_state_module.engine,
        artwork_cache_module.ARTWORK_CACHE_DIR,
    )
    library_module.engine = engine
    event_store_module.engine = engine
    user_state_module.engine = engine
    artwork_cache_module.ARTWORK_CACHE_DIR = artwork_cache_dir
    try:
        yield
    finally:
        (
            library_module.engine,
            event_store_module.engine,
            user_state_module.engine,
            artwork_cache_module.ARTWORK_CACHE_DIR,
        ) = originals


def _table_counts(engine, names: Sequence[str]) -> dict[str, int]:
    from sqlalchemy import text

    with engine.connect() as connection:
        return {
            name: int(connection.execute(text(f"SELECT COUNT(*) FROM {name}")).scalar_one())
            for name in names
        }


def _table_counts_from_database(database_path: Path, names: Sequence[str]) -> dict[str, int]:
    with closing(sqlite3.connect(database_path, timeout=30)) as connection:
        return {
            name: int(connection.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0])
            for name in names
        }


def _schema_version(database_path: Path) -> int:
    with closing(sqlite3.connect(database_path, timeout=30)) as connection:
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
        ).fetchone()
        if not exists:
            return 0
        row = connection.execute(
            "SELECT COALESCE(MAX(version), 0) FROM schema_migrations WHERE status='applied'"
        ).fetchone()
        return int(row[0] or 0)


def _check(check_id: str, passed: bool, details: dict[str, Any]) -> dict[str, Any]:
    return {"id": check_id, "status": "passed" if passed else "failed", "details": details}


def _phase_status(checks: Sequence[dict[str, Any]]) -> str:
    return "passed" if checks and all(item["status"] == "passed" for item in checks) else "failed"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sidecar_state(database_path: Path) -> dict[str, bool]:
    return {suffix: Path(f"{database_path}{suffix}").exists() for suffix in ("-wal", "-shm")}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the isolated W3 structured metadata rehearsal")
    subparsers = parser.add_subparsers(dest="command", required=True)
    rehearse = subparsers.add_parser("rehearse")
    rehearse.add_argument("--input-dir", type=Path, required=True)
    rehearse.add_argument("--run-dir", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        report = run_rehearsal(arguments.input_dir, arguments.run_dir)
    except StructuredMetadataValidationError as exc:
        print(f"Structured metadata rehearsal blocked: {exc}", file=sys.stderr)
        return 3
    print(
        json.dumps(
            {
                "run_id": report["run_id"],
                "source_fingerprint": report["source_fingerprint"],
                "overall_status": report["overall_status"],
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    return 0 if report["overall_status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
