"""Run the isolated Fresh Canonical local stabilization gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence


REPORT_SCHEMA_VERSION = "fresh-canonical-stabilization-report.v1"
BROWSER_SCHEMA_VERSION = "fresh-canonical-stabilization-browser.v1"
VALID_CHECK_STATUSES = frozenset({"passed", "failed", "blocked"})
REQUIRED_BROWSER_CHECKS = (
    "english-desktop",
    "chinese-desktop",
    "english-mobile-375",
    "chinese-mobile-375",
    "library-navigation",
    "film-detail-modal-and-direct",
    "multi-edition-detail",
    "local-artwork-loads",
    "filter-sort-profile-state",
    "management-review-anchors",
    "workflow-status",
    "diary-recent-search-activity-settings",
    "factual-graph",
    "snapshot-preview-restore",
    "no-key-degradation",
    "no-runtime-or-network-errors",
    "no-horizontal-overflow",
    "keyboard-focus-and-live-status",
)
PRIVATE_CANARIES = (
    "sk-stabilization-private-canary",
    "authorization: bearer",
    "thought_chain",
    "chain_of_thought",
)


class StabilizationError(RuntimeError):
    pass


class StabilizationBlocked(StabilizationError):
    pass


def run_rehearsal(run_dir: Path) -> dict[str, Any]:
    run_dir = _validate_new_run_dir(run_dir)
    active_before = _active_database_snapshot()
    commit_sha = _git_sha()
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise StabilizationBlocked("FFmpeg and FFprobe are required for the local gate")

    run_dir.mkdir(parents=True)
    checks: list[dict[str, Any]] = []
    phases: dict[str, str] = {}
    try:
        checks.extend((
            _check("isolated-run-directory", True),
            _check("ffmpeg-available", True),
            _check("active-database-snapshotted", True),
        ))
        phases["preflight"] = _phase_status(checks)

        normal_dir = run_dir / "fixtures" / "normal"
        mixed_dir = run_dir / "fixtures" / "mixed"
        from scripts.generate_test_data import generate_dataset

        normal_manifest = generate_dataset(
            normal_dir,
            count=12,
            seed=549,
            profile="normal",
            video_mode="valid",
        )
        mixed_manifest = generate_dataset(
            mixed_dir,
            count=30,
            seed=550,
            profile="mixed",
            video_mode="valid",
        )
        fixture_hash = _hash_json({"normal": normal_manifest, "mixed": mixed_manifest})
        probe = _probe_video(normal_dir / "media" / "film-0001" / "film.mp4", ffprobe)
        fixture_checks = [
            _check("normal-fixture-count", normal_manifest["count"] == 12),
            _check("mixed-fixture-count", mixed_manifest["count"] == 30),
            _check(
                "mixed-fixture-edge-coverage",
                {item["scenario"] for item in mixed_manifest["media_scenarios"]}
                >= {
                    "missing_nfo",
                    "corrupt_xml",
                    "multiple_videos",
                    "no_video",
                    "temporary_video_only",
                    "root_video",
                },
            ),
            _check("valid-video-probe", probe["video"] and probe["audio"]),
            _check("valid-video-dimensions", probe["width"] == 320 and probe["height"] == 180),
        ]
        checks.extend(fixture_checks)
        phases["fixtures"] = _phase_status(fixture_checks)

        contract_checks = _run_offline_contracts(run_dir)
        checks.extend(contract_checks)
        phases["recorded_external_and_commands"] = _phase_status(contract_checks)

        normal_report = _run_worker(
            run_dir,
            mode="normal",
            database_path=run_dir / "databases" / "normal.db",
            media_dir=normal_dir / "media",
        )
        mixed_report = _run_worker(
            run_dir,
            mode="mixed",
            database_path=run_dir / "databases" / "mixed.db",
            media_dir=mixed_dir / "media",
        )
        dangerous_database = run_dir / "databases" / "dangerous-clear.db"
        dangerous_database.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(run_dir / "databases" / "normal.db", dangerous_database)
        clear_report = _run_worker(
            run_dir,
            mode="clear",
            database_path=dangerous_database,
            media_dir=normal_dir / "media",
        )
        lifecycle_checks = [
            *normal_report["checks"],
            *mixed_report["checks"],
            *clear_report["checks"],
        ]
        checks.extend(lifecycle_checks)
        phases["lifecycle"] = _phase_status(lifecycle_checks)

        privacy_payload = {
            "normal": normal_report,
            "mixed": mixed_report,
            "clear": clear_report,
        }
        privacy_checks = [
            _check("worker-report-privacy", not _privacy_leaks(privacy_payload)),
            _check("legacy-tables-absent", normal_report.get("legacy_tables_absent") is True),
        ]
        checks.extend(privacy_checks)
        phases["privacy"] = _phase_status(privacy_checks)

        active_after = _active_database_snapshot()
        isolation_checks = [
            _check("active-database-unchanged", active_before == active_after),
            _check("generated-artifacts-contained", _artifacts_contained(run_dir)),
        ]
        checks.extend(isolation_checks)
        phases["isolation"] = _phase_status(isolation_checks)

        backend_status = _phase_status(checks)
        report = {
            "schema_version": REPORT_SCHEMA_VERSION,
            "run_id": run_dir.name,
            "commit_sha": commit_sha,
            "fixture_hash": fixture_hash,
            "checks": checks,
            "phases": phases,
            "backend_status": backend_status,
            "browser_status": "blocked",
            "live_external_status": "not_run",
            "docker_status": "not_available" if shutil.which("docker") is None else "not_run",
            "overall_status": "failed" if backend_status == "failed" else "blocked",
        }
        _write_json(run_dir / "run-report.json", report)
        return report
    except Exception:
        active_after = _active_database_snapshot()
        if active_before != active_after:
            raise StabilizationError("Active database changed during failed rehearsal") from None
        raise


def create_browser_template(run_report: Path, output: Path) -> dict[str, Any]:
    report = _read_run_report(run_report)
    output = output.resolve()
    if output != run_report.resolve().parent / "browser-report.json":
        raise StabilizationError("Browser report must stay in its stabilization run directory")
    payload = {
        "schema_version": BROWSER_SCHEMA_VERSION,
        "run_id": report["run_id"],
        "commit_sha": report["commit_sha"],
        "fixture_hash": report["fixture_hash"],
        "checks": [_check(check_id, False, blocked=True) for check_id in REQUIRED_BROWSER_CHECKS],
        "browser_status": "blocked",
    }
    _write_json(output, payload)
    return payload


def conclude(run_report: Path, browser_report: Path) -> dict[str, Any]:
    run = _read_run_report(run_report)
    browser = _read_browser_report(browser_report, run)
    browser_status = _phase_status(browser["checks"])
    backend_status = str(run["backend_status"])
    if "failed" in {backend_status, browser_status}:
        overall = "failed"
    elif backend_status == browser_status == "passed":
        overall = "passed"
    else:
        overall = "blocked"
    payload = {
        **{key: run[key] for key in (
            "schema_version",
            "run_id",
            "commit_sha",
            "fixture_hash",
            "checks",
            "phases",
            "live_external_status",
            "docker_status",
        )},
        "backend_status": backend_status,
        "browser_status": browser_status,
        "overall_status": overall,
    }
    _write_json(run_report.resolve().parent / "conclusion.json", payload)
    return payload


def _run_worker(
    run_dir: Path,
    *,
    mode: str,
    database_path: Path,
    media_dir: Path,
) -> dict[str, Any]:
    output = run_dir / "worker" / f"{mode}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update({
        "PYTHONPATH": str(_backend_root()),
        "SQLITE_DB_PATH": str(database_path.resolve()),
        "MEDIA_DIR": str(media_dir.resolve()),
        "OPERATION_MANIFEST_DIR": str((run_dir / "operation-manifests" / mode).resolve()),
        "WATCH_LIBRARY": "false",
        "TMDB_API_KEY": "",
        "OPENROUTER_API_KEY": "",
    })
    command = [
        sys.executable,
        "-m",
        "app.evaluation.stabilization",
        "_worker",
        "--mode",
        mode,
        "--run-dir",
        str(run_dir.resolve()),
        "--media-dir",
        str(media_dir.resolve()),
        "--output",
        str(output.resolve()),
    ]
    completed = subprocess.run(
        command,
        cwd=run_dir,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    if completed.returncode not in {0, 2}:
        raise StabilizationError(f"{mode} lifecycle worker failed")
    try:
        payload = json.loads(output.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StabilizationError(f"{mode} lifecycle worker did not produce a valid report") from exc
    if _privacy_leaks(payload):
        raise StabilizationError(f"{mode} lifecycle worker report failed privacy validation")
    return payload


def _run_offline_contracts(run_dir: Path) -> list[dict[str, str]]:
    """Exercise recorded/fake transports and command semantics without public network access."""
    temporary = run_dir / "temp" / "offline-contracts"
    temporary.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update({
        "PYTHONPATH": str(_backend_root()),
        "SQLITE_DB_PATH": str((run_dir / "databases" / "offline-contracts.db").resolve()),
        "MEDIA_DIR": str((run_dir / "fixtures" / "normal" / "media").resolve()),
        "OPERATION_MANIFEST_DIR": str((run_dir / "operation-manifests" / "contracts").resolve()),
        "TMP": str(temporary.resolve()),
        "TEMP": str(temporary.resolve()),
        "TMDB_API_KEY": "",
        "OPENROUTER_API_KEY": "",
        "NO_PROXY": "*",
        "HTTP_PROXY": "",
        "HTTPS_PROXY": "",
    })
    groups = {
        "recorded-tmdb-and-safe-failures": (
            "test_tmdb_client",
            "test_metadata_scraper.MetadataScraperIntegrationTests.test_scrape_film_writes_canonical_metadata_assertions_and_bounded_event",
            "test_metadata_scraper.MetadataScraperIntegrationTests.test_candidate_lookup_is_bounded_and_does_not_mutate_library_state",
            "test_metadata_scraper.MetadataScraperIntegrationTests.test_artwork_selection_updates_canonical_edition",
        ),
        "deterministic-analysis-persistence": (
            "test_analysis_runtime.AnalysisRuntimeTests.test_runtime_persists_structured_view_and_reuses_successful_run",
            "test_analysis_runtime.AnalysisRuntimeTests.test_user_rejection_survives_a_new_model_run",
            "test_analysis_runtime.AnalysisRuntimeTests.test_policy_critic_rejects_identity_conflict_before_evidence_or_assertion_write",
        ),
        "workflow-retry-cancel-and-snapshots": (
            "test_canonical_runtime.FreshCanonicalRuntimeTests.test_manual_unwatch_does_not_remove_other_viewing_sources",
            "test_workflows.WorkflowRuntimeTests.test_failure_retry_resumes_at_failed_step_and_preserves_completed_steps",
            "test_workflows.WorkflowRuntimeTests.test_queued_cancel_is_terminal_without_running_job",
            "test_workflows.WorkflowRuntimeTests.test_safe_domain_failure_reaches_the_public_workflow_view",
            "test_event_sourced_commands.CanonicalCommandEventTests.test_snapshot_restore_rejects_state_drift_and_is_single_use",
            "test_event_sourced_commands.CanonicalCommandEventTests.test_file_organization_restore_uses_only_a_controlled_manifest_reference",
        ),
        "projection-and-external-score-contracts": (
            "test_projections.ProjectionTests.test_projection_failure_rolls_back_domain_write",
            "test_external_scores.ExternalScoresTests.test_refresh_film_writes_normalized_score_state_and_bounded_event",
        ),
    }
    results: list[dict[str, str]] = []
    isolated_test_runner = (
        "import os,sys,unittest;"
        "suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(name) for name in sys.argv[1:]);"
        "sink=open(os.devnull,'w');"
        "result=unittest.TextTestRunner(stream=sink).run(suite);"
        "sink.flush();"
        "os._exit(0 if result.wasSuccessful() else 1)"
    )
    for check_id, cases in groups.items():
        passed = True
        for case in cases:
            try:
                completed = subprocess.run(
                    [sys.executable, "-c", isolated_test_runner, case],
                    cwd=run_dir,
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=90,
                )
                if completed.returncode != 0:
                    passed = False
                    break
            except subprocess.TimeoutExpired:
                passed = False
                break
        results.append(_check(check_id, passed))
    return results


def _worker(mode: str, run_dir: Path, media_dir: Path, output: Path) -> dict[str, Any]:
    os.chdir(run_dir.resolve())
    from sqlalchemy import text
    from sqlmodel import Session, select

    from app.canonical_models import OperationSnapshot, ProjectionState, Setting
    from app.database import create_db_and_tables, engine
    from app.services.library import library_manager
    from app.services.library_sync import library_sync_service
    from app.services.operation_snapshots import OperationConflict, operation_snapshot_service
    from app.services.projections import ProjectionUnavailable, projection_coordinator
    from app.services.user_state import film_profile_state_manager

    create_db_and_tables()
    checks: list[dict[str, Any]] = []
    with Session(engine) as session:
        epoch = session.exec(text("SELECT epoch FROM schema_metadata WHERE id = 1")).one()[0]
        tables = {
            row[0]
            for row in session.exec(text("SELECT name FROM sqlite_master WHERE type='table'")).all()
        }
        predicate_count = int(session.exec(text("SELECT COUNT(*) FROM assertion_predicate")).one()[0])
        genre_count = int(session.exec(text("SELECT COUNT(*) FROM concept WHERE kind='genre'")).one()[0])
    first_startup_signature = _fresh_baseline_signature(engine)
    create_db_and_tables()
    second_startup_signature = _fresh_baseline_signature(engine)
    legacy_tables = {"movie", "movie_user_state", "legacy_movie_alias", "canonical_backfill_run"}
    checks.extend((
        _check(f"{mode}-fresh-epoch", epoch == "fresh-canonical-v1"),
        _check(f"{mode}-schema-version", _schema_version(engine) == 4),
        _check(f"{mode}-predicate-reference-rows", predicate_count == 9),
        _check(f"{mode}-genre-reference-rows", genre_count == 19),
        _check(f"{mode}-legacy-tables-absent", not (tables & legacy_tables)),
        _check(f"{mode}-second-startup-idempotent", first_startup_signature == second_startup_signature),
    ))

    if mode == "clear":
        before = _domain_counts(engine)
        with Session(engine) as session:
            session.add(Setting(key="stabilization_marker", value="preserve", updated_at="2026-08-28T00:00:00+00:00"))
            session.commit()
        library_manager.clear_all_data()
        after = _domain_counts(engine)
        with Session(engine) as session:
            setting_preserved = session.get(Setting, "stabilization_marker") is not None
            predicate_preserved = int(session.exec(text("SELECT COUNT(*) FROM assertion_predicate")).one()[0]) == 9
            journal_preserved = _schema_version(engine) == 4
        checks.extend((
            _check("clear-copy-had-domain-data", before["film"] > 0),
            _check("clear-copy-domain-empty", all(after[name] == 0 for name in after)),
            _check("clear-copy-settings-preserved", setting_preserved),
            _check("clear-copy-predicates-preserved", predicate_preserved),
            _check("clear-copy-journal-preserved", journal_preserved),
        ))
        payload = {"checks": checks, "legacy_tables_absent": not (tables & legacy_tables)}
        _write_json(output, payload)
        return payload

    empty_projection = projection_coordinator.bootstrap(engine)
    checks.append(_check(f"{mode}-empty-projection-ready", empty_projection["status"] == "passed"))
    first = library_sync_service.reconcile(str(media_dir))
    first_counts = _domain_counts(engine)
    first_identity_counts = _stable_domain_counts(first_counts)
    first_projection = _projection_snapshot(projection_coordinator.verify_session, engine)
    second = library_sync_service.reconcile(str(media_dir))
    second_counts = _domain_counts(engine)
    second_identity_counts = _stable_domain_counts(second_counts)
    second_projection = _projection_snapshot(projection_coordinator.verify_session, engine)
    checks.extend((
        _check(f"{mode}-scan-found-media", first["scanned"] > 0),
        _check(
            f"{mode}-repeat-domain-idempotent",
            first_identity_counts == second_identity_counts,
        ),
        _check(
            f"{mode}-repeat-projection-rows-idempotent",
            {
                name: value["row_count"]
                for name, value in first_projection.items()
            }
            == {
                name: value["row_count"]
                for name, value in second_projection.items()
            },
        ),
        _check(f"{mode}-repeat-adds-no-items", second["added"] == 0),
    ))

    if mode == "mixed":
        from app.services.metadata.organizer import root_video_organizer

        recent_root_video = media_dir / (
            "这是一个用于验证移动端长文件名换行行为的近期根目录电影文件 (2024).mp4"
        )
        shutil.copy2(media_dir / "film-0001" / "film.mp4", recent_root_video)
        os.utime(recent_root_video, None)
        root_videos = root_video_organizer.list_root_videos(str(media_dir))
        checks.extend((
            _check("mixed-valid-observations-present", first_counts["film"] >= 24),
            _check("mixed-root-videos-discovered", len(root_videos) == 2),
            _check(
                "mixed-root-stability-states",
                {item["status"] for item in root_videos}
                == {"needs_organize", "waiting_for_stability"},
            ),
        ))
        payload = {"checks": checks, "legacy_tables_absent": not (tables & legacy_tables)}
        _write_json(output, payload)
        return payload

    films = library_manager.list_films()
    checks.append(_check("normal-film-count", len(films) == 12))
    source_edition = media_dir / "film-0001"
    source_context = next(
        context
        for context in library_manager.list_operation_contexts()
        if Path(str(context["media_path"])).resolve().parent == source_edition.resolve()
    )
    first_film_id = source_context["film_id"]
    first_item_id = source_context["library_item_id"]
    state = film_profile_state_manager.upsert(
        first_film_id,
        watched=True,
        watched_at="2026-08-28T12:00:00+00:00",
        rating=4,
        favorite=True,
        notes="stabilization-note",
        fields_set={"watched", "watched_at", "rating", "favorite", "notes"},
    )
    checks.append(_check(
        "profile-state-roundtrip",
        bool(state and state["watched"] and state["favorite"] and state["rating"] == 4),
    ))

    ignored = library_manager.ignore_item(first_item_id)
    with Session(engine) as session:
        snapshot = session.exec(
            select(OperationSnapshot)
            .where(OperationSnapshot.aggregate_id == first_item_id)
            .order_by(OperationSnapshot.created_at.desc())
        ).first()
    preview = operation_snapshot_service.preview(snapshot.id) if snapshot else None
    restored_once = False
    restore_rejected = False
    if preview and preview.get("confirmation_token"):
        operation_snapshot_service.restore(snapshot.id, preview["confirmation_token"])
        restored_once = True
        try:
            operation_snapshot_service.restore(snapshot.id, preview["confirmation_token"])
        except OperationConflict:
            restore_rejected = True
    checks.extend((
        _check("availability-ignore-created-snapshot", bool(ignored and snapshot)),
        _check("availability-snapshot-preview", bool(preview and preview["current_matches_after"])),
        _check("availability-snapshot-restored-once", restored_once),
        _check("availability-snapshot-single-use", restore_rejected),
    ))

    second_edition = media_dir / "film-0013-second-edition"
    shutil.copytree(source_edition, second_edition)
    with (second_edition / "film.mp4").open("ab") as handle:
        handle.write(b"\n5X49_SECOND_EDITION\n")
    library_sync_service.reconcile(str(media_dir))
    films_after_edition = library_manager.list_films()
    detail = library_manager.get_film(first_film_id)
    checks.extend((
        _check("multi-edition-single-film", len(films_after_edition) == 12),
        _check("multi-edition-two-items", bool(detail and len(detail["editions"]) == 2)),
    ))

    rename_folder = media_dir / "film-0003"
    rename_context = next(
        context
        for context in library_manager.list_operation_contexts()
        if Path(str(context["media_path"])).resolve().parent == rename_folder.resolve()
    )
    rename_film_id = rename_context["film_id"]
    rename_item_id = rename_context["library_item_id"]
    film_profile_state_manager.upsert(
        rename_film_id,
        favorite=True,
        fields_set={"favorite"},
    )
    renamed_folder = media_dir / "film-0003-renamed"
    rename_folder.replace(renamed_folder)
    (renamed_folder / "film.mp4").replace(renamed_folder / "renamed-film.mp4")
    library_sync_service.reconcile(str(media_dir))
    renamed_context = next(
        context
        for context in library_manager.list_operation_contexts()
        if Path(str(context["media_path"])).resolve().parent == renamed_folder.resolve()
    )
    renamed_detail = library_manager.get_film(rename_film_id)
    checks.extend((
        _check("rename-preserves-film", renamed_context["film_id"] == rename_film_id),
        _check("rename-relinks-library-item", renamed_context["library_item_id"] == rename_item_id),
        _check(
            "rename-preserves-profile-state",
            bool(renamed_detail and renamed_detail["profile_state"]["favorite"]),
        ),
    ))

    missing_folder = media_dir / "film-0002"
    holding = run_dir / "holding-film-0002"
    target_context = next(
        context
        for context in library_manager.list_operation_contexts()
        if Path(str(context["media_path"])).resolve().parent == missing_folder.resolve()
    )
    target_film_id = target_context["film_id"]
    missing_folder.replace(holding)
    library_sync_service.reconcile(str(media_dir))
    missing_detail = library_manager.get_film(target_film_id)
    holding.replace(missing_folder)
    library_sync_service.reconcile(str(media_dir))
    restored_detail = library_manager.get_film(target_film_id)
    checks.extend((
        _check(
            "missing-state-recorded",
            bool(missing_detail and missing_detail["primary_item"]["status"] == "missing"),
        ),
        _check(
            "missing-state-restored",
            bool(restored_detail and restored_detail["primary_item"]["status"] == "available"),
        ),
    ))

    before_rebuild = _projection_digest(projection_coordinator.verify_session, engine)
    with Session(engine) as session:
        projection_coordinator.rebuild_all(session)
        session.commit()
    after_rebuild = _projection_digest(projection_coordinator.verify_session, engine)
    checks.append(_check("projection-rebuild-digest-equal", before_rebuild == after_rebuild))

    with Session(engine) as session:
        state_row = session.get(ProjectionState, "library")
        state_row.projection_version = "stale.v0"
        session.add(state_row)
        session.commit()
    stale_rejected = False
    try:
        library_manager.list_films()
    except ProjectionUnavailable:
        stale_rejected = True
    projection_coordinator.bootstrap(engine)
    checks.extend((
        _check("stale-projection-rejected", stale_rejected),
        _check("stale-projection-recovered", projection_coordinator.bootstrap(engine)["status"] == "passed"),
    ))

    payload = {"checks": checks, "legacy_tables_absent": not (tables & legacy_tables)}
    _write_json(output, payload)
    return payload


def _domain_counts(engine) -> dict[str, int]:
    from sqlalchemy import text
    from sqlmodel import Session

    names = (
        "film",
        "library_item",
        "media_asset",
        "film_title",
        "film_country",
        "credit",
        "film_profile_state",
        "viewing",
        "assertion",
        "analysis_run",
        "operation_snapshot",
        "workflow_run",
        "workflow_step",
        "events",
        "library_film_read_model",
        "film_detail_read_model",
        "film_search_read_model",
        "graph_node_read_model",
        "graph_edge_read_model",
    )
    with Session(engine) as session:
        return {
            name: int(session.exec(text(f"SELECT COUNT(*) FROM {name}")).one()[0])
            for name in names
        }


def _stable_domain_counts(counts: Mapping[str, int]) -> dict[str, int]:
    """Return rows whose counts must not change during an idempotent reconcile."""
    excluded = {
        "events",
        "operation_snapshot",
        "workflow_run",
        "workflow_step",
    }
    return {name: value for name, value in counts.items() if name not in excluded}


def _fresh_baseline_signature(engine) -> str:
    from sqlalchemy import text
    from sqlmodel import Session

    with Session(engine) as session:
        tables = sorted(
            str(row[0])
            for row in session.exec(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
            ).all()
        )
        projection_rows = [
            tuple(row)
            for row in session.exec(
                text(
                    "SELECT name, projection_version, status, row_count, digest "
                    "FROM projection_state ORDER BY name"
                )
            ).all()
        ]
        reference_counts = {
            "predicates": int(session.exec(text("SELECT COUNT(*) FROM assertion_predicate")).one()[0]),
            "genres": int(session.exec(text("SELECT COUNT(*) FROM concept WHERE kind='genre'")).one()[0]),
        }
    return _hash_json({
        "tables": tables,
        "projection_rows": projection_rows,
        "reference_counts": reference_counts,
    })


def _schema_version(engine) -> int:
    from sqlalchemy import text
    from sqlmodel import Session

    with Session(engine) as session:
        value = session.exec(
            text("SELECT COALESCE(MAX(version), 0) FROM schema_migrations WHERE status='applied'")
        ).one()[0]
    return int(value)


def _projection_digest(verifier, engine) -> dict[str, str]:
    from sqlmodel import Session

    with Session(engine) as session:
        report = verifier(session)
    return {name: value["digest"] for name, value in report["checks"].items()}


def _projection_snapshot(verifier, engine) -> dict[str, dict[str, Any]]:
    from sqlmodel import Session

    with Session(engine) as session:
        report = verifier(session)
    return {
        name: {
            "digest": value["digest"],
            "row_count": value["row_count"],
            "version": value["version"],
        }
        for name, value in report["checks"].items()
    }


def _probe_video(path: Path, ffprobe: str) -> dict[str, Any]:
    completed = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "stream=codec_type,width,height",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    streams = json.loads(completed.stdout).get("streams") or []
    video = next((item for item in streams if item.get("codec_type") == "video"), {})
    return {
        "video": bool(video),
        "audio": any(item.get("codec_type") == "audio" for item in streams),
        "width": video.get("width"),
        "height": video.get("height"),
    }


def _validate_new_run_dir(value: Path) -> Path:
    raw = value if value.is_absolute() else _backend_root() / value
    run_dir = raw.resolve()
    runs_root = (_backend_root() / "data" / "stabilization" / "runs").resolve()
    runs_root.mkdir(parents=True, exist_ok=True)
    if run_dir.parent != runs_root:
        raise StabilizationError("Stabilization run directory is outside the isolated runs root")
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,80}", run_dir.name):
        raise StabilizationError("Stabilization run ID is invalid")
    if run_dir.exists():
        raise StabilizationError("Stabilization run directory already exists")
    active = (_backend_root() / "data" / "library.db").resolve()
    if run_dir == active or active.is_relative_to(run_dir):
        raise StabilizationError("Stabilization run directory overlaps the active database")
    return run_dir


def _active_database_snapshot() -> dict[str, dict[str, Any]]:
    active = (_backend_root() / "data" / "library.db").resolve()
    return {
        suffix or "database": _file_snapshot(Path(f"{active}{suffix}"))
        for suffix in ("", "-wal", "-shm")
    }


def _file_snapshot(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"exists": False}
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return {"exists": True, "size": path.stat().st_size, "sha256": digest.hexdigest()}


def _artifacts_contained(run_dir: Path) -> bool:
    allowed = run_dir.resolve()
    return all(path.resolve().is_relative_to(allowed) for path in run_dir.rglob("*"))


def _privacy_leaks(payload: Any) -> list[str]:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).casefold()
    path_scan = serialized.replace("\\\\", "\\")
    leaks = [canary for canary in PRIVATE_CANARIES if canary.casefold() in serialized]
    leaks.extend(
        pattern
        for pattern in (r"[a-z]:\\(?:users|home)\\", r"/(?:home|users)/[^/]+/")
        if re.search(pattern, path_scan)
    )
    return sorted(set(leaks))


def _read_run_report(path: Path) -> dict[str, Any]:
    path = path.resolve()
    runs_root = (_backend_root() / "data" / "stabilization" / "runs").resolve()
    if path.name != "run-report.json" or path.parent.parent != runs_root:
        raise StabilizationError("Run report is outside the isolated runs root")
    payload = _read_json(path)
    required = (
        "run_id",
        "commit_sha",
        "fixture_hash",
        "checks",
        "phases",
        "backend_status",
        "browser_status",
        "live_external_status",
        "docker_status",
        "overall_status",
    )
    if payload.get("schema_version") != REPORT_SCHEMA_VERSION or any(key not in payload for key in required):
        raise StabilizationError("Run report schema is invalid")
    if payload["run_id"] != path.parent.name:
        raise StabilizationError("Run report ID does not match its directory")
    return payload


def _read_browser_report(path: Path, run: Mapping[str, Any]) -> dict[str, Any]:
    path = path.resolve()
    if path != (_backend_root() / "data" / "stabilization" / "runs" / run["run_id"] / "browser-report.json").resolve():
        raise StabilizationError("Browser report is outside the stabilization run directory")
    payload = _read_json(path)
    if payload.get("schema_version") != BROWSER_SCHEMA_VERSION:
        raise StabilizationError("Browser report schema is invalid")
    if any(payload.get(key) != run[key] for key in ("run_id", "commit_sha", "fixture_hash")):
        raise StabilizationError("Browser report does not match the rehearsal")
    checks = payload.get("checks")
    if not isinstance(checks, list):
        raise StabilizationError("Browser report checks are invalid")
    ids = [item.get("id") for item in checks if isinstance(item, dict)]
    statuses = [item.get("status") for item in checks if isinstance(item, dict)]
    if tuple(ids) != REQUIRED_BROWSER_CHECKS or any(status not in VALID_CHECK_STATUSES for status in statuses):
        raise StabilizationError("Browser report does not contain the required checks")
    return payload


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StabilizationError("Stabilization report is invalid JSON") from exc
    if not isinstance(payload, dict):
        raise StabilizationError("Stabilization report must be an object")
    return payload


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _hash_json(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _git_sha() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=_backend_root().parent,
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return completed.stdout.strip()


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _check(check_id: str, passed: bool, *, blocked: bool = False) -> dict[str, str]:
    return {"id": check_id, "status": "blocked" if blocked else "passed" if passed else "failed"}


def _phase_status(checks: Sequence[Mapping[str, Any]]) -> str:
    statuses = {str(check.get("status")) for check in checks}
    if "failed" in statuses:
        return "failed"
    if "blocked" in statuses:
        return "blocked"
    return "passed"


def _exit_code(status: str) -> int:
    return {"passed": 0, "failed": 2, "blocked": 3}.get(status, 2)


def _summary(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: payload[key]
        for key in (
            "schema_version",
            "run_id",
            "commit_sha",
            "fixture_hash",
            "backend_status",
            "browser_status",
            "live_external_status",
            "docker_status",
            "overall_status",
        )
        if key in payload
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    rehearse = subparsers.add_parser("rehearse")
    rehearse.add_argument("--run-dir", required=True, type=Path)
    browser = subparsers.add_parser("browser-template")
    browser.add_argument("--run-report", required=True, type=Path)
    browser.add_argument("--output", required=True, type=Path)
    conclusion = subparsers.add_parser("conclude")
    conclusion.add_argument("--run-report", required=True, type=Path)
    conclusion.add_argument("--browser-report", required=True, type=Path)
    worker = subparsers.add_parser("_worker", help=argparse.SUPPRESS)
    worker.add_argument("--mode", required=True, choices=("normal", "mixed", "clear"))
    worker.add_argument("--run-dir", required=True, type=Path)
    worker.add_argument("--media-dir", required=True, type=Path)
    worker.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)

    try:
        if args.command == "rehearse":
            payload = run_rehearsal(args.run_dir)
        elif args.command == "browser-template":
            payload = create_browser_template(args.run_report, args.output)
        elif args.command == "conclude":
            payload = conclude(args.run_report, args.browser_report)
        else:
            payload = _worker(args.mode, args.run_dir, args.media_dir, args.output)
    except StabilizationBlocked as exc:
        print(f"Stabilization blocked: {exc}", file=sys.stderr)
        return 3
    except StabilizationError as exc:
        print(f"Stabilization refused: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(_summary(payload), ensure_ascii=True, indent=2, sort_keys=True))
    status = str(payload.get("overall_status") or payload.get("browser_status") or _phase_status(payload["checks"]))
    return _exit_code(status)


if __name__ == "__main__":
    raise SystemExit(main())
