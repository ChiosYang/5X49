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
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence


REPORT_SCHEMA_VERSION = 1
VALID_STATUSES = {"passed", "failed", "blocked"}
LOCAL_REQUIRED_PHASES = {
    "preflight",
    "upgrade",
    "idempotence",
    "consistency",
    "runtime",
    "restore",
    "privacy",
}
LOCAL_REQUIRED_CHECKS = {
    "real-library-input",
    "real-media-input-available",
    "source-database-unchanged",
}
DOCKER_REQUIRED_PHASES = {
    "compose_config",
    "image_build",
    "upgrade",
    "read_sources",
    "fresh_install",
    "restore",
    "browser_smoke",
}
DOCKER_REQUIRED_CHECKS = {
    "docker-isolated-resources",
    "docker-input-unchanged",
}


class GateAValidationError(RuntimeError):
    pass


@dataclass(frozen=True)
class GateAInput:
    gate_root: Path
    input_dir: Path
    source_database: Path
    media_root: Path
    run_dir: Path
    source_fingerprint: str
    development_clone: bool


def preflight_rehearsal(input_dir: Path, run_dir: Path) -> GateAInput:
    input_dir = input_dir.resolve()
    run_dir = run_dir.resolve()
    if input_dir.name != "input":
        raise GateAValidationError("Gate input directory must use the fixed input contract")
    gate_root = input_dir.parent
    runs_root = (gate_root / "runs").resolve()
    if run_dir == runs_root or not run_dir.is_relative_to(runs_root):
        raise GateAValidationError("Gate run directory is outside the isolated runs root")
    if run_dir.exists():
        raise GateAValidationError("Gate run directory already exists")
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,80}", run_dir.name):
        raise GateAValidationError("Gate run identifier is invalid")

    source_database = input_dir / "library.db"
    media_root_file = input_dir / "media-root.txt"
    if not source_database.is_file() or not media_root_file.is_file():
        raise GateAValidationError("Gate input is incomplete")
    application_database = (Path(__file__).resolve().parents[2] / "data" / "library.db").resolve()
    if source_database.resolve() == application_database:
        raise GateAValidationError("Gate input cannot be the application database")
    if any(Path(f"{source_database}{suffix}").exists() for suffix in ("-wal", "-shm")):
        raise GateAValidationError("Gate input must be an offline SQLite copy without sidecars")

    try:
        media_root_value = media_root_file.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise GateAValidationError("Gate media-root file cannot be read") from exc
    media_root = Path(media_root_value)
    if not media_root.is_absolute() or not media_root.is_dir():
        raise GateAValidationError("Gate media root must be an existing absolute directory")
    if run_dir.is_relative_to(media_root.resolve()):
        raise GateAValidationError("Gate run directory cannot be inside the media root")

    try:
        uri = f"{source_database.resolve().as_uri()}?mode=ro"
        with closing(sqlite3.connect(uri, uri=True, timeout=30)) as connection:
            integrity = [row[0] for row in connection.execute("PRAGMA integrity_check")]
    except sqlite3.DatabaseError as exc:
        raise GateAValidationError("Gate input is not a readable SQLite database") from exc
    if integrity != ["ok"]:
        raise GateAValidationError("Gate input failed SQLite integrity validation")
    try:
        with closing(sqlite3.connect(uri, uri=True, timeout=30)) as connection:
            foreign_key_issues = connection.execute("PRAGMA foreign_key_check").fetchall()
            journal_exists = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
            ).fetchone()
            invalid_journal = 0
            if journal_exists:
                invalid_journal = int(connection.execute(
                    "SELECT COUNT(*) FROM schema_migrations "
                    "WHERE status NOT IN ('applied', 'failed')"
                ).fetchone()[0])
    except sqlite3.DatabaseError as exc:
        raise GateAValidationError("Gate input preflight could not inspect constraints") from exc
    if foreign_key_issues:
        raise GateAValidationError("Gate input failed SQLite foreign-key validation")
    if invalid_journal:
        raise GateAValidationError("Gate input migration journal is invalid")

    required_free_bytes = max(source_database.stat().st_size * 4, 16 * 1024 * 1024)
    if shutil.disk_usage(runs_root.parent).free < required_free_bytes:
        raise GateAValidationError("Gate run root does not have enough free disk space")

    source_hash = _sha256(source_database)
    development_clone = (
        application_database.is_file()
        and application_database != source_database.resolve()
        and _sha256(application_database) == source_hash
    )

    return GateAInput(
        gate_root=gate_root,
        input_dir=input_dir,
        source_database=source_database.resolve(),
        media_root=media_root.resolve(),
        run_dir=run_dir,
        source_fingerprint=source_hash[:16],
        development_clone=development_clone,
    )


