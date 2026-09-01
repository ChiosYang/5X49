"""Run the isolated Factual Explore engineering quality evaluation."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Sequence


REPORT_SCHEMA_VERSION = "factual-explore-evaluation.v1"
SUMMARY_SCHEMA_VERSION = "factual-explore-summary.v1"
DEFAULT_SEED = 549
DEFAULT_COUNT = 200
DEFAULT_SCALE_COUNT = 1000
DIMENSIONS = ("genre", "person", "country", "decade")
NOW = "2026-09-01T00:00:00+00:00"
RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
FORBIDDEN_PUBLIC_TEXT = (
    "absolute_path",
    "authorization",
    "bearer ",
    "media_path",
    "origin_ref",
    "private-canary",
    "source_ref",
    "token",
)


class FactualExploreEvaluationError(RuntimeError):
    """Raised when an evaluation cannot be run safely."""


def run_evaluation(
    *,
    run_id: str,
    seed: int = DEFAULT_SEED,
    count: int = DEFAULT_COUNT,
    scale_count: int = DEFAULT_SCALE_COUNT,
    output_root: Path | None = None,
) -> dict[str, Any]:
    """Run behavior and scale workers against isolated disposable databases."""

    _validate_options(run_id, count, scale_count)
    root = (output_root or _default_output_root()).resolve()
    run_dir = (root / run_id).resolve()
    if run_dir.parent != root:
        raise FactualExploreEvaluationError("Run directory must stay inside the evaluation root")
    if run_dir.exists():
        raise FactualExploreEvaluationError("Evaluation run already exists")
    run_dir.mkdir(parents=True)

    behavior = _run_worker(run_dir, "behavior", seed=seed, count=count)
    scale = _run_worker(run_dir, "scale", seed=seed + 1, count=scale_count)
    checks = [*behavior["checks"], *scale["checks"]]
    status = "passed" if all(item["status"] == "passed" for item in checks) else "failed"
    report = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "summary_schema_version": SUMMARY_SCHEMA_VERSION,
        "run_id": run_id,
        "commit_sha": _git_sha(),
        "seed": seed,
        "count": count,
        "scale_count": scale_count,
        "fixture_contract_hash": _fixture_contract_hash(seed, count, scale_count),
        "dimensions": list(DIMENSIONS),
        "status": status,
        "behavior": behavior,
        "scale": scale,
        "checks": checks,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    _assert_report_privacy(report, run_dir)
    (run_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (run_dir / "summary.md").write_text(render_git_safe_summary(report), encoding="utf-8")
    return report


def render_git_safe_summary(report: dict[str, Any]) -> str:
    """Render aggregate-only Markdown suitable for a tracked quality summary."""

    behavior = report["behavior"]
    scale = report["scale"]
    coverage = behavior["coverage"]
    lines = [
        "# Factual Explore engineering quality summary",
        "",
        f"- Contract: `{report['schema_version']}`",
        f"- Run ID: `{report['run_id']}`",
        f"- Commit: `{report['commit_sha']}`",
        f"- Fixture seed: `{report['seed']}`",
        f"- Behavior fixture size: `{report['count']}`",
        f"- Scale fixture size: `{report['scale_count']}`",
        f"- Fixture contract hash: `{report['fixture_contract_hash']}`",
        f"- Result: **{report['status'].title()}**",
        "- Evidence class: deterministic engineering fixture; not real-library or Alpha-user evidence",
        "",
        "| Dimension | Total | Covered | Conflicted | Missing |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for dimension in DIMENSIONS:
        item = coverage[dimension]
        lines.append(
            f"| {dimension.title()} | {item['total_films']} | {item['covered_films']} | "
            f"{item['conflicted_films']} | {item['missing_films']} |"
        )
    lines.extend(
        (
            "",
            "| Engineering check | Result |",
            "| --- | --- |",
        )
    )
    for item in report["checks"]:
        lines.append(f"| `{item['id']}` | {item['status'].title()} |")
    lines.extend(
        (
            "",
            "## Scale observations",
            "",
            f"- Context SQL statements: `{scale['context_statement_count']}` (hard maximum: `10`).",
            f"- Overview duration: `{scale['durations_ms']['overview']}` ms.",
            f"- Context duration: `{scale['durations_ms']['context']}` ms.",
            f"- Film query duration: `{scale['durations_ms']['films']}` ms.",
            "- Durations are informational and are not cross-machine release gates.",
            "",
            "## Product evidence still required",
            "",
            "- Representative real-library coverage and correctness sampling.",
            "- External Alpha comprehension and task-completion evidence.",
            "- Repeat-use and retention evidence in the W10/W13-W14 product gates.",
            "",
        )
    )
    summary = "\n".join(lines)
    _assert_text_privacy(summary)
    return summary


def _run_worker(run_dir: Path, mode: str, *, seed: int, count: int) -> dict[str, Any]:
    worker_dir = run_dir / mode
    worker_dir.mkdir()
    output_path = worker_dir / "worker-report.json"
    database_path = worker_dir / "library.db"
    environment = os.environ.copy()
    environment.update(
        {
            "SQLITE_DB_PATH": str(database_path),
            "MEDIA_DIR": str(worker_dir / "media"),
            "OPENROUTER_API_KEY": "",
            "TMDB_API_KEY": "",
        }
    )
    command = [
        sys.executable,
        "-m",
        "app.evaluation.factual_explore",
        "--worker-mode",
        mode,
        "--worker-dir",
        str(worker_dir),
        "--worker-output",
        str(output_path),
        "--seed",
        str(seed),
        "--count",
        str(count),
        "--scale-count",
        str(count),
    ]
    result = subprocess.run(
        command,
        cwd=Path(__file__).resolve().parents[2],
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
        check=False,
    )
    if result.returncode != 0 or not output_path.is_file():
        (worker_dir / "worker-diagnostic.log").write_text(
            f"stdout:\n{result.stdout}\n\nstderr:\n{result.stderr}",
            encoding="utf-8",
        )
        raise FactualExploreEvaluationError(
            f"{mode} worker failed with exit code {result.returncode}"
        )
    return json.loads(output_path.read_text(encoding="utf-8"))


def _worker(mode: str, worker_dir: Path, output_path: Path, *, seed: int, count: int) -> int:
    if mode not in {"behavior", "scale"}:
        raise FactualExploreEvaluationError("Unknown worker mode")
    worker_dir = worker_dir.resolve()
    output_path = output_path.resolve()
    if output_path.parent != worker_dir:
        raise FactualExploreEvaluationError("Worker output must stay inside its worker directory")

    from sqlalchemy import event as sqlalchemy_event
    from sqlmodel import Session, select

    from app.canonical_models import ExploreFacetReadModel, ExploreFilmReadModel
    from app.database import create_db_and_tables, engine
    from app.services.explore_query import explore_query_service
    from app.services.projections import projection_coordinator

    create_db_and_tables()
    expected = (
        _seed_fixture(engine, worker_dir / "media", seed=seed, count=count)
        if mode == "behavior"
        else _seed_scale_fixture(engine, seed=seed, count=count)
    )

    timings: dict[str, float] = {}
    overview, timings["overview"] = _timed(explore_query_service.overview)
    empty_filters = {dimension: [] for dimension in DIMENSIONS}
    statements: list[bool] = []

    def count_statement(*_args):
        statements.append(True)

    sqlalchemy_event.listen(engine, "before_cursor_execute", count_statement)
    try:
        context, timings["context"] = _timed(
            explore_query_service.context,
            filters=empty_filters,
            view="all",
            limit=6,
        )
    finally:
        sqlalchemy_event.remove(engine, "before_cursor_execute", count_statement)
    films, timings["films"] = _timed(
        explore_query_service.list_films,
        filters=empty_filters,
        view="all",
        sort="title",
        direction="asc",
        limit=40,
        offset=0,
    )

    dimensions = {item["dimension"]: item for item in overview["dimensions"]}
    coverage = {dimension: dimensions[dimension]["coverage"] for dimension in DIMENSIONS}
    checks: list[dict[str, str]] = []
    checks.append(_check(f"{mode}-four-dimensions", set(dimensions) == set(DIMENSIONS)))
    for dimension in DIMENSIONS:
        item = coverage[dimension]
        partitioned = item["covered_films"] + item["conflicted_films"] + item["missing_films"]
        checks.append(_check(f"{mode}-{dimension}-coverage-partition", partitioned == item["total_films"]))
        checks.append(_check(f"{mode}-{dimension}-expected-coverage", item == expected["coverage"][dimension]))

    semantic_checks = _strict_semantic_checks(engine, expected, prefix=mode)
    checks.extend(semantic_checks)
    checks.append(_check(f"{mode}-context-statement-bound", len(statements) <= 10))
    checks.append(_check(f"{mode}-first-page-bounded", len(films["items"]) == min(40, count)))
    checks.append(_check(f"{mode}-context-total", context["current_total"] == count))

    with Session(engine) as session:
        before = projection_coordinator.verify_session(session)
        if mode == "behavior":
            rebuilt = projection_coordinator.rebuild_all(session)
            session.commit()
            after = projection_coordinator.verify_session(session)
            stable_names = ("explore_films", "explore_facets")
            stable = all(
                before["checks"][name]["digest"]
                == rebuilt["checks"][name]["digest"]
                == after["checks"][name]["digest"]
                for name in stable_names
            )
            checks.append(_check("behavior-projection-rebuild-stable", stable))
        else:
            checks.append(_check("scale-projection-state-verified", before["status"] == "passed"))
        facet_rows = session.exec(select(ExploreFacetReadModel)).all()
        film_rows = session.exec(select(ExploreFilmReadModel)).all()

    public_payload = {"overview": overview, "context": context, "films": films}
    serialized = json.dumps(public_payload, ensure_ascii=False, sort_keys=True).casefold()
    checks.append(
        _check(
            f"{mode}-public-payload-private-free",
            not any(value in serialized for value in FORBIDDEN_PUBLIC_TEXT)
            and str(worker_dir).casefold() not in serialized,
        )
    )
    checks.append(_check(f"{mode}-projection-row-count", len(film_rows) == count and len(facet_rows) > count))

    report = {
        "mode": mode,
        "seed": seed,
        "count": count,
        "status": "passed" if all(item["status"] == "passed" for item in checks) else "failed",
        "coverage": coverage,
        "context_statement_count": len(statements),
        "durations_ms": {key: round(value, 3) for key, value in timings.items()},
        "projection_rows": {"films": len(film_rows), "facets": len(facet_rows)},
        "checks": checks,
    }
    _assert_report_privacy(report, worker_dir)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    engine.dispose()
    return 0 if report["status"] == "passed" else 1


def _seed_fixture(engine, media_root: Path, *, seed: int, count: int) -> dict[str, Any]:
    import hashlib as _hashlib

    from sqlmodel import Session, select

    from app.canonical_models import (
        Assertion,
        AssertionProvenance,
        Concept,
        Credit,
        CreditProvenance,
        Film,
        FilmCountry,
        FilmCountryProvenance,
        GraphEntity,
        LocalProfile,
        Person,
        Viewing,
    )
    from app.contracts.analysis_persistence import assertion_qualifier_hash, assertion_semantic_key
    from app.contracts.structured_metadata import credit_semantic_key, normalize_metadata_text
    from app.services.library import library_manager

    media_root.mkdir(parents=True)
    observations: list[dict[str, Any]] = []
    titles: list[str] = []
    missing_indexes = {index for index in range(count) if index % 20 == 0}
    conflict_indexes = {index for index in range(count) if index % 20 == 1}
    for index in range(count):
        title = f"W7 Fixture {seed:04d}-{index + 1:04d}"
        titles.append(title)
        folder = media_root / f"film-{index + 1:04d}"
        folder.mkdir()
        video = folder / "film.mkv"
        video.write_bytes(f"W7-{seed}-{index}".encode("ascii"))
        release_year = None if index in missing_indexes else 1950 + ((index * 7 + seed) % 76)
        observations.append(
            {
                "title": title,
                "original_title": title,
                "year": release_year,
                "media_path": str(video.resolve()),
                "video_file": video.name,
                "folder_path": str(folder.resolve()),
                "folder_name": folder.name,
                "file_size": video.stat().st_size,
                "file_mtime": video.stat().st_mtime,
                "library_status": "available",
                "metadata_source": "filename",
                "scrape_status": "pending",
                "last_seen_at": NOW,
                "source_item_key": f"w7-evaluation-{seed}-{index}",
            }
        )
    created = library_manager.add_observations(observations)
    if created != count:
        raise FactualExploreEvaluationError("Fixture did not create the expected Film count")

    with Session(engine) as session:
        films = session.exec(select(Film).where(Film.canonical_title.in_(titles))).all()
        film_by_title = {film.canonical_title: film for film in films}
        if len(film_by_title) != count:
            raise FactualExploreEvaluationError("Fixture Film identity count is not deterministic")
        concepts = {
            concept.canonical_name: concept
            for concept in session.exec(
                select(Concept).where(Concept.canonical_name.in_(("Action", "Drama")))
            ).all()
        }
        if set(concepts) != {"Action", "Drama"}:
            raise FactualExploreEvaluationError("Required seeded Genre vocabulary is missing")
        profile_id = session.exec(select(LocalProfile.id)).one()
        countries = ("US", "CN", "FR", "JP", "BR", "DE", "GB")

        for index in range(count):
            if index in missing_indexes:
                continue
            person_id = f"person_{_stable_hex(seed, index, 'person')}"
            session.add(GraphEntity(id=person_id, entity_type="person", lifecycle_status="active"))
            session.add(
                Person(
                    id=person_id,
                    canonical_name=f"Fixture Person {index + 1:04d}",
                    normalized_name=normalize_metadata_text(f"Fixture Person {index + 1:04d}"),
                    resolution_status="verified",
                    lifecycle_status="active",
                )
            )
        session.flush()

        for index, title in enumerate(titles):
            film = film_by_title[title]
            suffix = _stable_hex(seed, index, "fixture")
            if index not in missing_indexes:
                person_id = f"person_{_stable_hex(seed, index, 'person')}"
                credit_id = f"credit_{_stable_hex(seed, index, 'credit')}"
                session.add(
                    Credit(
                        id=credit_id,
                        film_id=film.id,
                        person_id=person_id,
                        department="Acting" if index % 2 else "Directing",
                        job="Actor" if index % 2 else "Director",
                        semantic_key=credit_semantic_key(
                            film.id,
                            person_id,
                            "Acting" if index % 2 else "Directing",
                            "Actor" if index % 2 else "Director",
                        ),
                    )
                )
                session.add(
                    CreditProvenance(
                        id=f"cprov_{_stable_hex(seed, index, 'credit-provenance')}",
                        credit_id=credit_id,
                        origin_kind="nfo",
                        origin_ref=f"fixture:{suffix}",
                        observed_at=NOW,
                    )
                )

                concept = concepts["Action" if index % 2 == 0 else "Drama"]
                qualifier_hash = assertion_qualifier_hash({})
                assertion_key = assertion_semantic_key(
                    subject_entity_id=film.id,
                    predicate="HAS_GENRE",
                    object_entity_id=concept.id,
                    qualifier_hash=qualifier_hash,
                )
                assertion_id = f"assert_{_hashlib.sha256(assertion_key.encode()).hexdigest()[:32]}"
                session.add(
                    Assertion(
                        id=assertion_id,
                        subject_entity_id=film.id,
                        object_entity_id=concept.id,
                        predicate="HAS_GENRE",
                        qualifiers={},
                        qualifier_hash=qualifier_hash,
                        assertion_key=assertion_key,
                        source_scope="factual",
                        review_status="accepted",
                        review_method="import_policy",
                        review_policy_version="factual-explore-evaluation.v1",
                        reviewed_at=NOW,
                        first_seen_at=NOW,
                        last_seen_at=NOW,
                    )
                )
                session.add(
                    AssertionProvenance(
                        id=f"aprov_{_stable_hex(seed, index, 'assertion-provenance')}",
                        assertion_id=assertion_id,
                        origin_kind="nfo",
                        origin_scope="factual",
                        origin_ref=f"fixture:{suffix}",
                        source_field="genres",
                        first_observed_at=NOW,
                        last_observed_at=NOW,
                    )
                )

                country_codes = ("XZ", "XQ") if index in conflict_indexes else (countries[index % len(countries)],)
                for country_position, country_code in enumerate(country_codes):
                    country_id = f"fcountry_{_stable_hex(seed, index, f'country-{country_position}')}"
                    session.add(
                        FilmCountry(
                            id=country_id,
                            film_id=film.id,
                            iso_3166_1=country_code,
                        )
                    )
                    session.add(
                        FilmCountryProvenance(
                            id=f"fcprov_{_stable_hex(seed, index, f'country-provenance-{country_position}')}",
                            film_country_id=country_id,
                            origin_kind="nfo",
                            origin_ref=f"fixture:{suffix}:{country_position}",
                            observed_at=NOW,
                        )
                    )
            if index % 3 == 0:
                session.add(
                    Viewing(
                        id=f"view_{_stable_hex(seed, index, 'viewing')}",
                        profile_id=profile_id,
                        film_id=film.id,
                        watched_at="2026-09-01",
                        watched_at_precision="date",
                        source="diary",
                        source_record_id=f"w7-evaluation-{seed}-{index}",
                        review_status="confirmed",
                    )
                )
        target_index = next(
            index
            for index in range(count)
            if index not in missing_indexes and index not in conflict_indexes and index % 3 != 0
        )
        target_film_id = film_by_title[titles[target_index]].id
        session.commit()

    missing_count = len(missing_indexes)
    conflict_count = len(conflict_indexes)
    covered_default = count - missing_count
    return {
        "coverage": {
            "genre": _coverage(count, covered_default, 0, missing_count),
            "person": _coverage(count, covered_default, 0, missing_count),
            "country": _coverage(count, count - missing_count - conflict_count, conflict_count, missing_count),
            "decade": _coverage(count, covered_default, 0, missing_count),
        },
        "target_id": target_film_id,
        "watched_count": sum(1 for index in range(count) if index % 3 == 0),
    }


def _seed_scale_fixture(engine, *, seed: int, count: int) -> dict[str, Any]:
    from sqlmodel import Session

    from app.canonical_models import (
        ExploreFacetReadModel,
        ExploreFilmReadModel,
        Film,
        GraphEntity,
        LibraryFilmReadModel,
    )
    from app.contracts.structured_metadata import normalize_metadata_text
    from app.services.projections import PROJECTION_VERSIONS, projection_coordinator

    missing_indexes = {index for index in range(count) if index % 20 == 0}
    conflict_indexes = {index for index in range(count) if index % 20 == 1}
    countries = ("US", "CN", "FR", "JP", "BR", "DE", "GB")
    target_index = next(
        index
        for index in range(count)
        if index not in missing_indexes and index not in conflict_indexes and index % 3 != 0
    )
    with Session(engine) as session:
        session.info["skip_projection_hook"] = True
        try:
            for index in range(count):
                film_id = f"film_{_stable_hex(seed, index, 'film')}"
                session.add(GraphEntity(id=film_id, entity_type="film", lifecycle_status="active"))
            session.flush()
            for index in range(count):
                film_id = f"film_{_stable_hex(seed, index, 'film')}"
                title = f"W7 Scale {seed:04d}-{index + 1:04d}"
                release_year = None if index in missing_indexes else 1950 + ((index * 7 + seed) % 76)
                watched = index % 3 == 0
                session.add(
                    Film(
                        id=film_id,
                        canonical_title=title,
                        original_title=title,
                        release_year=release_year,
                        lifecycle_status="active",
                    )
                )
            session.flush()
            for index in range(count):
                film_id = f"film_{_stable_hex(seed, index, 'film')}"
                title = f"W7 Scale {seed:04d}-{index + 1:04d}"
                sort_title = normalize_metadata_text(title)
                release_year = None if index in missing_indexes else 1950 + ((index * 7 + seed) % 76)
                watched = index % 3 == 0
                library_payload = {
                    "id": film_id,
                    "title": title,
                    "year": release_year,
                    "poster_path": None,
                    "backdrop_path": None,
                    "profile_state": {"watched": watched},
                    "primary_item": {"status": "available"},
                }
                session.add(
                    LibraryFilmReadModel(
                        film_id=film_id,
                        sort_title=sort_title,
                        release_year=release_year,
                        visible=True,
                        payload=library_payload,
                        source_hash=_canonical_hash(library_payload),
                        projection_version=PROJECTION_VERSIONS["library"],
                    )
                )
                explore_film_source = {
                    "sort_title": sort_title,
                    "release_year": release_year,
                    "watched": watched,
                }
                session.add(
                    ExploreFilmReadModel(
                        film_id=film_id,
                        sort_title=sort_title,
                        release_year=release_year,
                        watched=watched,
                        source_hash=_canonical_hash(explore_film_source),
                        projection_version=PROJECTION_VERSIONS["explore_films"],
                    )
                )
                if index in missing_indexes:
                    continue
                facets = [
                    (
                        "genre",
                        f"con_{_stable_hex(seed, index % 2, 'genre')}",
                        "Action" if index % 2 == 0 else "Drama",
                        True,
                        False,
                        {"source_kind": "nfo", "policy_version": "factual-explore-evaluation.v1"},
                    ),
                    (
                        "person",
                        f"person_{_stable_hex(seed, index, 'person')}",
                        f"Fixture Person {index + 1:04d}",
                        True,
                        False,
                        {
                            "source_kind": "nfo",
                            "policy_version": "factual-explore-evaluation.v1",
                            "roles": ["actor" if index % 2 else "director"],
                        },
                    ),
                    (
                        "decade",
                        str(release_year // 10 * 10),
                        f"{release_year // 10 * 10}s",
                        True,
                        False,
                        {"source_kind": "canonical", "policy_version": "release-year-decade.v1"},
                    ),
                ]
                country_codes = ("XZ", "XQ") if index in conflict_indexes else (countries[index % len(countries)],)
                facets.extend(
                    (
                        "country",
                        country_code,
                        country_code,
                        index not in conflict_indexes,
                        index in conflict_indexes,
                        {"source_kind": "nfo", "policy_version": "factual-explore-evaluation.v1"},
                    )
                    for country_code in country_codes
                )
                for dimension, key, label, eligible, conflicted, payload in facets:
                    source = {
                        "dimension": dimension,
                        "facet_key": key,
                        "film_id": film_id,
                        "display_label": label,
                        "normalized_label": normalize_metadata_text(label),
                        "eligible": eligible,
                        "conflicted": conflicted,
                        "payload": payload,
                    }
                    session.add(
                        ExploreFacetReadModel(
                            **source,
                            source_hash=_canonical_hash(source),
                            projection_version=PROJECTION_VERSIONS["explore_facets"],
                        )
                    )
            session.flush()
            projection_coordinator.refresh_states(session, rebuilt=True)
            session.commit()
        finally:
            session.info.pop("skip_projection_hook", None)

    missing_count = len(missing_indexes)
    conflict_count = len(conflict_indexes)
    covered_default = count - missing_count
    return {
        "coverage": {
            "genre": _coverage(count, covered_default, 0, missing_count),
            "person": _coverage(count, covered_default, 0, missing_count),
            "country": _coverage(count, count - missing_count - conflict_count, conflict_count, missing_count),
            "decade": _coverage(count, covered_default, 0, missing_count),
        },
        "target_id": f"film_{_stable_hex(seed, target_index, 'film')}",
        "watched_count": sum(1 for index in range(count) if index % 3 == 0),
    }


def _strict_semantic_checks(
    engine,
    expected: dict[str, Any],
    *,
    prefix: str,
) -> list[dict[str, str]]:
    from sqlmodel import Session, select

    from app.canonical_models import ExploreFacetReadModel, ExploreFilmReadModel
    from app.services.explore_query import explore_query_service

    empty = {dimension: [] for dimension in DIMENSIONS}
    with Session(engine) as session:
        target_facets = session.exec(
            select(ExploreFacetReadModel)
            .where(ExploreFacetReadModel.film_id == expected["target_id"])
            .where(ExploreFacetReadModel.eligible.is_(True))
        ).all()
        by_dimension = {row.dimension: row.facet_key for row in target_facets}
        genre_keys = session.exec(
            select(ExploreFacetReadModel.facet_key)
            .where(ExploreFacetReadModel.dimension == "genre")
            .where(ExploreFacetReadModel.eligible.is_(True))
            .distinct()
            .order_by(ExploreFacetReadModel.facet_key)
        ).all()
        watched_count = len(
            session.exec(
                select(ExploreFilmReadModel.film_id).where(ExploreFilmReadModel.watched.is_(True))
            ).all()
        )
    strict_filters = {dimension: [by_dimension[dimension]] for dimension in DIMENSIONS}
    strict = explore_query_service.list_films(
        filters=strict_filters,
        view="unwatched",
        sort="title",
        direction="asc",
        limit=40,
        offset=0,
    )
    strict_context = explore_query_service.context(filters=strict_filters, view="unwatched", limit=6)
    or_result = explore_query_service.list_films(
        filters={**empty, "genre": genre_keys[:2]},
        view="all",
        sort="title",
        direction="asc",
        limit=40,
        offset=0,
    )
    unresolved = explore_query_service.list_films(
        filters={**empty, "country": ["ZZ"]},
        view="all",
        sort="title",
        direction="asc",
        limit=40,
        offset=0,
    )
    conflicted = explore_query_service.list_films(
        filters={**empty, "country": ["XZ"]},
        view="all",
        sort="title",
        direction="asc",
        limit=40,
        offset=0,
    )
    watched = explore_query_service.list_films(
        filters=empty,
        view="watched",
        sort="title",
        direction="asc",
        limit=40,
        offset=0,
    )
    expected_or = expected["coverage"]["genre"]["covered_films"]
    return [
        _check(f"{prefix}-strict-four-dimension-and", strict["total"] == 1),
        _check(f"{prefix}-strict-context-matches-films", strict_context["current_total"] == strict["total"]),
        _check(f"{prefix}-same-dimension-or", or_result["total"] == expected_or),
        _check(
            f"{prefix}-unresolved-filter-fails-closed",
            unresolved["total"] == 0 and bool(unresolved["unresolved_filters"]),
        ),
        _check(
            f"{prefix}-conflicted-filter-fails-closed",
            conflicted["total"] == 0 and bool(conflicted["unresolved_filters"]),
        ),
        _check(f"{prefix}-viewing-and", watched["total"] == watched_count == expected["watched_count"]),
        _check(
            f"{prefix}-result-reasons-cover-four-dimensions",
            (
                {item["dimension"] for item in strict["items"][0]["matched_facts"]}
                == set(DIMENSIONS)
                if strict["items"]
                else False
            ),
        ),
    ]


def _timed(function, *args, **kwargs):
    started = perf_counter()
    value = function(*args, **kwargs)
    return value, (perf_counter() - started) * 1000


def _coverage(total: int, covered: int, conflicted: int, missing: int) -> dict[str, int]:
    return {
        "total_films": total,
        "covered_films": covered,
        "conflicted_films": conflicted,
        "missing_films": missing,
    }


def _check(check_id: str, passed: bool) -> dict[str, str]:
    return {"id": check_id, "status": "passed" if passed else "failed"}


def _stable_hex(seed: int, index: int, kind: str) -> str:
    return hashlib.sha256(f"{seed}:{index}:{kind}".encode("utf-8")).hexdigest()[:32]


def _canonical_hash(value: Any) -> str:
    serialized = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _fixture_contract_hash(seed: int, count: int, scale_count: int) -> str:
    value = {
        "schema": REPORT_SCHEMA_VERSION,
        "seed": seed,
        "count": count,
        "scale_count": scale_count,
        "dimensions": DIMENSIONS,
        "missing_policy": "index-mod-20-equals-0",
        "conflict_policy": "country-index-mod-20-equals-1",
        "watched_policy": "index-mod-3-equals-0",
    }
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:16]


def _git_sha() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--short=12", "HEAD"],
        cwd=Path(__file__).resolve().parents[3],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else "unavailable"


def _assert_report_privacy(report: dict[str, Any], run_dir: Path) -> None:
    serialized = json.dumps(report, ensure_ascii=False, sort_keys=True).casefold()
    if str(run_dir).casefold() in serialized or any(value in serialized for value in FORBIDDEN_PUBLIC_TEXT):
        raise FactualExploreEvaluationError("Evaluation report contains private material")


def _assert_text_privacy(text: str) -> None:
    normalized = text.casefold()
    if any(value in normalized for value in FORBIDDEN_PUBLIC_TEXT):
        raise FactualExploreEvaluationError("Evaluation summary contains private material")


def _validate_options(run_id: str, count: int, scale_count: int) -> None:
    if not RUN_ID_PATTERN.fullmatch(run_id):
        raise FactualExploreEvaluationError("Run ID must be a bounded portable identifier")
    if count < 8:
        raise FactualExploreEvaluationError("Behavior fixture requires at least 8 Films")
    if scale_count < 48:
        raise FactualExploreEvaluationError("Scale fixture requires at least 48 Films")


def _default_output_root() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "factual-explore-evaluation"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default=datetime.now(timezone.utc).strftime("w7-%Y%m%d-%H%M%S"))
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--count", type=int, default=DEFAULT_COUNT)
    parser.add_argument("--scale-count", type=int, default=DEFAULT_SCALE_COUNT)
    parser.add_argument("--worker-mode", choices=("behavior", "scale"), help=argparse.SUPPRESS)
    parser.add_argument("--worker-dir", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--worker-output", type=Path, help=argparse.SUPPRESS)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.worker_mode:
            if args.worker_dir is None or args.worker_output is None:
                raise FactualExploreEvaluationError("Worker paths are required")
            return _worker(
                args.worker_mode,
                args.worker_dir,
                args.worker_output,
                seed=args.seed,
                count=args.count,
            )
        report = run_evaluation(
            run_id=args.run_id,
            seed=args.seed,
            count=args.count,
            scale_count=args.scale_count,
        )
        print(render_git_safe_summary(report))
        return 0 if report["status"] == "passed" else 1
    except FactualExploreEvaluationError as exc:
        print(f"Factual Explore evaluation failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