def run_rehearsal(input_dir: Path, run_dir: Path) -> dict[str, Any]:
    gate_input = preflight_rehearsal(input_dir, run_dir)
    gate_input.run_dir.mkdir(parents=True, exist_ok=False)
    checks: list[dict[str, Any]] = []
    phases = {
        "preflight": "passed",
        "upgrade": "blocked",
        "idempotence": "blocked",
        "consistency": "blocked",
        "runtime": "blocked",
        "restore": "blocked",
        "privacy": "blocked",
        "docker": "blocked",
    }
    checks.append(_check(
        "real-library-input",
        not gate_input.development_clone,
        {"eligible": not gate_input.development_clone},
        blocked=gate_input.development_clone,
    ))
    source_hash = _sha256(gate_input.source_database)
    source_size = gate_input.source_database.stat().st_size
    source_sidecars = _sidecar_state(gate_input.source_database)
    source_legacy_events = _table_digest(
        gate_input.source_database,
        "events",
        where="aggregate_type IN ('movie', 'library')",
    )
    try:
        from sqlalchemy import create_engine
        from sqlmodel import SQLModel

        import app.models  # noqa: F401
        from app.database import configure_sqlite_engine
        from app.migrations.backup import create_verified_backup
        from app.migrations.restore import restore_verified_backup
        from app.migrations.runner import run_migrations
        from app.migrations.versions import MIGRATIONS
        from app.services.compatibility_projection import rebuild_legacy_compatibility_projections

        backup_dir = gate_input.run_dir / "backups" / "source"
        source_version = _schema_version(gate_input.source_database)
        backup = create_verified_backup(
            gate_input.source_database,
            backup_dir,
            app_version="gate-a",
            source_schema_version=source_version,
            target_schema_version=MIGRATIONS[-1].version,
        )
        work_dir = gate_input.run_dir / "work"
        work_dir.mkdir(parents=True)
        working_database = work_dir / "library.db"
        shutil.copy2(backup.database_path, working_database)

        engine = create_engine(f"sqlite:///{working_database}", connect_args={"timeout": 30})
        configure_sqlite_engine(engine)
        try:
            migration = run_migrations(
                engine,
                working_database,
                app_version="gate-a",
                backup_required=False,
            )
            SQLModel.metadata.create_all(engine)
            rebuild_legacy_compatibility_projections(engine)
        finally:
            engine.dispose()
        phases["upgrade"] = "passed"
        checks.append(_check(
            "schema-upgraded-to-current",
            migration.current_version == MIGRATIONS[-1].version,
            {"version": migration.current_version},
        ))

        first_fingerprint = _sha256(working_database)
        backup_count = len(list(backup_dir.glob("*.db")))
        engine = create_engine(f"sqlite:///{working_database}", connect_args={"timeout": 30})
        configure_sqlite_engine(engine)
        try:
            second = run_migrations(
                engine,
                working_database,
                app_version="gate-a",
                backup_required=False,
            )
            rebuild_legacy_compatibility_projections(engine)
        finally:
            engine.dispose()
        second_fingerprint = _sha256(working_database)
        idempotent = (
            second.applied_versions == ()
            and first_fingerprint == second_fingerprint
            and len(list(backup_dir.glob("*.db"))) == backup_count
        )
        phases["idempotence"] = "passed" if idempotent else "failed"
        checks.append(_check(
            "migration-rerun-idempotent",
            idempotent,
            {
                "no_applied_versions": second.applied_versions == (),
                "database_equal": first_fingerprint == second_fingerprint,
                "backup_count_equal": len(list(backup_dir.glob("*.db"))) == backup_count,
            },
        ))
        legacy_events_preserved = _table_digest(
            working_database,
            "events",
            where="aggregate_type IN ('movie', 'library')",
        ) == source_legacy_events
        checks.append(_check(
            "legacy-audit-events-preserved",
            legacy_events_preserved,
            {"equal": legacy_events_preserved},
        ))

        engine = create_engine(f"sqlite:///{working_database}", connect_args={"timeout": 30})
        configure_sqlite_engine(engine)
        try:
            consistency_checks = _canonical_consistency_checks(engine)
        finally:
            engine.dispose()
        checks.extend(consistency_checks)
        consistency_passed = all(item["status"] == "passed" for item in consistency_checks)
        phases["consistency"] = "passed" if consistency_passed else "failed"

        with closing(sqlite3.connect(working_database, timeout=30)) as connection:
            connection.execute("CREATE TABLE gate_a_restore_sentinel (value TEXT NOT NULL)")
            connection.execute(
                "INSERT INTO gate_a_restore_sentinel (value) VALUES ('synthetic')"
            )
            connection.commit()
        mutated_hash = _sha256(working_database)
        restored = restore_verified_backup(
            backup.manifest_path,
            working_database,
            expected_target_sha256=mutated_hash,
            preserve_dir=gate_input.run_dir / "backups" / "pre-restore",
            app_version="gate-a",
        )
        restore_equal = (
            restored.restored_sha256 == backup.sha256
            and restored.restored_size_bytes == backup.size_bytes
            and restored.restored_row_counts == backup.row_counts
        )
        checks.append(_check(
            "backup-restored-byte-for-byte",
            restore_equal,
            {
                "hash_equal": restored.restored_sha256 == backup.sha256,
                "size_equal": restored.restored_size_bytes == backup.size_bytes,
                "table_counts_equal": restored.restored_row_counts == backup.row_counts,
            },
        ))

        engine = create_engine(f"sqlite:///{working_database}", connect_args={"timeout": 30})
        configure_sqlite_engine(engine)
        try:
            remigration = run_migrations(
                engine,
                working_database,
                app_version="gate-a-restore",
                backup_required=False,
            )
            SQLModel.metadata.create_all(engine)
            rebuild_legacy_compatibility_projections(engine)
            restored_consistency = _canonical_consistency_checks(engine)
        finally:
            engine.dispose()
        restored_cleanly = (
            remigration.current_version == MIGRATIONS[-1].version
            and all(item["status"] == "passed" for item in restored_consistency)
        )
        checks.append(_check(
            "restored-database-remigrates-cleanly",
            restored_cleanly,
            {
                "version_equal": remigration.current_version == MIGRATIONS[-1].version,
                "consistency_equal": all(
                    item["status"] == "passed" for item in restored_consistency
                ),
            },
        ))
        phases["restore"] = "passed" if restore_equal and restored_cleanly else "failed"

        real_media_count = _video_file_count(gate_input.media_root)
        media_available = real_media_count > 0
        checks.append(_check(
            "real-media-input-available",
            media_available,
            {"available": media_available},
            blocked=not media_available,
        ))
        runtime_console = ""
        if media_available:
            engine = create_engine(f"sqlite:///{working_database}", connect_args={"timeout": 30})
            configure_sqlite_engine(engine)
            try:
                runtime_checks, runtime_console = _runtime_checks(
                    engine,
                    working_database,
                    gate_input.media_root,
                    gate_input.run_dir,
                )
            finally:
                engine.dispose()
            checks.extend(runtime_checks)
            phases["runtime"] = (
                "passed" if all(item["status"] == "passed" for item in runtime_checks) else "failed"
            )

        engine = create_engine(f"sqlite:///{working_database}", connect_args={"timeout": 30})
        configure_sqlite_engine(engine)
        try:
            privacy_checks = _privacy_checks(
                engine,
                _privacy_canaries(gate_input.source_database, gate_input.media_root),
                runtime_console,
                {
                    "run_id": gate_input.run_dir.name,
                    "source_fingerprint": gate_input.source_fingerprint,
                    "checks": checks,
                    "phases": phases,
                },
            )
        finally:
            engine.dispose()
        checks.extend(privacy_checks)
        phases["privacy"] = (
            "passed" if all(item["status"] == "passed" for item in privacy_checks) else "failed"
        )

        source_unchanged = (
            _sha256(gate_input.source_database) == source_hash
            and gate_input.source_database.stat().st_size == source_size
            and _sidecar_state(gate_input.source_database) == source_sidecars
        )
        checks.append(_check(
            "source-database-unchanged",
            source_unchanged,
            {
                "hash_equal": _sha256(gate_input.source_database) == source_hash,
                "size_equal": gate_input.source_database.stat().st_size == source_size,
                "sidecars_equal": _sidecar_state(gate_input.source_database) == source_sidecars,
            },
        ))
    except GateAValidationError:
        raise
    except Exception as exc:
        raise GateAValidationError("Gate rehearsal failed during isolated migration") from exc

    failed = any(item["status"] == "failed" for item in checks)
    blocked = any(item["status"] == "blocked" for item in checks) or any(
        value == "blocked" for key, value in phases.items() if key != "docker"
    )
    local_status = "failed" if failed else "blocked" if blocked else "passed"
    overall_status = "failed" if local_status == "failed" else "blocked"
    payload = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "run_id": gate_input.run_dir.name,
        "source_fingerprint": gate_input.source_fingerprint,
        "checks": checks,
        "phases": phases,
        "local_status": local_status,
        "docker_status": "blocked",
        "overall_status": overall_status,
    }
    (gate_input.run_dir / "local-report.json").write_text(
        json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload


def _canonical_consistency_checks(engine) -> list[dict[str, Any]]:
    from sqlalchemy import inspect, text

    from app.services.canonical_shadow import CanonicalShadowReader

    required_tables = {
        "movie",
        "movie_user_state",
        "film",
        "library_item",
        "media_asset",
        "legacy_movie_alias",
        "viewing",
        "film_profile_state",
        "schema_migrations",
    }
    tables = set(inspect(engine).get_table_names())
    checks = [_check(
        "canonical-tables-present",
        required_tables.issubset(tables),
        {"complete": required_tables.issubset(tables)},
    )]
    if not required_tables.issubset(tables):
        return checks

    with engine.connect() as connection:
        foreign_key_issues = len(connection.execute(text("PRAGMA foreign_key_check")).all())
        missing_aliases = connection.execute(text(
            "SELECT COUNT(*) FROM movie m LEFT JOIN legacy_movie_alias a "
            "ON a.legacy_movie_id = m.id WHERE a.legacy_movie_id IS NULL"
        )).scalar_one()
        visible_alias_without_movie = connection.execute(text(
            "SELECT COUNT(*) FROM legacy_movie_alias a "
            "JOIN library_item li ON li.id = a.library_item_id "
            "LEFT JOIN movie m ON m.id = a.legacy_movie_id "
            "WHERE (li.availability_status <> 'retired' "
            "OR a.legacy_library_status = 'reverted') AND m.id IS NULL"
        )).scalar_one()
        duplicate_identities = connection.execute(text(
            "SELECT COUNT(*) FROM (SELECT provider, external_id FROM external_identity "
            "WHERE identity_status = 'active' GROUP BY provider, external_id HAVING COUNT(*) > 1)"
        )).scalar_one()
        invalid_assets = connection.execute(text(
            "SELECT COUNT(*) FROM media_asset WHERE "
            "(library_item_id IS NULL AND film_id IS NULL) OR "
            "(library_item_id IS NOT NULL AND film_id IS NOT NULL)"
        )).scalar_one()
        orphan_reviews = connection.execute(text(
            "SELECT COUNT(*) FROM identity_review r LEFT JOIN legacy_movie_alias a "
            "ON a.legacy_movie_id = r.legacy_movie_id "
            "WHERE r.legacy_movie_id IS NOT NULL AND a.legacy_movie_id IS NULL"
        )).scalar_one()
        status_mismatches = connection.execute(text(
            "SELECT COUNT(*) FROM legacy_movie_alias a "
            "JOIN library_item li ON li.id = a.library_item_id "
            "JOIN movie m ON m.id = a.legacy_movie_id "
            "WHERE m.library_status <> CASE "
            "WHEN a.legacy_library_status = 'reverted' THEN 'reverted' "
            "ELSE li.availability_status END"
        )).scalar_one()
        expected_history_aliases = [
            str(value)
            for value in connection.execute(text(
                "SELECT MIN(a.legacy_movie_id) FROM viewing v "
                "JOIN legacy_movie_alias a ON a.film_id = v.film_id "
                "JOIN library_item li ON li.id = a.library_item_id "
                "WHERE v.review_status='confirmed' AND v.deleted_at IS NULL "
                "AND (li.availability_status <> 'retired' "
                "OR a.legacy_library_status='reverted') "
                "GROUP BY v.film_id ORDER BY MAX(COALESCE(v.watched_at, v.updated_at)) DESC, "
                "v.film_id"
            )).scalars()
        ]

    checks.extend([
        _check("foreign-keys-valid", foreign_key_issues == 0, {"issue_count": foreign_key_issues}),
        _check("legacy-movies-have-aliases", missing_aliases == 0, {"missing_count": missing_aliases}),
        _check(
            "visible-aliases-have-legacy-projections",
            visible_alias_without_movie == 0,
            {"missing_count": visible_alias_without_movie},
        ),
        _check(
            "external-identities-are-unique",
            duplicate_identities == 0,
            {"duplicate_count": duplicate_identities},
        ),
        _check("media-asset-ownership-valid", invalid_assets == 0, {"issue_count": invalid_assets}),
        _check("identity-reviews-are-linked", orphan_reviews == 0, {"orphan_count": orphan_reviews}),
        _check(
            "library-availability-projection-equal",
            status_mismatches == 0,
            {"mismatch_count": status_mismatches},
        ),
    ])
    reader = CanonicalShadowReader(engine)
    library_report = reader.compare_library()
    user_state_report = reader.compare_user_states()
    history_aliases = [
        str(entry["movie"]["id"])
        for entry in reader.watch_history()
    ]
    checks.extend([
        _check(
            "library-shadow-equal",
            library_report.records_different == 0 and library_report.records_missing == 0,
            {
                "different_count": library_report.records_different,
                "missing_count": library_report.records_missing,
                "fields": sorted({item.field for item in library_report.differences}),
            },
        ),
        _check(
            "user-state-shadow-equal",
            user_state_report.records_different == 0 and user_state_report.records_missing == 0,
            {
                "different_count": user_state_report.records_different,
                "missing_count": user_state_report.records_missing,
                "fields": sorted({item.field for item in user_state_report.differences}),
            },
        ),
        _check(
            "watch-history-uses-one-stable-alias-per-film",
            history_aliases == expected_history_aliases
            and len(history_aliases) == len(set(history_aliases)),
            {
                "ordering_equal": history_aliases == expected_history_aliases,
                "unique_per_film": len(history_aliases) == len(set(history_aliases)),
            },
        ),
    ])
    return checks


def _runtime_checks(
    engine,
    working_database: Path,
    media_root: Path,
    run_dir: Path,
) -> tuple[list[dict[str, Any]], str]:
    from sqlalchemy import text

    from app.services.canonical_shadow import CanonicalShadowReader
    from app.services.library import library_manager
    from app.services.library_sync import library_sync_service

    captured = io.StringIO()
    with _runtime_bindings(engine, run_dir / "work" / "artwork-cache"), redirect_stdout(
        captured
    ), redirect_stderr(captured):
        first = library_sync_service.reconcile(str(media_root))
        first_counts = _domain_counts(engine)
        _resolve_relink_jobs(engine)
        second = library_sync_service.reconcile(str(media_root))
        second_counts = _domain_counts(engine)

        with engine.connect() as connection:
            restorable_aliases = {
                str(value)
                for value in connection.execute(
                    text(
                        "SELECT a.legacy_movie_id FROM legacy_movie_alias a "
                        "JOIN movie m ON m.id = a.legacy_movie_id "
                        "WHERE m.library_status <> 'retired' "
                        "AND (m.media_path LIKE :root OR m.folder_path LIKE :root)"
                    ),
                    {"root": f"{str(media_root.resolve())}%"},
                ).scalars()
            }
            personal_before = _personal_state_digest(connection, restorable_aliases)

        library_manager.clear_library()
        library_sync_service.reconcile(str(media_root))
        with engine.connect() as connection:
            restored_aliases = {
                str(value)
                for value in connection.execute(
                    text(
                        "SELECT a.legacy_movie_id FROM legacy_movie_alias a "
                        "JOIN library_item li ON li.id = a.library_item_id "
                        "WHERE li.availability_status <> 'retired'"
                    )
                ).scalars()
            }
            personal_after = _personal_state_digest(connection, restorable_aliases)
        reader = CanonicalShadowReader(engine)
        restored_shadow_reports = [reader.compare_movie(movie_id) for movie_id in restored_aliases]
        restored_different = sum(report.records_different for report in restored_shadow_reports)
        restored_missing = sum(report.records_missing for report in restored_shadow_reports)
        restored_fields = sorted({
            difference.field
            for report in restored_shadow_reports
            for difference in report.differences
        })

    no_growth = all(second_counts[name] == first_counts[name] for name in first_counts)
    checks = [
        _check(
            "second-full-reconcile-is-idempotent",
            no_growth and int(second.get("added") or 0) == 0,
            {
                "domain_counts_equal": no_growth,
                "second_added_zero": int(second.get("added") or 0) == 0,
                "first_scan_nonempty": int(first.get("scanned") or 0) > 0,
            },
        ),
        _check(
            "ordinary-clear-restores-aliases-and-personal-state",
            bool(restorable_aliases)
            and restorable_aliases.issubset(restored_aliases)
            and personal_before == personal_after,
            {
                "had_restorable_aliases": bool(restorable_aliases),
                "aliases_restored": restorable_aliases.issubset(restored_aliases),
                "personal_state_equal": personal_before == personal_after,
            },
        ),
        _check(
            "post-restore-shadow-equal",
            restored_different == 0 and restored_missing == 0,
            {
                "different_count": restored_different,
                "missing_count": restored_missing,
                "fields": restored_fields,
            },
        ),
    ]
    checks.append(_deep_clear_check(working_database, run_dir))
    checks.extend(_mini_library_checks(run_dir))
    return checks, captured.getvalue()


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


def _resolve_relink_jobs(engine) -> None:
    from sqlalchemy import text

    from app.services.library import library_manager

    with engine.connect() as connection:
        rows = connection.execute(text(
            "SELECT payload FROM job WHERE type='library.resolve_relink' AND status='queued'"
        )).scalars().all()
    for payload in rows:
        if isinstance(payload, str):
            payload = json.loads(payload)
        library_manager.resolve_relink(dict(payload or {}))


def _domain_counts(engine) -> dict[str, int]:
    from sqlalchemy import text

    names = ("film", "library_item", "legacy_movie_alias", "viewing", "identity_review")
    with engine.connect() as connection:
        return {
            name: int(connection.execute(text(f"SELECT COUNT(*) FROM {name}")).scalar_one())
            for name in names
        }


def _personal_state_digest(connection, aliases: set[str]) -> str:
    from sqlalchemy import text

    if not aliases:
        return hashlib.sha256(b"empty").hexdigest()
    parameters = {f"alias_{index}": value for index, value in enumerate(sorted(aliases))}
    placeholders = ", ".join(f":{key}" for key in parameters)
    rows = connection.execute(
        text(
            "SELECT a.legacy_movie_id, COALESCE(fps.favorite, 0), v.source, "
            "v.review_status, v.watched_at, v.rating, v.review, v.deleted_at "
            "FROM legacy_movie_alias a "
            "LEFT JOIN film_profile_state fps ON fps.film_id = a.film_id "
            "LEFT JOIN viewing v ON v.film_id = a.film_id "
            f"WHERE a.legacy_movie_id IN ({placeholders}) "
            "ORDER BY a.legacy_movie_id, v.id"
        ),
        parameters,
    ).all()
    encoded = json.dumps([list(row) for row in rows], default=str, ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _deep_clear_check(working_database: Path, run_dir: Path) -> dict[str, Any]:
    from sqlalchemy import create_engine, text

    from app.database import configure_sqlite_engine
    from app.services.library import library_manager

    deep_database = run_dir / "work" / "deep-clear.db"
    with closing(sqlite3.connect(working_database, timeout=30)) as source, closing(
        sqlite3.connect(deep_database, timeout=30)
    ) as destination:
        source.backup(destination)
    engine = create_engine(f"sqlite:///{deep_database}", connect_args={"timeout": 30})
    configure_sqlite_engine(engine)
    try:
        with _runtime_bindings(engine, run_dir / "work" / "deep-clear-artwork"):
            library_manager.clear_all_data()
        with engine.connect() as connection:
            domain_empty = all(
                int(connection.execute(text(f"SELECT COUNT(*) FROM {name}")).scalar_one()) == 0
                for name in (
                    "movie",
                    "movie_user_state",
                    "film",
                    "library_item",
                    "legacy_movie_alias",
                    "viewing",
                    "identity_review",
                    "person",
                    "credit",
                    "credit_provenance",
                    "concept",
                    "concept_alias",
                    "film_title",
                    "film_country",
                    "film_country_provenance",
                    "structured_metadata_review",
                    "analysis_run",
                    "assertion",
                    "evidence",
                    "assertion_evidence",
                    "assertion_provenance",
                    "analysis_resolution_review",
                    "job",
                    "events",
                )
            )
            predicate_registry_preserved = int(
                connection.execute(text("SELECT COUNT(*) FROM assertion_predicate")).scalar_one()
            ) == 9
            journal_preserved = int(connection.execute(
                text("SELECT COUNT(*) FROM schema_migrations WHERE status='applied'")
            ).scalar_one()) > 0
    finally:
        engine.dispose()
    return _check(
        "destructive-clear-is-confined-to-extra-copy",
        domain_empty and predicate_registry_preserved and journal_preserved,
        {
            "domain_empty": domain_empty,
            "predicate_registry_preserved": predicate_registry_preserved,
            "migration_journal_preserved": journal_preserved,
        },
    )


def _large_file_budget_check(run_dir: Path) -> dict[str, Any]:
    from app.services.file_identity import FOREGROUND_BUDGET_BYTES, observe_file

    sample = run_dir / "work" / "mini-library" / "large-video.mkv"
    sample.parent.mkdir(parents=True, exist_ok=True)
    with sample.open("wb") as stream:
        stream.write(b"gate-a")
        stream.seek(FOREGROUND_BUDGET_BYTES + 1024)
        stream.write(b"x")
    observation = observe_file(sample)
    passed = (
        observation is not None
        and observation.bytes_read <= FOREGROUND_BUDGET_BYTES
        and observation.content_hash is None
        and observation.content_fingerprint.startswith("sha256-sampled-v1:")
    )
    return _check(
        "large-file-foreground-budget-enforced",
        passed,
        {
            "within_budget": observation is not None
            and observation.bytes_read <= FOREGROUND_BUDGET_BYTES,
            "sampled": observation is not None and observation.content_hash is None,
        },
    )


def _mini_library_checks(run_dir: Path) -> list[dict[str, Any]]:
    from sqlalchemy import create_engine, text
    from sqlmodel import SQLModel

    import app.models  # noqa: F401
    from app.database import configure_sqlite_engine
    from app.migrations.runner import run_migrations
    from app.services.library import library_manager

    mini_root = run_dir / "work" / "mini-library"
    mini_root.mkdir(parents=True, exist_ok=True)
    database_path = mini_root / "library.db"
    engine = create_engine(f"sqlite:///{database_path}", connect_args={"timeout": 30})
    configure_sqlite_engine(engine)
    try:
        SQLModel.metadata.create_all(engine)
        run_migrations(engine, database_path, app_version="gate-a-mini", backup_required=False)
        with _runtime_bindings(engine, mini_root / "artwork-cache"):
            original = mini_root / "edition-a" / "movie.mkv"
            original.parent.mkdir()
            original.write_bytes(b"platform-relink")
            library_manager.add_movies([_mini_movie("platform-a", original, "7001")])
            with engine.connect() as connection:
                stable_alias = str(connection.execute(text(
                    "SELECT legacy_movie_id FROM legacy_movie_alias"
                )).scalar_one())
                stable_item = str(connection.execute(text(
                    "SELECT library_item_id FROM legacy_movie_alias"
                )).scalar_one())

            moved = mini_root / "edition-renamed" / "movie.mkv"
            moved.parent.mkdir()
            original.replace(moved)
            library_manager.add_movies([_mini_movie("platform-b", moved, "7001")])
            with engine.connect() as connection:
                relink_alias = str(connection.execute(text(
                    "SELECT legacy_movie_id FROM legacy_movie_alias"
                )).scalar_one())
                relink_item = str(connection.execute(text(
                    "SELECT library_item_id FROM legacy_movie_alias"
                )).scalar_one())
                relink_path = str(connection.execute(text(
                    "SELECT media_path FROM movie WHERE id=:movie_id"
                ), {"movie_id": stable_alias}).scalar_one())

            library_manager.mark_path_missing(str(moved))
            library_manager.add_movies([_mini_movie("platform-c", moved, "7001")])
            with engine.connect() as connection:
                restored_status = str(connection.execute(text(
                    "SELECT library_status FROM movie WHERE id=:movie_id"
                ), {"movie_id": stable_alias}).scalar_one())

            second_edition = mini_root / "edition-b" / "movie.mkv"
            second_edition.parent.mkdir()
            second_edition.write_bytes(b"second-edition")
            library_manager.add_movies([_mini_movie("multi-item", second_edition, "7001")])
            with engine.connect() as connection:
                shared_film_counts = connection.execute(text(
                    "SELECT COUNT(DISTINCT film_id), COUNT(*), "
                    "COUNT(DISTINCT legacy_movie_id) FROM legacy_movie_alias "
                    "WHERE film_id=(SELECT film_id FROM legacy_movie_alias "
                    "WHERE legacy_movie_id=:movie_id)"
                ), {"movie_id": stable_alias}).one()

            hash_result = _exercise_full_hash_disambiguation(
                engine,
                mini_root / "hash-relink",
            )
    finally:
        engine.dispose()

    return [
        _check(
            "mini-platform-id-relink-preserves-alias",
            stable_alias == relink_alias
            and stable_item == relink_item
            and relink_path == str(moved),
            {
                "alias_equal": stable_alias == relink_alias,
                "item_equal": stable_item == relink_item,
                "locator_equal": relink_path == str(moved),
            },
        ),
        _check(
            "mini-missing-restore-preserves-alias",
            restored_status == "available" and stable_alias == relink_alias,
            {
                "available": restored_status == "available",
                "alias_equal": stable_alias == relink_alias,
            },
        ),
        _check(
            "mini-multiple-items-share-one-film",
            tuple(int(value) for value in shared_film_counts) == (1, 2, 2),
            {
                "one_film": int(shared_film_counts[0]) == 1,
                "two_items": int(shared_film_counts[1]) == 2,
                "two_aliases": int(shared_film_counts[2]) == 2,
            },
        ),
        _check(
            "mini-full-hash-disambiguates-collision",
            hash_result["passed"],
            {
                "job_deduped": hash_result["job_deduped"],
                "matched_one": hash_result["matched_one"],
                "alias_preserved": hash_result["alias_preserved"],
            },
        ),
        _large_file_budget_check(run_dir),
    ]


def _exercise_full_hash_disambiguation(engine, root: Path) -> dict[str, bool]:
    from sqlalchemy import text

    from app.services.file_identity import full_content_hash, observe_file
    from app.services.library import library_manager

    size = 13 * 1024 * 1024
    first_path = root / "first" / "movie.mkv"
    second_path = root / "second" / "movie.mkv"
    moved_path = root / "moved" / "movie.mkv"
    for path, first_byte in ((first_path, b"A"), (second_path, b"B")):
        path.parent.mkdir(parents=True)
        with path.open("wb") as stream:
            stream.write(first_byte)
            stream.seek(size - 1)
            stream.write(b"\0")
    with second_path.open("r+b") as stream:
        stream.seek(4 * 1024 * 1024 + 128)
        stream.write(b"different-full-hash")

    library_manager.add_movies([_mini_movie("hash-first", first_path, "8001")])
    with engine.connect() as connection:
        first_alias = str(connection.execute(text(
            "SELECT legacy_movie_id FROM legacy_movie_alias a "
            "JOIN movie m ON m.id=a.legacy_movie_id WHERE m.tmdb_id='8001'"
        )).scalar_one())
        first_item = str(connection.execute(text(
            "SELECT library_item_id FROM legacy_movie_alias WHERE legacy_movie_id=:movie_id"
        ), {"movie_id": first_alias}).scalar_one())
    library_manager.add_movies([_mini_movie("hash-second", second_path, "8002")])
    with engine.connect() as connection:
        second_item = str(connection.execute(text(
            "SELECT a.library_item_id FROM legacy_movie_alias a "
            "JOIN movie m ON m.id=a.legacy_movie_id WHERE m.tmdb_id='8002'"
        )).scalar_one())

    with second_path.open("r+b") as stream:
        stream.seek(0)
        stream.write(b"A")
    observation = observe_file(first_path)
    if observation is None:
        return {"passed": False, "job_deduped": False, "matched_one": False, "alias_preserved": False}
    first_hash = full_content_hash(first_path)
    with engine.begin() as connection:
        connection.execute(text(
            "UPDATE media_asset SET content_fingerprint=:fingerprint, content_hash=NULL "
            "WHERE library_item_id IN (:first_item, :second_item) AND asset_kind='video'"
        ), {
            "fingerprint": observation.content_fingerprint,
            "first_item": first_item,
            "second_item": second_item,
        })
        connection.execute(text(
            "UPDATE media_asset SET content_hash=:content_hash "
            "WHERE library_item_id=:first_item AND asset_kind='video'"
        ), {"content_hash": first_hash, "first_item": first_item})
    moved_path.parent.mkdir(parents=True)
    shutil.copyfile(first_path, moved_path)
    first_path.unlink()

    library_manager.add_movies([_mini_movie("hash-moved", moved_path, "8001")])
    library_manager.add_movies([_mini_movie("hash-moved-repeat", moved_path, "8001")])
    with engine.connect() as connection:
        jobs = connection.execute(text(
            "SELECT payload FROM job WHERE type='library.resolve_relink' ORDER BY id"
        )).scalars().all()
    payload = jobs[0] if jobs else None
    if isinstance(payload, str):
        payload = json.loads(payload)
    result = library_manager.resolve_relink(dict(payload or {})) if payload else {}
    with engine.connect() as connection:
        final_item = connection.execute(text(
            "SELECT library_item_id FROM legacy_movie_alias WHERE legacy_movie_id=:movie_id"
        ), {"movie_id": first_alias}).scalar_one_or_none()
        final_path = connection.execute(text(
            "SELECT media_path FROM movie WHERE id=:movie_id"
        ), {"movie_id": first_alias}).scalar_one_or_none()
    job_deduped = len(jobs) == 1
    matched_one = int(result.get("matched") or 0) == 1
    alias_preserved = final_item == first_item and final_path == str(moved_path)
    return {
        "passed": job_deduped and matched_one and alias_preserved,
        "job_deduped": job_deduped,
        "matched_one": matched_one,
        "alias_preserved": alias_preserved,
    }


def _mini_movie(scanner_id: str, media_path: Path, tmdb_id: str) -> dict[str, Any]:
    return {
        "id": scanner_id,
        "title": f"Synthetic Film {tmdb_id}",
        "title_cn": f"Synthetic Film {tmdb_id}",
        "year": 2026,
        "tmdb_id": tmdb_id,
        "media_path": str(media_path),
        "folder_path": str(media_path.parent),
        "folder_name": media_path.parent.name,
        "video_file": media_path.name,
        "file_size": media_path.stat().st_size,
        "file_mtime": media_path.stat().st_mtime,
        "library_status": "available",
        "metadata_source": "nfo",
        "scrape_status": "matched",
    }


def _privacy_canaries(source_database: Path, media_root: Path) -> set[str]:
    import xml.etree.ElementTree as ET

    canaries = {str(media_root.resolve()), "sk-gate-a-synthetic-secret-canary"}
    uri = f"{source_database.resolve().as_uri()}?mode=ro"
    with closing(sqlite3.connect(uri, uri=True, timeout=30)) as connection:
        movie_table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='movie'"
        ).fetchone()
        if movie_table:
            columns = {
                str(row[1]) for row in connection.execute("PRAGMA table_info(movie)").fetchall()
            }
            selected = [
                name for name in ("title", "title_cn", "media_path", "folder_path", "nfo_path")
                if name in columns
            ]
            if selected:
                for row in connection.execute(f"SELECT {', '.join(selected)} FROM movie"):
                    canaries.update(str(value) for value in row if value)
    for nfo_path in media_root.rglob("*.nfo"):
        try:
            root = ET.parse(nfo_path).getroot()
        except (ET.ParseError, OSError):
            continue
        for field in ("title", "originaltitle"):
            value = root.findtext(field)
            if value:
                canaries.add(value)
        if len(canaries) >= 128:
            break
    return {value for value in canaries if len(value) >= 6}


def _privacy_checks(
    engine,
    canaries: set[str],
    captured_console: str,
    provisional_report: dict[str, Any],
) -> list[dict[str, Any]]:
    from sqlalchemy import text

    from app.jobs.runtime import JobRuntime

    leak_layers: list[str] = []
    with engine.connect() as connection:
        event_rows = connection.execute(text(
            "SELECT aggregate_id, payload, context FROM events "
            "WHERE aggregate_type='library_item'"
        )).all()
        job_rows = connection.execute(text(
            "SELECT id, type, status, payload, progress, result, result_summary, error, "
            "attempts, max_attempts, priority, dedupe_key, cancel_requested, created_at, "
            "updated_at, started_at, finished_at FROM job"
        )).mappings().all()
    normalized_events = [
        [
            _decode_json_value(value)
            for value in row
        ]
        for row in event_rows
    ]
    if _contains_canary_value(normalized_events, canaries):
        leak_layers.append("event_record")
    public_jobs = [JobRuntime.public_job(dict(row)) for row in job_rows]
    synthetic_values = sorted(canaries, key=len, reverse=True)
    public_jobs.append(JobRuntime.public_job({
        "id": "job_gate_a_synthetic",
        "type": "library.resolve_relink",
        "status": "queued",
        "payload": {
            "source_instance_id": "legacy.local",
            "content_fingerprint": "sk-gate-a-synthetic-secret-canary",
            "items": [{
                "movie": {
                    "title": synthetic_values[0] if synthetic_values else "synthetic",
                    "media_path": str(next(iter(canaries), "synthetic")),
                },
                "candidate_item_ids": [],
            }],
        },
    }))
    if _contains_canary_value(public_jobs, canaries):
        leak_layers.append("job_public")
    if _contains_canary_value(provisional_report, canaries):
        leak_layers.append("report")

    return [
        _check(
            "sensitive-canaries-not-exposed",
            not leak_layers,
            {"leak_layers": sorted(leak_layers)},
        ),
        _check(
            "runtime-console-was-contained",
            True,
            {"captured": bool(captured_console)},
        ),
    ]


def _decode_json_value(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _contains_canary_value(value: Any, canaries: set[str]) -> bool:
    if isinstance(value, dict):
        return any(
            _contains_canary_value(key, canaries)
            or _contains_canary_value(item, canaries)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple, set)):
        return any(_contains_canary_value(item, canaries) for item in value)
    if value is None:
        return False
    text_value = str(value)
    return any(canary in text_value for canary in canaries)


def _check(
    check_id: str,
    passed: bool,
    details: dict[str, Any],
    *,
    blocked: bool = False,
) -> dict[str, Any]:
    return {
        "id": check_id,
        "status": "blocked" if blocked else "passed" if passed else "failed",
        "details": details,
    }


def _schema_version(database_path: Path) -> int:
    uri = f"{database_path.resolve().as_uri()}?mode=ro"
    with closing(sqlite3.connect(uri, uri=True, timeout=30)) as connection:
        table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
        ).fetchone()
        if not table:
            return 0
        row = connection.execute(
            "SELECT MAX(version) FROM schema_migrations WHERE status='applied'"
        ).fetchone()
        return int(row[0] or 0)


def _video_file_count(media_root: Path) -> int:
    extensions = {".mkv", ".mp4", ".avi", ".mov", ".wmv", ".m4v", ".ts", ".iso"}
    return sum(1 for path in media_root.rglob("*") if path.is_file() and path.suffix.casefold() in extensions)


def _sidecar_state(database_path: Path) -> dict[str, tuple[bool, int]]:
    return {
        suffix: (path.exists(), path.stat().st_size if path.exists() else 0)
        for suffix in ("-wal", "-shm")
        for path in (Path(f"{database_path}{suffix}"),)
    }


def _table_digest(database_path: Path, table: str, *, where: str | None = None) -> str:
    if not re.fullmatch(r"[a-z_]+", table):
        raise GateAValidationError("Gate table digest identifier is invalid")
    uri = f"{database_path.resolve().as_uri()}?mode=ro"
    with closing(sqlite3.connect(uri, uri=True, timeout=30)) as connection:
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
        if not exists:
            return hashlib.sha256(b"missing").hexdigest()
        query = f"SELECT * FROM {table}"
        if where:
            query += f" WHERE {where}"
        columns = [str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")]
        order_column = "id" if "id" in columns else columns[0]
        rows = connection.execute(f"{query} ORDER BY {order_column}").fetchall()
    encoded = json.dumps(rows, default=str, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def conclude_reports(local_report_path: Path, docker_report_path: Path | None = None) -> dict[str, Any]:
    local = _read_report(local_report_path)
    docker = _read_report(docker_report_path) if docker_report_path else None
    local_status = _qualified_evidence_status(
        local,
        "local_status",
        LOCAL_REQUIRED_PHASES,
        LOCAL_REQUIRED_CHECKS,
    )
    docker_status = (
        _qualified_evidence_status(
            docker,
            "docker_status",
            DOCKER_REQUIRED_PHASES,
            DOCKER_REQUIRED_CHECKS,
        )
        if docker is not None
        else "blocked"
    )
    if "failed" in {local_status, docker_status}:
        overall_status = "failed"
    elif "blocked" in {local_status, docker_status}:
        overall_status = "blocked"
    else:
        overall_status = "passed"
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "run_id": str(local.get("run_id") or "unknown"),
        "source_fingerprint": str(local.get("source_fingerprint") or "unknown"),
        "checks": [
            *(local.get("checks") or []),
            *((docker or {}).get("checks") or []),
        ],
        "phases": {
            **(local.get("phases") or {}),
            **((docker or {}).get("phases") or {"docker": "blocked"}),
        },
        "local_status": local_status,
        "docker_status": docker_status,
        "overall_status": overall_status,
    }


def _read_report(path: Path | None) -> dict[str, Any]:
    if path is None or not path.is_file():
        raise GateAValidationError("Gate evidence report does not exist")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GateAValidationError("Gate evidence report is not valid JSON") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != REPORT_SCHEMA_VERSION:
        raise GateAValidationError("Gate evidence report schema is not supported")
    return payload


def _status(value: Any, field: str) -> str:
    if value not in VALID_STATUSES:
        raise GateAValidationError(f"Gate evidence {field} is invalid")
    return str(value)


def _qualified_evidence_status(
    report: dict[str, Any],
    field: str,
    required_phases: set[str],
    required_checks: set[str],
) -> str:
    claimed = _status(report.get(field), field)
    checks = {
        str(item.get("id")): item.get("status")
        for item in report.get("checks") or []
        if isinstance(item, dict)
    }
    phases = report.get("phases") if isinstance(report.get("phases"), dict) else {}
    observed_statuses = [*checks.values(), *phases.values()]
    if claimed == "failed" or "failed" in observed_statuses:
        return "failed"
    complete = (
        all(phases.get(phase) == "passed" for phase in required_phases)
        and all(checks.get(check_id) == "passed" for check_id in required_checks)
    )
    if claimed == "passed" and complete:
        return "passed"
    return "blocked"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _exit_code(status: str) -> int:
    return {"passed": 0, "failed": 2, "blocked": 3}[status]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run or conclude the 5X49 Gate A rehearsal")
    subparsers = parser.add_subparsers(dest="command", required=True)
    conclude = subparsers.add_parser("conclude", help="Combine local and Docker evidence")
    conclude.add_argument("--local-report", required=True, type=Path)
    conclude.add_argument("--docker-report", type=Path)
    rehearse = subparsers.add_parser("rehearse", help="Run an isolated local Gate A rehearsal")
    rehearse.add_argument("--input-dir", required=True, type=Path)
    rehearse.add_argument("--run-dir", required=True, type=Path)
    args = parser.parse_args(argv)

    try:
        if args.command == "conclude":
            payload = conclude_reports(args.local_report, args.docker_report)
        elif args.command == "rehearse":
            payload = run_rehearsal(args.input_dir, args.run_dir)
        else:  # pragma: no cover - argparse keeps this unreachable
            parser.error("unsupported command")
    except GateAValidationError as exc:
        print(f"Gate A refused: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True))
    return _exit_code(payload["overall_status"])


if __name__ == "__main__":
    raise SystemExit(main())
