from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import statistics
import sys
from collections import Counter
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from openai import OpenAI
from pydantic import ValidationError
from sqlalchemy import text
from sqlmodel import SQLModel, Session, create_engine, select

from app.canonical_models import (
    AnalysisResolutionReview,
    AnalysisRun,
    Assertion,
    AssertionEvidence,
    AssertionProvenance,
    Concept,
    ConceptAlias,
    Evidence,
    ExternalIdentity,
    Film,
    FilmCountry,
    FilmCountryProvenance,
    FilmTitle,
    GraphEntity,
    LegacyMovieAlias,
    LibraryItem,
    LocalProfile,
)
from app.contracts.analysis_persistence import (
    assertion_qualifier_hash,
    assertion_semantic_key,
)
from app.contracts.analysis_v2 import (
    AnalysisEvaluationDataset,
    AnalysisEvaluationHumanReview,
    AnalysisV2Output,
    GateBPricingManifest,
)
from app.contracts.structured_metadata import canonical_json_hash, normalize_metadata_text
from app.migrations.backup import create_verified_backup, inspect_database
from app.migrations.restore import restore_verified_backup
from app.models import Movie
from app.services.analysis import AnalysisExecutionError, AnalysisService
from app.services.analysis_evidence import (
    EVIDENCE_VERIFICATION_POLICY_VERSION,
    EvidenceBatchResult,
    VerifiedEvidenceCandidate,
    evidence_retriever,
)
from app.services.historian import (
    AnalysisGenerationResult,
    AnalysisModelConfiguration,
    FilmHistorian,
)


REPORT_SCHEMA_VERSION = 1
POLICY_VERSION = "gate-b-policy.v2"
SUPPORTED_POLICY_VERSIONS = frozenset({"gate-b-policy.v1", POLICY_VERSION})
HUMAN_REVIEW_VERSION = "analysis-eval-human-review.v1"
VALID_STATUSES = frozenset({"passed", "failed", "blocked"})
W4_TABLES = (
    "analysis_run",
    "assertion",
    "assertion_provenance",
    "evidence",
    "assertion_evidence",
    "analysis_resolution_review",
)
SENSITIVE_CANARIES = (
    "sk-gate-b-private-canary",
    "C:\\GateBPrivate\\library.mkv",
    "/home/private/gate-b/library.mkv",
    "<html>gate-b-source-body-canary</html>",
    "chain_of_thought",
    "thought_chain",
)


class GateBValidationError(RuntimeError):
    pass


class GateBBlocked(GateBValidationError):
    pass


def load_dataset(path: Path) -> AnalysisEvaluationDataset:
    path = path.resolve()
    fixtures_root = (_backend_root() / "fixtures" / "analysis_v2").resolve()
    if not path.is_file() or not path.is_relative_to(fixtures_root):
        raise GateBValidationError("Gate B dataset must be a versioned analysis_v2 fixture")
    try:
        return AnalysisEvaluationDataset.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as exc:
        raise GateBValidationError("Gate B dataset is invalid") from exc


def load_policy(path: Path) -> dict[str, Any]:
    path = path.resolve()
    fixtures_root = (_backend_root() / "fixtures" / "analysis_v2").resolve()
    if not path.is_file() or not path.is_relative_to(fixtures_root):
        raise GateBValidationError("Gate B policy must be a versioned analysis_v2 fixture")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GateBValidationError("Gate B policy is invalid JSON") from exc
    if not isinstance(payload, dict) or payload.get("format_version") not in SUPPORTED_POLICY_VERSIONS:
        raise GateBValidationError("Gate B policy version is unsupported")
    for key in ("dataset", "thresholds", "priority_evidence_predicates"):
        if key not in payload:
            raise GateBValidationError(f"Gate B policy is missing {key}")
    if "predicate_minimums" not in payload["dataset"]:
        raise GateBValidationError("Gate B policy is missing dataset predicate_minimums")
    if payload.get("evidence_policy_version") != EVIDENCE_VERIFICATION_POLICY_VERSION:
        raise GateBValidationError("Gate B Evidence policy does not match the runtime")
    return payload


def validate_dataset(
    dataset: AnalysisEvaluationDataset,
    policy: Mapping[str, Any],
) -> dict[str, Any]:
    requirements = policy["dataset"]
    languages = Counter(case.language for case in dataset.cases)
    tags = Counter(tag for case in dataset.cases for tag in case.tags)
    predicates = Counter(
        expected.predicate.value
        for case in dataset.cases
        for expected in case.expected_assertions
        if expected.label in {"required", "acceptable"}
    )
    forbidden_cases = sum(
        any(item.label == "forbidden" for item in case.expected_assertions)
        for case in dataset.cases
    )
    subject_film_ids = [case.input.film_id for case in dataset.cases]
    subject_identities = [
        (provider, external_id)
        for case in dataset.cases
        for provider, external_id in case.input.external_identities.items()
    ]
    checks = [
        _check("dataset-case-count", len(dataset.cases) == int(requirements["case_count"])),
        _check(
            "dataset-language-coverage",
            languages["zh"] >= int(requirements["language_minimums"]["zh"])
            and languages["en"] >= int(requirements["language_minimums"]["en"])
            and languages["mixed"] + languages["other"]
            >= int(requirements["language_minimums"]["mixed_or_other"]),
        ),
        _check(
            "dataset-tag-coverage",
            all(tags[tag] >= int(minimum) for tag, minimum in requirements["tag_minimums"].items()),
        ),
        _check(
            "dataset-predicate-coverage",
            all(
                predicates[predicate] >= int(minimum)
                for predicate, minimum in requirements["predicate_minimums"].items()
            ),
        ),
        _check(
            "dataset-forbidden-traps",
            forbidden_cases >= int(requirements["forbidden_case_minimum"])
            and all(
                any(item.label == "forbidden" for item in case.expected_assertions)
                for case in dataset.cases
                if "same_title" in case.tags
            ),
        ),
        _check(
            "dataset-public-identities",
            all(case.input.external_identities for case in dataset.cases)
            and len(subject_film_ids) == len(set(subject_film_ids))
            and len(subject_identities) == len(set(subject_identities))
            and all(
                expected.target.entity_type != "film"
                or bool(expected.target.provider and expected.target.external_id)
                for case in dataset.cases
                for expected in case.expected_assertions
            ),
        ),
        _check(
            "dataset-has-expected-assertions",
            all(
                case.expected_assertions
                and all(expected.note for expected in case.expected_assertions)
                and sum(
                    len(assertion_match_keys(expected))
                    for expected in case.expected_assertions
                )
                == len({
                    key
                    for expected in case.expected_assertions
                    for key in assertion_match_keys(expected)
                })
                for case in dataset.cases
            ),
        ),
        _check(
            "dataset-sensitive-fields-absent",
            not _privacy_leaks(dataset.model_dump(mode="json")),
        ),
    ]
    validation_status = _phase_status(checks)
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "dataset_id": dataset.dataset_id,
        "dataset_hash": dataset_hash(dataset),
        "policy_version": str(policy["format_version"]),
        "checks": checks,
        "validation_status": validation_status,
        "adjudication_ready": all(
            case.adjudication_status == "adjudicated" and case.annotator_count >= 1
            for case in dataset.cases
        ),
        "overall_status": validation_status,
    }


def dataset_hash(dataset: AnalysisEvaluationDataset) -> str:
    payload = dataset.model_dump(mode="json")
    # Runtime-only prompt context must not alter the already frozen public
    # evaluation corpus when older fixtures omit the new optional field.
    for case in payload.get("cases") or []:
        case_input = case.get("input") or {}
        if not case_input.get("available_concepts"):
            case_input.pop("available_concepts", None)
    return canonical_json_hash(payload)


def assertion_match_key(value: Any) -> str:
    payload = value.model_dump(mode="json", exclude_none=True) if hasattr(value, "model_dump") else dict(value)
    target = payload.get("target") or {}
    if target.get("provider") and target.get("external_id"):
        target_key = f"provider:{target['provider']}:{target['external_id']}"
    elif target.get("entity_id"):
        target_key = f"entity:{target['entity_id']}"
    else:
        target_key = (
            f"name:{target.get('entity_type')}:{normalize_metadata_text(str(target.get('display_name') or ''))}:"
            f"{target.get('release_year') or ''}"
        )
    semantic = {
        "predicate": payload.get("predicate"),
        "direction": payload.get("direction") or "subject_to_target",
        "target": target_key,
        "qualifiers": payload.get("qualifiers") or {},
    }
    return canonical_json_hash(semantic)


def assertion_match_keys(value: Any) -> frozenset[str]:
    """Return the canonical expected key plus any adjudicated Concept aliases."""
    payload = (
        value.model_dump(mode="json", exclude_none=True)
        if hasattr(value, "model_dump")
        else dict(value)
    )
    keys = {assertion_match_key(payload)}
    target = payload.get("target") or {}
    aliases = payload.get("target_aliases") or []
    if target.get("entity_type") != "concept":
        return frozenset(keys)
    for alias in aliases:
        aliased_payload = dict(payload)
        aliased_payload.pop("target_aliases", None)
        aliased_payload["target"] = {**target, "display_name": alias}
        keys.add(assertion_match_key(aliased_payload))
    return frozenset(keys)


def prediction_hash(value: Any) -> str:
    payload = value.model_dump(mode="json", exclude_none=True) if hasattr(value, "model_dump") else dict(value)
    return canonical_json_hash(payload)


def score_evaluation(
    case_results: Sequence[Mapping[str, Any]],
    *,
    policy: Mapping[str, Any],
    human_review: AnalysisEvaluationHumanReview | None,
    operational_metrics: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    operational_metrics = dict(operational_metrics or {})
    thresholds = policy["thresholds"]
    priority_predicates = set(policy["priority_evidence_predicates"])
    human_cases = {case.case_id: case for case in human_review.cases} if human_review else {}

    completed = 0
    display_predictions = 0
    acceptable_display_predictions = 0
    resolution_total = 0
    resolution_correct = 0
    required_total = 0
    required_matched = 0
    forbidden_or_harmful = 0
    invented_entities = 0
    unresolved_total = 0
    unresolved_with_review = 0
    resolved_identity_conflicts = 0
    identity_conflicts = 0
    identity_conflicts_with_review = 0
    qualifier_policy_violations = 0
    assertion_counts: list[float] = []
    semantic_duplicates = 0
    priority_evidence_total = 0
    priority_evidence_covered = 0
    input_tokens_complete = True
    output_tokens_complete = True
    costs_complete = True
    costs: list[float] = []
    helpfulness: list[int] = []
    missing_human_labels = 0

    for result in case_results:
        case_id = str(result.get("case_id") or "")
        if result.get("status") == "succeeded":
            completed += 1
        expected = result.get("expected_assertions") or []
        expected_by_key: dict[str, tuple[str, str]] = {}
        for index, item in enumerate(expected):
            label = str(item.get("label"))
            expected_id = f"{case_id}:{index}"
            for key in assertion_match_keys(item):
                expected_by_key[key] = (label, expected_id)
            if label == "required":
                required_total += 1

        predictions = result.get("predictions") or []
        assertion_counts.append(float(len(predictions)))
        prediction_keys = [assertion_match_key(item.get("candidate") or {}) for item in predictions]
        semantic_prediction_keys = [
            expected_by_key.get(
                str(item.get("expected_match_key") or ""),
                expected_by_key.get(key, ("", key)),
            )[1]
            for item, key in zip(predictions, prediction_keys, strict=True)
        ]
        semantic_duplicates += len(semantic_prediction_keys) - len(set(semantic_prediction_keys))
        human_case = human_cases.get(case_id)
        human_novel = (
            {item.prediction_hash: item.label for item in human_case.novel_predictions}
            if human_case
            else {}
        )
        if human_case:
            helpfulness.append(human_case.summary_helpfulness)

        matched_required_keys: set[str] = set()
        for item, key in zip(predictions, prediction_keys, strict=True):
            candidate = item.get("candidate") or {}
            resolved = item.get("resolution_status") == "resolved"
            review = item.get("resolution_status") == "review"
            review_reason = item.get("review_reason")
            qualifiers = candidate.get("qualifiers") or {}
            qualifier_policy_violations += int(bool(qualifiers))
            expected_match = expected_by_key.get(str(item.get("expected_match_key") or ""))
            if expected_match is None:
                expected_match = expected_by_key.get(key)
            label = expected_match[0] if expected_match else None
            if label is None:
                label = human_novel.get(str(item.get("prediction_hash") or ""))
                if label is None:
                    missing_human_labels += 1

            resolution_total += 1
            resolution_correct += int(item.get("resolution_correct") is True)

            if resolved:
                if item.get("identity_consistent") is False:
                    resolved_identity_conflicts += 1
                    identity_conflicts += 1
                display_predictions += 1
                if label in {"required", "acceptable"}:
                    acceptable_display_predictions += 1
                if label in {"forbidden", "harmful"}:
                    forbidden_or_harmful += 1
                if label == "required" and expected_match is not None:
                    matched_required_keys.add(expected_match[1])
                if (
                    label in {"required", "acceptable"}
                    and candidate.get("predicate") in priority_predicates
                ):
                    priority_evidence_total += 1
                    evidence_rows = item.get("evidence") or []
                    if any(
                        evidence.get("active") is True
                        and evidence.get("fresh") is True
                        and evidence.get("stance") in {"supports", "context"}
                        and evidence.get("policy_version")
                        == policy["evidence_policy_version"]
                        for evidence in evidence_rows
                    ):
                        priority_evidence_covered += 1
            elif review:
                unresolved_total += 1
                unresolved_with_review += int(item.get("review_created") is True)
                if review_reason == "identity_conflict":
                    identity_conflicts += 1
                    identity_conflicts_with_review += int(item.get("review_created") is True)
            invented_entities += int(item.get("invented_entity") is True)
        required_matched += len(matched_required_keys)

        if result.get("status") == "succeeded":
            input_tokens_complete &= isinstance(result.get("input_tokens"), int)
            output_tokens_complete &= isinstance(result.get("output_tokens"), int)
            raw_cost = result.get("cost_usd")
            costs_complete &= isinstance(raw_cost, (int, float)) and not isinstance(raw_cost, bool)
            if isinstance(raw_cost, (int, float)) and not isinstance(raw_cost, bool):
                costs.append(float(raw_cost))

    case_count = len(case_results)
    prediction_count = sum(len(result.get("predictions") or []) for result in case_results)
    metrics = {
        "run_completion_rate": _ratio(completed, case_count),
        "display_edge_precision": _ratio(acceptable_display_predictions, display_predictions),
        "resolution_decision_accuracy": _ratio(resolution_correct, resolution_total),
        "required_assertion_recall": _ratio(required_matched, required_total),
        "forbidden_or_harmful_count": forbidden_or_harmful,
        "invented_entity_count": invented_entities,
        "unresolved_review_capture_rate": _ratio(unresolved_with_review, unresolved_total),
        "resolved_identity_conflict_count": resolved_identity_conflicts,
        "identity_conflict_review_capture_rate": _ratio(
            identity_conflicts_with_review,
            identity_conflicts,
        ),
        "qualifier_policy_violation_count": qualifier_policy_violations,
        "assertions_per_case_p95": _percentile(assertion_counts, 0.95),
        "semantic_duplicate_rate": _ratio(semantic_duplicates, max(1, prediction_count)),
        "replay_new_row_count": int(operational_metrics.get("replay_new_row_count", 0)),
        "rejected_reactivation_count": int(operational_metrics.get("rejected_reactivation_count", 0)),
        "review_field_change_count": int(operational_metrics.get("review_field_change_count", 0)),
        "revoked_link_reactivation_count": int(
            operational_metrics.get("revoked_link_reactivation_count", 0)
        ),
        "helpfulness_median": float(statistics.median(helpfulness)) if helpfulness else None,
        "helpfulness_four_or_higher_rate": _ratio(sum(value >= 4 for value in helpfulness), case_count),
        "priority_evidence_coverage": _ratio(priority_evidence_covered, priority_evidence_total),
        "total_cost_usd": round(sum(costs), 8) if costs_complete else None,
        "case_cost_p95_usd": _percentile(costs, 0.95) if costs_complete else None,
        "token_and_cost_complete": input_tokens_complete and output_tokens_complete and costs_complete,
        "human_case_count": len(helpfulness),
        "missing_human_prediction_labels": missing_human_labels,
        "restore_equal": bool(operational_metrics.get("restore_equal", False)),
        "privacy_leak_count": int(operational_metrics.get("privacy_leak_count", 0)),
    }
    checks = [
        _threshold_check("run-completion", metrics, thresholds, "run_completion_rate", minimum=True),
        _threshold_check("display-edge-precision", metrics, thresholds, "display_edge_precision", minimum=True),
        _threshold_check("resolution-accuracy", metrics, thresholds, "resolution_decision_accuracy", minimum=True),
        _threshold_check("required-recall", metrics, thresholds, "required_assertion_recall", minimum=True),
        _threshold_check("forbidden-or-harmful", metrics, thresholds, "forbidden_or_harmful_count"),
        _threshold_check("invented-entity", metrics, thresholds, "invented_entity_count"),
        _threshold_check("review-capture", metrics, thresholds, "unresolved_review_capture_rate", minimum=True),
        _threshold_check("semantic-duplicates", metrics, thresholds, "semantic_duplicate_rate"),
        _threshold_check("replay-idempotence", metrics, thresholds, "replay_new_row_count"),
        _threshold_check("rejected-protection", metrics, thresholds, "rejected_reactivation_count"),
        _threshold_check("review-field-protection", metrics, thresholds, "review_field_change_count"),
        _threshold_check(
            "revoked-link-protection",
            metrics,
            thresholds,
            "revoked_link_reactivation_count",
        ),
        _threshold_check("evidence-coverage", metrics, thresholds, "priority_evidence_coverage", minimum=True),
        _check("restore-equal", metrics["restore_equal"]),
        _check("privacy-clean", metrics["privacy_leak_count"] == 0),
    ]
    optional_thresholds = (
        ("resolved-identity-conflicts", "resolved_identity_conflict_count", False),
        ("identity-conflict-review-capture", "identity_conflict_review_capture_rate", True),
        ("qualifier-policy", "qualifier_policy_violation_count", False),
        ("assertion-count-p95", "assertions_per_case_p95", False),
    )
    checks.extend(
        _threshold_check(check_id, metrics, thresholds, metric, minimum=minimum)
        for check_id, metric, minimum in optional_thresholds
        if metric in thresholds
    )
    if human_review is None or len(helpfulness) != case_count or missing_human_labels:
        checks.append(_check("human-review-complete", False, blocked=True))
    else:
        checks.extend([
            _threshold_check("helpfulness-median", metrics, thresholds, "helpfulness_median", minimum=True),
            _threshold_check(
                "helpfulness-four-or-higher",
                metrics,
                thresholds,
                "helpfulness_four_or_higher_rate",
                minimum=True,
            ),
        ])
    if not metrics["token_and_cost_complete"]:
        checks.append(_check("token-and-cost-complete", False, blocked=True))
    else:
        checks.extend([
            _threshold_check("total-cost", metrics, thresholds, "total_cost_usd"),
            _threshold_check("case-cost-p95", metrics, thresholds, "case_cost_p95_usd"),
        ])
    return {"metrics": metrics, "checks": checks, "status": _phase_status(checks)}


def run_rehearsal(
    dataset_path: Path,
    run_dir: Path,
    *,
    policy_path: Path | None = None,
) -> dict[str, Any]:
    dataset = load_dataset(dataset_path)
    policy = load_policy(policy_path or _default_policy_path(dataset_path))
    run_dir = _validate_run_dir(run_dir)
    run_dir.mkdir(parents=True, exist_ok=False)
    validation = validate_dataset(dataset, policy)
    phases = {
        "preflight": validation["validation_status"],
        "dataset": "passed",
        "persistence": "blocked",
        "scoring": "blocked",
        "restore": "blocked",
        "privacy": "blocked",
        "live": "blocked",
        "human": "blocked",
    }
    checks = list(validation["checks"])
    checks.append(
        _check(
            "dataset-adjudicated",
            validation["adjudication_ready"],
            blocked=not validation["adjudication_ready"],
        )
    )
    database_path = run_dir / "work" / "gate-b.db"
    database_path.parent.mkdir(parents=True)
    engine = _create_isolated_database(database_path)
    try:
        _seed_dataset(engine, dataset)
        operational = _exercise_persistence(engine, dataset)
        phases["persistence"] = "passed" if operational["persistence_passed"] else "failed"
        checks.append(_check("runtime-persistence-contract", operational["persistence_passed"]))
    finally:
        engine.dispose()

    before_restore = _w4_digest(database_path)
    backup = create_verified_backup(
        database_path,
        run_dir / "backups" / "post-run",
        app_version="gate-b-rehearsal",
        source_schema_version=_schema_version(database_path),
        target_schema_version=_schema_version(database_path),
    )
    with closing(sqlite3.connect(database_path)) as connection:
        connection.execute("CREATE TABLE gate_b_restore_sentinel (value TEXT NOT NULL)")
        connection.execute("INSERT INTO gate_b_restore_sentinel VALUES ('mutated')")
        connection.commit()
    mutated_hash = inspect_database(database_path).sha256
    restored = restore_verified_backup(
        backup.manifest_path,
        database_path,
        expected_target_sha256=mutated_hash,
        preserve_dir=run_dir / "backups" / "pre-restore",
        app_version="gate-b-rehearsal",
    )
    restore_equal = restored.restored_sha256 == backup.sha256 and _w4_digest(database_path) == before_restore
    phases["restore"] = "passed" if restore_equal else "failed"
    checks.append(_check("verified-backup-restores-w4", restore_equal))

    synthetic_results = _synthetic_case_results(dataset, policy)
    synthetic_review = AnalysisEvaluationHumanReview.model_validate({
        "run_id": run_dir.name,
        "dataset_id": dataset.dataset_id,
        "dataset_hash": dataset_hash(dataset),
        "reviewer_count": 1,
        "cases": [
            {"case_id": case.case_id, "summary_helpfulness": 4, "novel_predictions": []}
            for case in dataset.cases
        ],
    })
    operational_metrics = {
        **operational,
        "restore_equal": restore_equal,
        "privacy_leak_count": 0,
    }
    scored = score_evaluation(
        synthetic_results,
        policy=policy,
        human_review=synthetic_review,
        operational_metrics=operational_metrics,
    )
    phases["scoring"] = scored["status"]
    checks.append(_check("deterministic-scorer-rehearsal", scored["status"] == "passed"))

    provisional = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "run_id": run_dir.name,
        "dataset_id": dataset.dataset_id,
        "dataset_hash": dataset_hash(dataset),
        "policy_version": str(policy["format_version"]),
        "model_snapshot": None,
        "pricing_hash": None,
        "checks": checks,
        "metrics": scored["metrics"],
        "phases": phases,
        "cases": synthetic_results,
        "operational_metrics": operational_metrics,
        "tool_status": _tool_status(phases),
        "live_status": "blocked",
        "human_status": "blocked",
        "overall_status": "blocked",
    }
    leak_count = len(_privacy_leaks(provisional)) + _database_privacy_leak_count(database_path)
    provisional["operational_metrics"]["privacy_leak_count"] = leak_count
    phases["privacy"] = "passed" if leak_count == 0 else "failed"
    checks.append(_check("gate-b-surfaces-are-redacted", leak_count == 0))
    provisional["tool_status"] = _tool_status(phases)
    if provisional["tool_status"] == "failed":
        provisional["overall_status"] = "failed"
    _write_json(run_dir / "run-report.json", provisional)
    return provisional


def run_live(
    dataset_path: Path,
    run_dir: Path,
    *,
    provider: str,
    model: str,
    pricing_path: Path,
    allow_public_network: bool,
    policy_path: Path | None = None,
    reasoning_effort: str | None = None,
    max_output_tokens: int | None = None,
    case_limit: int | None = None,
    diagnostic: bool = False,
) -> dict[str, Any]:
    dataset = load_dataset(dataset_path)
    policy = load_policy(policy_path or _default_policy_path(dataset_path))
    run_dir = _validate_run_dir(run_dir)
    validation = validate_dataset(dataset, policy)
    blockers: list[str] = []
    if provider != "openrouter":
        blockers.append("unsupported_provider")
    if not validation["adjudication_ready"]:
        blockers.append("dataset_awaiting_human_adjudication")
    if not allow_public_network:
        blockers.append("public_network_not_authorized")
    if not provider or not model:
        blockers.append("exact_model_snapshot_missing")
    if max_output_tokens is not None and not 256 <= max_output_tokens <= 131072:
        blockers.append("max_output_tokens_invalid")
    if case_limit is not None and not 1 <= case_limit <= (12 if diagnostic else len(dataset.cases)):
        blockers.append("case_limit_invalid")
    if not os.getenv("OPENROUTER_API_KEY"):
        blockers.append("openrouter_key_missing")
    pricing = _load_pricing(pricing_path, provider=provider, model=model, blockers=blockers)
    evidence_preflight = None
    if not blockers:
        evidence_preflight = evidence_retriever.preflight()
        if evidence_preflight and not diagnostic:
            blockers.append(evidence_preflight)
    run_dir.mkdir(parents=True, exist_ok=False)
    if blockers:
        report = _blocked_live_report(
            dataset,
            policy,
            run_dir,
            provider,
            model,
            pricing,
            blockers,
            reasoning_effort=reasoning_effort,
            max_output_tokens=max_output_tokens,
        )
        if diagnostic:
            report["diagnostic_status"] = "blocked"
            report["case_limit"] = case_limit
        _write_json(run_dir / "run-report.json", report)
        return report

    database_path = run_dir / "work" / "gate-b.db"
    database_path.parent.mkdir(parents=True)
    engine = _create_isolated_database(database_path)
    try:
        _seed_dataset(engine, dataset)
        historian = _PinnedHistorian(
            provider,
            model,
            reasoning_effort=reasoning_effort,
            max_output_tokens=max_output_tokens,
        )
        service = AnalysisService(database_engine=engine, historian=historian)
        case_results: list[dict[str, Any]] = []
        total_cost = 0.0
        selected_cases = dataset.cases[:case_limit] if case_limit is not None else dataset.cases
        for case in selected_cases:
            if total_cost >= float(policy["thresholds"]["total_cost_usd"]):
                case_results.append(_failed_case_result(case, "budget_exceeded"))
                continue
            try:
                service.analyze_movie(case.case_id)
                result = _collect_live_case_result(engine, case, historian, pricing, policy)
            except AnalysisExecutionError:
                result = _failed_case_result(case, "analysis_failed")
            case_results.append(result)
            if isinstance(result.get("cost_usd"), (int, float)):
                total_cost += float(result["cost_usd"])
        operational = _live_operational_checks(engine, dataset, service)
    finally:
        engine.dispose()

    backup = create_verified_backup(
        database_path,
        run_dir / "backups" / "post-run",
        app_version="gate-b-live",
        source_schema_version=_schema_version(database_path),
        target_schema_version=_schema_version(database_path),
    )
    restored_path = run_dir / "restore" / "gate-b.db"
    restored_path.parent.mkdir(parents=True)
    restored_path.write_bytes(database_path.read_bytes())
    restored_hash = inspect_database(restored_path).sha256
    restore_verified_backup(
        backup.manifest_path,
        restored_path,
        expected_target_sha256=restored_hash,
        preserve_dir=run_dir / "backups" / "live-pre-restore",
        app_version="gate-b-live",
    )
    operational["restore_equal"] = _w4_digest(restored_path) == _w4_digest(database_path)
    provisional = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "run_id": run_dir.name,
        "dataset_id": dataset.dataset_id,
        "dataset_hash": dataset_hash(dataset),
        "policy_version": str(policy["format_version"]),
        "model_snapshot": {
            "provider": provider,
            "model": model,
            "reasoning_effort": reasoning_effort,
            "max_output_tokens": max_output_tokens,
        },
        "pricing_hash": canonical_json_hash(pricing.model_dump(mode="json")),
        "checks": list(validation["checks"]),
        "metrics": {},
        "phases": {"preflight": "passed", "live": "passed", "human": "blocked"},
        "cases": case_results,
        "operational_metrics": operational,
        "tool_status": "passed",
        "live_status": "passed",
        "human_status": "blocked",
        "overall_status": "blocked",
    }
    operational["privacy_leak_count"] = len(_privacy_leaks(provisional)) + _database_privacy_leak_count(database_path)
    scored = score_evaluation(case_results, policy=policy, human_review=None, operational_metrics=operational)
    provisional["metrics"] = scored["metrics"]
    if diagnostic:
        diagnostic_status = (
            "passed"
            if all(result.get("status") == "succeeded" for result in case_results)
            and operational["privacy_leak_count"] == 0
            and operational["restore_equal"]
            else "failed"
        )
        provisional.update({
            "case_limit": case_limit,
            "diagnostic_status": diagnostic_status,
            "live_status": "blocked",
            "overall_status": "blocked" if diagnostic_status == "passed" else "failed",
        })
        provisional["phases"] = {
            "preflight": "blocked" if evidence_preflight else "passed",
            "pilot": diagnostic_status,
            "live": "blocked",
            "human": "blocked",
        }
        if evidence_preflight:
            provisional["checks"].append(
                _check(f"pilot-preflight-{evidence_preflight.replace('_', '-')}", False, blocked=True)
            )
    else:
        provisional["checks"].extend(scored["checks"])
        if any(check["status"] == "failed" for check in provisional["checks"]):
            provisional["live_status"] = "failed"
            provisional["overall_status"] = "failed"
    _write_json(run_dir / "run-report.json", provisional)
    return provisional


def run_pilot(
    dataset_path: Path,
    run_dir: Path,
    *,
    provider: str,
    model: str,
    pricing_path: Path,
    allow_public_network: bool,
    case_limit: int = 6,
    policy_path: Path | None = None,
    reasoning_effort: str | None = None,
    max_output_tokens: int | None = None,
) -> dict[str, Any]:
    """Run a bounded tuning diagnostic that can never count as Gate B evidence."""

    return run_live(
        dataset_path,
        run_dir,
        provider=provider,
        model=model,
        pricing_path=pricing_path,
        allow_public_network=allow_public_network,
        policy_path=policy_path,
        reasoning_effort=reasoning_effort,
        max_output_tokens=max_output_tokens,
        case_limit=case_limit,
        diagnostic=True,
    )


def create_review_template(run_report_path: Path, output_path: Path) -> dict[str, Any]:
    report = _read_report(run_report_path)
    if report.get("live_status") != "passed" or not report.get("cases"):
        raise GateBBlocked("Human review requires a completed live Gate B run")
    _require_frozen_adjudicated_dataset(report)
    output_path = output_path.resolve()
    if output_path.parent != run_report_path.resolve().parent:
        raise GateBValidationError("Human review template must stay beside its run report")
    cases = []
    for result in report.get("cases") or []:
        novel = [
            {
                "prediction_hash": item.get("prediction_hash"),
                "label": None,
                "note": None,
            }
            for item in result.get("predictions") or []
            if item.get("expected_label") is None
        ]
        cases.append({
            "case_id": result.get("case_id"),
            "summary_helpfulness": None,
            "novel_predictions": novel,
        })
    template = {
        "format_version": HUMAN_REVIEW_VERSION,
        "run_id": report["run_id"],
        "dataset_id": report["dataset_id"],
        "dataset_hash": report["dataset_hash"],
        "reviewer_count": 1,
        "cases": cases,
    }
    _write_json(output_path, template)
    return {"output": output_path.name, "case_count": len(cases), "overall_status": "blocked"}


def conclude(run_report_path: Path, human_review_path: Path, *, policy_path: Path | None = None) -> dict[str, Any]:
    report = _read_report(run_report_path)
    if report.get("live_status") != "passed":
        raise GateBBlocked("Gate B live evidence is incomplete")
    _require_frozen_adjudicated_dataset(report)
    if human_review_path.resolve().parent != run_report_path.resolve().parent:
        raise GateBValidationError("Human review must stay beside its run report")
    try:
        review = AnalysisEvaluationHumanReview.model_validate_json(
            human_review_path.read_text(encoding="utf-8")
        )
    except (OSError, ValidationError) as exc:
        raise GateBBlocked("Human review is incomplete or invalid") from exc
    if (
        review.run_id != report.get("run_id")
        or review.dataset_id != report.get("dataset_id")
        or review.dataset_hash != report.get("dataset_hash")
    ):
        raise GateBBlocked("Human review does not match the frozen run and dataset")
    _validate_human_review_coverage(report, review)
    policy = load_policy(policy_path or _default_policy_path_from_report(run_report_path))
    scored = score_evaluation(
        report.get("cases") or [],
        policy=policy,
        human_review=review,
        operational_metrics=report.get("operational_metrics") or {},
    )
    human_checks = [
        check
        for check in scored["checks"]
        if check["id"].startswith("human-") or check["id"].startswith("helpfulness-")
    ]
    human_status = _phase_status(human_checks)
    statuses = {str(report.get("tool_status")), str(report.get("live_status")), human_status, scored["status"]}
    if "failed" in statuses:
        overall = "failed"
    elif "blocked" in statuses:
        overall = "blocked"
    else:
        overall = "passed"
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "run_id": report["run_id"],
        "dataset_id": report["dataset_id"],
        "dataset_hash": report["dataset_hash"],
        "policy_version": report["policy_version"],
        "model_snapshot": report.get("model_snapshot"),
        "pricing_hash": report.get("pricing_hash"),
        "checks": scored["checks"],
        "metrics": scored["metrics"],
        "phases": {**(report.get("phases") or {}), "human": human_status},
        "tool_status": report.get("tool_status"),
        "live_status": report.get("live_status"),
        "human_status": human_status,
        "overall_status": overall,
    }


def _validate_human_review_coverage(
    report: Mapping[str, Any],
    review: AnalysisEvaluationHumanReview,
) -> None:
    expected_by_case = {
        str(result.get("case_id")): {
            str(prediction.get("prediction_hash"))
            for prediction in result.get("predictions") or []
            if prediction.get("expected_label") is None
        }
        for result in report.get("cases") or []
    }
    supplied_by_case = {
        case.case_id: {prediction.prediction_hash for prediction in case.novel_predictions}
        for case in review.cases
    }
    if supplied_by_case.keys() != expected_by_case.keys() or any(
        supplied_by_case[case_id] != prediction_hashes
        for case_id, prediction_hashes in expected_by_case.items()
    ):
        raise GateBBlocked("Human review does not cover every case and novel prediction exactly")


def _require_frozen_adjudicated_dataset(report: Mapping[str, Any]) -> None:
    dataset = load_dataset(_backend_root() / "fixtures" / "analysis_v2" / "gate-b-v1.json")
    if (
        report.get("dataset_id") != dataset.dataset_id
        or report.get("dataset_hash") != dataset_hash(dataset)
        or not all(
            case.adjudication_status == "adjudicated" and case.annotator_count >= 1
            for case in dataset.cases
        )
    ):
        raise GateBBlocked("Gate B dataset is not frozen with completed human adjudication")


def _create_isolated_database(path: Path):
    from app.database import configure_sqlite_engine
    from app.migrations.runner import run_migrations

    engine = create_engine(f"sqlite:///{path}", connect_args={"timeout": 30})
    configure_sqlite_engine(engine)
    SQLModel.metadata.create_all(engine)
    run_migrations(engine, path, app_version="gate-b", backup_required=False)
    return engine


def _seed_dataset(engine, dataset: AnalysisEvaluationDataset) -> None:
    now = datetime.now(timezone.utc).isoformat()
    target_entities: dict[str, str] = {}
    with Session(engine) as session:
        if session.get(LocalProfile, "profile_gate_b") is None:
            session.add(LocalProfile(id="profile_gate_b", profile_key="gate-b", display_name=None))
        session.flush()

        # Seed every subject and its public identities before targets. A film
        # such as Tokyo Story can be both a target in an earlier case and a
        # subject later in the corpus; the subject's stable synthetic ID must
        # remain the owner of that public identity regardless of case order.
        for case in dataset.cases:
            _seed_film(session, case.input.film_id, case.input.canonical_title, case.input.release_year, now)
            film = session.get(Film, case.input.film_id)
            film.original_title = case.input.original_title
            film.runtime_minutes = case.input.runtime_minutes
            film.overview = case.input.overview
            session.add(film)
            for provider, external_id in case.input.external_identities.items():
                _seed_identity(session, case.input.film_id, provider, external_id, now)
        session.flush()

        for case in dataset.cases:
            for index, title in enumerate(case.input.localized_titles):
                normalized = normalize_metadata_text(title)
                session.add(FilmTitle(
                    id=_stable_id("title", f"{case.case_id}:{index}:{normalized}"),
                    film_id=case.input.film_id,
                    locale="und",
                    title_type="localized",
                    title=title,
                    normalized_title=normalized,
                    origin_kind="curated",
                    origin_ref=case.case_id,
                    observed_at=now,
                ))
            for country in case.input.countries:
                country_id = _stable_id("country", f"{case.case_id}:{country}")
                session.add(FilmCountry(id=country_id, film_id=case.input.film_id, iso_3166_1=country))
                session.add(FilmCountryProvenance(
                    id=_stable_id("countryprov", f"{case.case_id}:{country}"),
                    film_country_id=country_id,
                    origin_kind="curated",
                    origin_ref=case.case_id,
                    observed_at=now,
                ))
            for genre in case.input.genres:
                concept_id = _seed_concept(session, "genre", genre, now)
                qualifier_hash = assertion_qualifier_hash({})
                key = assertion_semantic_key(
                    subject_entity_id=case.input.film_id,
                    predicate="HAS_GENRE",
                    object_entity_id=concept_id,
                    qualifier_hash=qualifier_hash,
                )
                if session.exec(select(Assertion).where(Assertion.assertion_key == key)).first() is None:
                    session.add(Assertion(
                        subject_entity_id=case.input.film_id,
                        object_entity_id=concept_id,
                        predicate="HAS_GENRE",
                        qualifiers={},
                        qualifier_hash=qualifier_hash,
                        assertion_key=key,
                        source_scope="factual",
                        review_status="accepted",
                        review_method="import_policy",
                        review_policy_version="gate-b-dataset.v1",
                        reviewed_at=now,
                        first_seen_at=now,
                        last_seen_at=now,
                    ))
            item_id = _stable_id("lib", case.case_id)
            session.add(Movie(
                id=case.case_id,
                title=case.input.original_title or case.input.canonical_title,
                title_cn=case.input.canonical_title,
                year=case.input.release_year or 0,
                tmdb_id=case.input.external_identities.get("tmdb.movie"),
                imdb_id=case.input.external_identities.get("imdb.title"),
                overview=case.input.overview,
                genres=case.input.genres,
                library_status="available",
                metadata_source="curated",
                scrape_status="matched",
            ))
            session.add(LibraryItem(
                id=item_id,
                profile_id="profile_gate_b",
                film_id=case.input.film_id,
                source_type="evaluation",
                source_instance_id="gate-b.public",
                source_item_key=f"eval:{case.case_id}",
                display_name=case.input.canonical_title,
                availability_status="available",
                resolution_status="matched",
                metadata_source="curated",
                scrape_status="matched",
                added_at=now,
                last_seen_at=now,
            ))
            # Keep the fixture seed deterministic even though the ORM models do
            # not declare relationships that would otherwise guide flush order.
            session.flush()
            session.add(LegacyMovieAlias(
                legacy_movie_id=case.case_id,
                film_id=case.input.film_id,
                library_item_id=item_id,
                legacy_library_status="available",
            ))
            for expected in case.expected_assertions:
                target_key = _target_reference_key(expected.target.model_dump(mode="json", exclude_none=True))
                target_id = target_entities.get(target_key)
                if target_id is None:
                    if expected.target.entity_type == "film":
                        if expected.target.provider and expected.target.external_id:
                            existing = session.exec(
                                select(ExternalIdentity)
                                .where(ExternalIdentity.provider == expected.target.provider)
                                .where(ExternalIdentity.external_id == expected.target.external_id)
                            ).first()
                            if existing is not None:
                                target_id = existing.entity_id
                            else:
                                target_id = _stable_id("film", target_key)
                                _seed_film(
                                    session,
                                    target_id,
                                    expected.target.display_name or "Evaluation Film",
                                    expected.target.release_year,
                                    now,
                                )
                                _seed_identity(
                                    session,
                                    target_id,
                                    expected.target.provider,
                                    expected.target.external_id,
                                    now,
                                )
                        else:
                            target_id = _stable_id("film", target_key)
                            _seed_film(
                                session,
                                target_id,
                                expected.target.display_name or "Evaluation Film",
                                expected.target.release_year,
                                now,
                            )
                    else:
                        kind = _concept_kind(expected.predicate.value)
                        target_id = _seed_concept(
                            session,
                            kind,
                            expected.target.display_name or "Evaluation Concept",
                            now,
                        )
                    target_entities[target_key] = target_id
                if expected.target.entity_type == "concept" and expected.target_aliases:
                    _seed_concept_aliases(session, target_id, expected.target_aliases, now)
        session.commit()


def _exercise_persistence(engine, dataset: AnalysisEvaluationDataset) -> dict[str, Any]:
    case = dataset.cases[0]
    expected = next(item for item in case.expected_assertions if item.label == "required")
    output_payload = {
        "subject_film_id": case.input.film_id,
        "summary": "Synthetic public rehearsal summary.",
        "assertions": [{
            **expected.model_dump(
                mode="json",
                exclude={"label", "note", "target_aliases"},
                exclude_none=True,
            ),
            "rationale": "Synthetic bounded rationale for persistence rehearsal.",
            "evidence_candidates": [{
                "source_title": "Synthetic public catalog",
                "source_uri": "https://example.com/gate-b-evidence",
                "publisher": "Example",
                "claim": "Synthetic policy-safe claim.",
            }],
        }],
    }
    output = AnalysisV2Output.model_validate(output_payload)
    historian = _FixtureHistorian("fixture-v1", output)
    evidence = _FixtureEvidence()
    service = AnalysisService(
        database_engine=engine,
        historian=historian,
        tmdb=_UnconfiguredTMDB(),
        evidence=evidence,
    )
    first = service.analyze_movie(case.case_id)
    with Session(engine) as session:
        first_counts = _table_counts(session, W4_TABLES)
    second = service.analyze_movie(case.case_id)
    with Session(engine) as session:
        replay_counts = _table_counts(session, W4_TABLES)
        assertion = session.exec(
            select(Assertion)
            .where(Assertion.predicate == expected.predicate.value)
            .where(Assertion.source_scope == "inferred")
        ).one()
        assertion.review_status = "rejected"
        assertion.review_method = "user"
        assertion.reviewed_by_profile_id = "profile_gate_b"
        assertion.reviewed_at = datetime.now(timezone.utc).isoformat()
        assertion.rationale = "Synthetic user-owned rejection rationale."
        session.add(assertion)
        session.commit()
        assertion_id = assertion.id
        protected = (
            assertion.review_status,
            assertion.review_method,
            assertion.reviewed_by_profile_id,
            assertion.reviewed_at,
            assertion.rationale,
        )

    historian.model = "fixture-v2"
    service.analyze_movie(case.case_id)
    with Session(engine) as session:
        assertion = session.get(Assertion, assertion_id)
        after = (
            assertion.review_status,
            assertion.review_method,
            assertion.reviewed_by_profile_id,
            assertion.reviewed_at,
            assertion.rationale,
        )
        link = session.exec(select(AssertionEvidence).where(AssertionEvidence.assertion_id == assertion.id)).one()
        link.link_status = "revoked"
        link.revoked_at = datetime.now(timezone.utc).isoformat()
        session.add(link)
        session.commit()

    historian.model = "fixture-v3"
    service.analyze_movie(case.case_id)
    with Session(engine) as session:
        link = session.exec(select(AssertionEvidence).where(AssertionEvidence.assertion_id == assertion_id)).one()
        revoked_preserved = link.link_status == "revoked" and link.revoked_at is not None

    unresolved = AnalysisV2Output.model_validate({
        "subject_film_id": case.input.film_id,
        "summary": "Synthetic unresolved-reference rehearsal.",
        "assertions": [{
            "predicate": "HAS_THEME",
            "target": {"entity_type": "concept", "display_name": "Missing Gate B Concept"},
            "rationale": "This deliberately unresolved concept must enter review.",
        }],
    })
    historian.output = unresolved
    historian.model = "fixture-v4"
    service.analyze_movie(case.case_id)
    with Session(engine) as session:
        review_exists = session.exec(
            select(AnalysisResolutionReview)
            .where(AnalysisResolutionReview.film_id == case.input.film_id)
            .where(AnalysisResolutionReview.status == "open")
        ).first() is not None
    replay_new = sum(max(0, replay_counts[name] - first_counts[name]) for name in W4_TABLES)
    rejected_reactivated = int(protected[0] == "rejected" and after[0] != "rejected")
    review_field_changes = sum(left != right for left, right in zip(protected, after, strict=True))
    passed = (
        first.get("cached") is False
        and second.get("cached") is True
        and replay_new == 0
        and rejected_reactivated == 0
        and review_field_changes == 0
        and revoked_preserved
        and review_exists
    )
    return {
        "persistence_passed": passed,
        "replay_new_row_count": replay_new,
        "rejected_reactivation_count": rejected_reactivated,
        "review_field_change_count": review_field_changes,
        "revoked_link_reactivation_count": 0 if revoked_preserved else 1,
        "revoked_link_preserved": revoked_preserved,
        "unresolved_review_created": review_exists,
    }


def _synthetic_case_results(
    dataset: AnalysisEvaluationDataset,
    policy: Mapping[str, Any],
) -> list[dict[str, Any]]:
    results = []
    priority = set(policy["priority_evidence_predicates"])
    for case in dataset.cases:
        predictions = []
        for expected in case.expected_assertions:
            if expected.label != "required":
                continue
            candidate = {
                **expected.model_dump(
                    mode="json",
                    exclude={"label", "note", "target_aliases"},
                    exclude_none=True,
                ),
                "rationale": "Synthetic scorer rehearsal rationale.",
            }
            predictions.append({
                "prediction_hash": prediction_hash(candidate),
                "candidate": candidate,
                "expected_label": "required",
                "resolution_status": "resolved",
                "resolution_correct": True,
                "review_created": False,
                "invented_entity": False,
                "identity_consistent": True,
                "review_reason": None,
                "evidence": ([{
                    "active": True,
                    "fresh": True,
                    "stance": "supports",
                    "policy_version": policy["evidence_policy_version"],
                }] if expected.predicate.value in priority else []),
            })
        results.append({
            "case_id": case.case_id,
            "status": "succeeded",
            "summary": "Synthetic scorer rehearsal summary.",
            "expected_assertions": [
                item.model_dump(mode="json", exclude_none=True)
                for item in case.expected_assertions
            ],
            "predictions": predictions,
            "input_tokens": 1,
            "output_tokens": 1,
            "cost_usd": 0.0,
        })
    return results


def _collect_live_case_result(engine, case, historian, pricing, policy) -> dict[str, Any]:
    generation = historian.generations.get(case.input.film_id)
    if generation is None:
        return _failed_case_result(case, "validated_output_missing")
    with Session(engine) as session:
        run = session.exec(
            select(AnalysisRun)
            .where(AnalysisRun.film_id == case.input.film_id)
            .where(AnalysisRun.model == historian.model)
            .order_by(AnalysisRun.created_at.desc())
        ).first()
        if run is None or run.status != "succeeded":
            return _failed_case_result(case, "analysis_run_missing")
        provenance = session.exec(
            select(AssertionProvenance).where(AssertionProvenance.analysis_run_id == run.id)
        ).all()
        assertions_by_hash = {
            item.source_payload_hash: session.get(Assertion, item.assertion_id)
            for item in provenance
            if item.source_payload_hash
        }
        reviews = session.exec(
            select(AnalysisResolutionReview)
            .where(AnalysisResolutionReview.analysis_run_id == run.id)
            .where(AnalysisResolutionReview.candidate_kind == "assertion")
        ).all()
        reviews_by_key = {
            assertion_match_key(review.candidate_summary or {}): review
            for review in reviews
        }
        expected_labels = {
            key: item.label
            for item in case.expected_assertions
            for key in assertion_match_keys(item)
        }
        predictions = []
        finished_at = _parse_datetime(run.finished_at) or datetime.now(timezone.utc)
        for candidate in generation.output.assertions:
            candidate_payload = candidate.model_dump(mode="json", exclude_none=True)
            payload_hash = canonical_json_hash(candidate_payload)
            assertion = assertions_by_hash.get(payload_hash)
            review = reviews_by_key.get(assertion_match_key(candidate_payload))
            evidence_rows = []
            if assertion is not None:
                for link in session.exec(
                    select(AssertionEvidence).where(AssertionEvidence.assertion_id == assertion.id)
                ).all():
                    evidence = session.get(Evidence, link.evidence_id)
                    if evidence is None:
                        continue
                    retrieved = _parse_datetime(evidence.retrieved_at)
                    fresh = bool(
                        retrieved
                        and 0 <= (finished_at - retrieved).total_seconds()
                        <= int(policy["thresholds"]["evidence_freshness_days"]) * 86400
                    )
                    evidence_rows.append({
                        "active": link.link_status == "active",
                        "fresh": fresh,
                        "stance": link.stance,
                        "policy_version": evidence.verification_policy_version,
                    })
            key = assertion_match_key(candidate_payload)
            expected_match_key = key if key in expected_labels else None
            target = candidate_payload.get("target") or {}
            if (
                expected_match_key is None
                and assertion is not None
                and target.get("entity_type") == "concept"
                and target.get("entity_id")
            ):
                direction = candidate_payload.get("direction") or "subject_to_target"
                target_entity_id = (
                    assertion.object_entity_id
                    if direction == "subject_to_target"
                    else assertion.subject_entity_id
                )
                concept = session.get(Concept, target_entity_id)
                if concept is not None:
                    named_candidate = {
                        **candidate_payload,
                        "target": {
                            "entity_type": "concept",
                            "display_name": concept.canonical_name,
                        },
                    }
                    named_key = assertion_match_key(named_candidate)
                    if named_key in expected_labels:
                        expected_match_key = named_key
            identity_consistent = (
                _assertion_target_matches(session, assertion, candidate_payload, run.film_id)
                if assertion is not None
                else None
            )
            predictions.append({
                "prediction_hash": prediction_hash(candidate_payload),
                "candidate": candidate_payload,
                "expected_label": expected_labels.get(expected_match_key or key),
                "expected_match_key": expected_match_key,
                "resolution_status": "resolved" if assertion is not None else "review",
                "resolution_correct": (
                    identity_consistent
                    if assertion is not None
                    else key not in expected_labels
                ),
                "review_created": review is not None if assertion is None else False,
                "invented_entity": False,
                "identity_consistent": identity_consistent,
                "review_reason": review.reason_code if review is not None else None,
                "evidence": evidence_rows,
            })
        cost = run.estimated_cost
        if cost is None and run.input_tokens is not None and run.output_tokens is not None:
            cost = (
                run.input_tokens * pricing.input_usd_per_million
                + run.output_tokens * pricing.output_usd_per_million
            ) / 1_000_000
        return {
            "case_id": case.case_id,
            "status": "succeeded",
            "summary": generation.output.summary,
            "expected_assertions": [
                item.model_dump(mode="json", exclude_none=True)
                for item in case.expected_assertions
            ],
            "predictions": predictions,
            "input_tokens": run.input_tokens,
            "output_tokens": run.output_tokens,
            "cost_usd": cost,
        }


def _assertion_target_matches(
    session: Session,
    assertion: Assertion,
    candidate: Mapping[str, Any],
    subject_film_id: str,
) -> bool:
    direction = candidate.get("direction") or "subject_to_target"
    target_entity_id = (
        assertion.object_entity_id
        if direction == "subject_to_target"
        else assertion.subject_entity_id
    )
    if target_entity_id == subject_film_id:
        return False
    target = candidate.get("target") or {}
    if target.get("entity_id") and target_entity_id != target["entity_id"]:
        return False
    if target.get("provider") and target.get("external_id"):
        identity = session.exec(
            select(ExternalIdentity)
            .where(ExternalIdentity.provider == target["provider"])
            .where(ExternalIdentity.external_id == target["external_id"])
            .where(ExternalIdentity.identity_status == "active")
        ).first()
        if identity is None or identity.entity_id != target_entity_id:
            return False
    if target.get("entity_type") == "film":
        return _film_target_metadata_matches(session, target_entity_id, target)
    concept = session.get(Concept, target_entity_id)
    if concept is None or concept.kind != _concept_kind(str(candidate.get("predicate") or "")):
        return False
    display_name = str(target.get("display_name") or "").strip()
    if not display_name:
        return bool(target.get("entity_id") == target_entity_id)
    normalized_target = normalize_metadata_text(display_name)
    if normalize_metadata_text(concept.canonical_name) == normalized_target:
        return True
    alias = session.exec(
        select(ConceptAlias)
        .where(ConceptAlias.concept_id == concept.id)
        .where(ConceptAlias.normalized_alias == normalized_target)
    ).first()
    return alias is not None


def _film_target_metadata_matches(
    session: Session,
    target_entity_id: str,
    target: Mapping[str, Any],
) -> bool:
    film = session.get(Film, target_entity_id)
    if film is None:
        return False
    release_year = target.get("release_year")
    if release_year is not None and film.release_year != release_year:
        return False
    display_name = str(target.get("display_name") or "").strip()
    if not display_name:
        return True
    normalized = normalize_metadata_text(display_name)
    known_titles = {
        normalize_metadata_text(film.canonical_title),
        normalize_metadata_text(film.original_title or ""),
    }
    known_titles.update(
        item.normalized_title
        for item in session.exec(
            select(FilmTitle)
            .where(FilmTitle.film_id == target_entity_id)
            .where(FilmTitle.superseded_at.is_(None))
        ).all()
    )
    return normalized in known_titles


def _live_operational_checks(engine, dataset, service) -> dict[str, Any]:
    first_case = dataset.cases[0]
    with Session(engine) as session:
        before = _table_counts(session, W4_TABLES)
        run = session.exec(
            select(AnalysisRun)
            .where(AnalysisRun.film_id == first_case.input.film_id)
            .where(AnalysisRun.status == "succeeded")
            .order_by(AnalysisRun.finished_at.desc())
        ).first()
        provenance = session.exec(
            select(AssertionProvenance)
            .where(AssertionProvenance.analysis_run_id == (run.id if run else ""))
        ).first()
        assertion = session.get(Assertion, provenance.assertion_id) if provenance else None
        assertion_id = assertion.id if assertion else None
        protected = None
        link_id = None
        if assertion is not None:
            assertion.review_status = "rejected"
            assertion.review_method = "user"
            assertion.review_policy_version = None
            assertion.reviewed_by_profile_id = "profile_gate_b"
            assertion.reviewed_at = datetime.now(timezone.utc).isoformat()
            assertion.rationale = "Synthetic Gate B rejection-protection check."
            session.add(assertion)
            protected = (
                assertion.review_status,
                assertion.review_method,
                assertion.reviewed_by_profile_id,
                assertion.reviewed_at,
                assertion.rationale,
            )
        link = session.exec(
            select(AssertionEvidence).where(AssertionEvidence.link_status == "active")
        ).first()
        if link is not None:
            link.link_status = "revoked"
            link.revoked_at = datetime.now(timezone.utc).isoformat()
            session.add(link)
            link_id = link.id
        session.commit()
    try:
        service.analyze_movie(first_case.case_id)
    except AnalysisExecutionError:
        pass
    with Session(engine) as session:
        after = _table_counts(session, W4_TABLES)
        current = session.get(Assertion, assertion_id) if assertion_id else None
        current_fields = (
            (
                current.review_status,
                current.review_method,
                current.reviewed_by_profile_id,
                current.reviewed_at,
                current.rationale,
            )
            if current is not None
            else None
        )
        current_link = session.get(AssertionEvidence, link_id) if link_id else None
    return {
        "replay_new_row_count": sum(max(0, after[name] - before[name]) for name in W4_TABLES),
        "rejected_reactivation_count": int(
            current is None or current.review_status != "rejected"
        ),
        "review_field_change_count": (
            sum(left != right for left, right in zip(protected, current_fields, strict=True))
            if protected is not None and current_fields is not None
            else 1
        ),
        "revoked_link_reactivation_count": int(
            current_link is None or current_link.link_status != "revoked"
        ),
        "restore_equal": False,
        "privacy_leak_count": 0,
    }


class _PinnedHistorian:
    def __init__(
        self,
        provider: str,
        model: str,
        *,
        reasoning_effort: str | None = None,
        max_output_tokens: int | None = None,
    ) -> None:
        self.provider = provider
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.max_output_tokens = max_output_tokens
        self.delegate = FilmHistorian(
            client_factory=lambda: OpenAI(
                api_key=os.environ["OPENROUTER_API_KEY"],
                base_url="https://openrouter.ai/api/v1",
            )
        )
        self.generations: dict[str, AnalysisGenerationResult] = {}

    def analysis_configuration(self) -> AnalysisModelConfiguration:
        return AnalysisModelConfiguration(
            self.provider,
            self.model,
            reasoning_effort=self.reasoning_effort,
            max_output_tokens=self.max_output_tokens,
        )

    def analyze_v2(self, analysis_input, *, configuration=None):
        result = self.delegate.analyze_v2(
            analysis_input,
            configuration=self.analysis_configuration(),
        )
        self.generations[analysis_input.film_id] = result
        return result


class _FixtureHistorian:
    def __init__(self, model: str, output: AnalysisV2Output) -> None:
        self.model = model
        self.output = output

    def analysis_configuration(self) -> AnalysisModelConfiguration:
        return AnalysisModelConfiguration("openai_compatible", self.model)

    def analyze_v2(self, _analysis_input, *, configuration=None):
        return AnalysisGenerationResult(self.output, 1, 1, 0.0, "USD")


class _FixtureEvidence:
    def verify(self, candidates):
        verified = tuple(
            VerifiedEvidenceCandidate(
                candidate_key=key,
                candidate=candidate,
                source_uri=str(candidate.source_uri),
                content_hash=hashlib.sha256(str(candidate.source_uri).encode("utf-8")).hexdigest(),
                retrieved_at=datetime.now(timezone.utc).isoformat(),
            )
            for key, candidate in sorted(candidates.items())
        )
        return EvidenceBatchResult(verified, ())


class _UnconfiguredTMDB:
    @staticmethod
    def is_configured() -> bool:
        return False


def _seed_film(session: Session, film_id: str, title: str, year: int | None, now: str) -> None:
    if session.get(Film, film_id) is not None:
        return
    session.add(GraphEntity(id=film_id, entity_type="film", created_at=now, updated_at=now))
    session.flush()
    session.add(Film(
        id=film_id,
        canonical_title=title[:300],
        release_year=year,
        lifecycle_status="active",
        created_at=now,
        updated_at=now,
    ))
    session.flush()


def _seed_identity(session: Session, entity_id: str, provider: str, external_id: str, now: str) -> None:
    existing = session.exec(
        select(ExternalIdentity)
        .where(ExternalIdentity.provider == provider)
        .where(ExternalIdentity.external_id == external_id)
    ).first()
    if existing is not None:
        return
    session.add(ExternalIdentity(
        id=_stable_id("identity", f"{provider}:{external_id}"),
        entity_id=entity_id,
        provider=provider,
        external_id=external_id,
        identity_status="active",
        verified_at=now,
        provenance_kind="evaluation",
        provenance_ref="gate-b-dataset.v1",
        created_at=now,
        updated_at=now,
    ))


def _seed_concept(session: Session, kind: str, name: str, now: str) -> str:
    canonical_key = f"gate-b.{kind}.{normalize_metadata_text(name)}"
    existing = session.exec(
        select(Concept).where(Concept.kind == kind).where(Concept.canonical_key == canonical_key)
    ).first()
    if existing is not None:
        return existing.id
    concept_id = _stable_id("concept", canonical_key)
    session.add(GraphEntity(id=concept_id, entity_type="concept", created_at=now, updated_at=now))
    session.flush()
    session.add(Concept(
        id=concept_id,
        kind=kind,
        canonical_key=canonical_key,
        canonical_name=name[:300],
        lifecycle_status="active",
        created_at=now,
        updated_at=now,
    ))
    session.flush()
    return concept_id


def _seed_concept_aliases(
    session: Session,
    concept_id: str,
    aliases: Sequence[str],
    now: str,
) -> None:
    for alias in aliases:
        normalized = normalize_metadata_text(alias)
        existing = session.exec(
            select(ConceptAlias)
            .where(ConceptAlias.concept_id == concept_id)
            .where(ConceptAlias.locale == "und")
            .where(ConceptAlias.normalized_alias == normalized)
        ).first()
        if existing is not None:
            continue
        session.add(ConceptAlias(
            id=_stable_id("conceptalias", f"{concept_id}:und:{normalized}"),
            concept_id=concept_id,
            locale="und",
            alias=alias[:300],
            normalized_alias=normalized,
            provenance_ref="gate-b-dataset.v1",
            created_at=now,
            updated_at=now,
        ))


def _concept_kind(predicate: str) -> str:
    return {
        "HAS_THEME": "theme",
        "HAS_MOVEMENT": "movement",
        "HAS_VISUAL_STYLE": "visual_style",
        "HAS_MICRO_GENRE": "micro_genre",
    }.get(predicate, "theme")


def _target_reference_key(target: Mapping[str, Any]) -> str:
    if target.get("provider") and target.get("external_id"):
        return f"{target['provider']}:{target['external_id']}"
    return (
        f"{target.get('entity_type')}:{normalize_metadata_text(str(target.get('display_name') or ''))}:"
        f"{target.get('release_year') or ''}"
    )


def _stable_id(prefix: str, value: str) -> str:
    return f"{prefix}_{hashlib.sha256(value.encode('utf-8')).hexdigest()[:32]}"


def _load_pricing(path: Path, *, provider: str, model: str, blockers: list[str]) -> GateBPricingManifest | None:
    path = path.resolve()
    pricing_root = (_backend_root() / "data" / "analysis-v2" / "gate-b" / "input").resolve()
    if not path.is_file() or not path.is_relative_to(pricing_root):
        blockers.append("pricing_manifest_missing_or_invalid")
        return None
    try:
        pricing = GateBPricingManifest.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError):
        blockers.append("pricing_manifest_missing_or_invalid")
        return None
    if pricing.provider != provider or pricing.model != model:
        blockers.append("pricing_manifest_model_mismatch")
    return pricing


def _blocked_live_report(
    dataset,
    policy,
    run_dir,
    provider,
    model,
    pricing,
    blockers,
    *,
    reasoning_effort=None,
    max_output_tokens=None,
):
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "run_id": run_dir.name,
        "dataset_id": dataset.dataset_id,
        "dataset_hash": dataset_hash(dataset),
        "policy_version": policy["format_version"],
        "model_snapshot": {
            "provider": provider or None,
            "model": model or None,
            "reasoning_effort": reasoning_effort,
            "max_output_tokens": max_output_tokens,
        },
        "pricing_hash": canonical_json_hash(pricing.model_dump(mode="json")) if pricing else None,
        "checks": [
            _check(f"live-preflight-{reason.replace('_', '-')}", False, blocked=True)
            for reason in blockers
        ],
        "metrics": {},
        "phases": {"preflight": "blocked", "live": "blocked", "human": "blocked"},
        "cases": [],
        "operational_metrics": {},
        "tool_status": "passed",
        "live_status": "blocked",
        "human_status": "blocked",
        "overall_status": "blocked",
    }


def _failed_case_result(case, code: str) -> dict[str, Any]:
    return {
        "case_id": case.case_id,
        "status": "failed",
        "error_code": code,
        "expected_assertions": [item.model_dump(mode="json", exclude_none=True) for item in case.expected_assertions],
        "predictions": [],
        "input_tokens": None,
        "output_tokens": None,
        "cost_usd": None,
    }


def _validate_run_dir(run_dir: Path) -> Path:
    run_dir = run_dir.resolve()
    runs_root = (_backend_root() / "data" / "analysis-v2" / "gate-b" / "runs").resolve()
    runs_root.mkdir(parents=True, exist_ok=True)
    if run_dir == runs_root or not run_dir.is_relative_to(runs_root):
        raise GateBValidationError("Gate B run directory is outside the isolated runs root")
    if run_dir.exists():
        raise GateBValidationError("Gate B run directory already exists")
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,80}", run_dir.name):
        raise GateBValidationError("Gate B run ID is invalid")
    return run_dir


def _default_policy_path(dataset_path: Path) -> Path:
    return dataset_path.resolve().parent / "gate-b-policy-v2.json"


def _default_policy_path_from_report(report_path: Path) -> Path:
    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        payload = {}
    version = payload.get("policy_version")
    filename = "gate-b-policy-v1.json" if version == "gate-b-policy.v1" else "gate-b-policy-v2.json"
    return _backend_root() / "fixtures" / "analysis_v2" / filename


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _read_report(path: Path) -> dict[str, Any]:
    path = path.resolve()
    runs_root = (_backend_root() / "data" / "analysis-v2" / "gate-b" / "runs").resolve()
    if (
        path.name != "run-report.json"
        or path.parent.parent != runs_root
    ):
        raise GateBValidationError("Gate B run report is outside the isolated runs root")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GateBValidationError("Gate B run report is invalid") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != REPORT_SCHEMA_VERSION:
        raise GateBValidationError("Gate B run report schema is unsupported")
    for field in ("run_id", "dataset_id", "dataset_hash", "policy_version"):
        if not payload.get(field):
            raise GateBValidationError(f"Gate B run report is missing {field}")
    if payload["run_id"] != path.parent.name:
        raise GateBValidationError("Gate B run report ID does not match its run directory")
    for field in ("tool_status", "live_status", "human_status", "overall_status"):
        if payload.get(field) not in VALID_STATUSES:
            raise GateBValidationError(f"Gate B run report has invalid {field}")
    return payload


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _privacy_leaks(payload: Any) -> list[str]:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).casefold()
    leaks = [canary for canary in SENSITIVE_CANARIES if canary.casefold() in serialized]
    path_patterns = (r"[a-z]:\\(?:users|home|gatebprivate)\\", r"/(?:home|users)/[^/]+/")
    leaks.extend(pattern for pattern in path_patterns if re.search(pattern, serialized))
    credential_patterns = ("api_key", "authorization", "bearer ")
    leaks.extend(pattern for pattern in credential_patterns if pattern in serialized)
    return sorted(set(leaks))


def _database_privacy_leak_count(path: Path) -> int:
    data = path.read_bytes().decode("utf-8", errors="ignore").casefold()
    return sum(canary.casefold() in data for canary in SENSITIVE_CANARIES)


def _w4_digest(path: Path) -> str:
    uri = f"{path.resolve().as_uri()}?mode=ro"
    parts: list[Any] = []
    with closing(sqlite3.connect(uri, uri=True, timeout=30)) as connection:
        for table in W4_TABLES:
            columns = [row[1] for row in connection.execute(f"PRAGMA table_info({table})")]
            order = "id" if "id" in columns else columns[0]
            rows = connection.execute(f"SELECT * FROM {table} ORDER BY {order}").fetchall()
            parts.append((table, rows))
        journal = connection.execute(
            "SELECT version, name, checksum, status FROM schema_migrations ORDER BY version"
        ).fetchall()
        parts.append(("schema_migrations", journal))
    return canonical_json_hash(parts)


def _schema_version(path: Path) -> int:
    uri = f"{path.resolve().as_uri()}?mode=ro"
    with closing(sqlite3.connect(uri, uri=True, timeout=30)) as connection:
        row = connection.execute(
            "SELECT COALESCE(MAX(version), 0) FROM schema_migrations WHERE status='applied'"
        ).fetchone()
    return int(row[0] or 0)


def _table_counts(session: Session, tables: Sequence[str]) -> dict[str, int]:
    return {
        table: int(session.exec(text(f"SELECT COUNT(*) FROM {table}")).one()[0])
        for table in tables
    }


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _percentile(values: Sequence[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int((len(ordered) - 1) * quantile + 0.999999)))
    return round(float(ordered[index]), 8)


def _ratio(numerator: int, denominator: int) -> float:
    return 1.0 if denominator == 0 else round(numerator / denominator, 8)


def _check(check_id: str, passed: bool, *, blocked: bool = False) -> dict[str, Any]:
    return {"id": check_id, "status": "blocked" if blocked else "passed" if passed else "failed"}


def _threshold_check(check_id, metrics, thresholds, field, minimum=False):
    actual = metrics.get(field)
    expected = thresholds[field]
    if actual is None:
        return _check(check_id, False, blocked=True)
    passed = actual >= expected if minimum else actual <= expected
    return {"id": check_id, "status": "passed" if passed else "failed", "actual": actual, "threshold": expected}


def _phase_status(checks: Sequence[Mapping[str, Any]]) -> str:
    statuses = {str(check.get("status")) for check in checks}
    if "failed" in statuses:
        return "failed"
    if "blocked" in statuses:
        return "blocked"
    return "passed"


def _tool_status(phases: Mapping[str, str]) -> str:
    local = [phases.get(name) for name in ("preflight", "dataset", "persistence", "scoring", "restore", "privacy")]
    if "failed" in local:
        return "failed"
    return "passed" if all(status == "passed" for status in local) else "blocked"


def _exit_code(status: str) -> int:
    return {"passed": 0, "failed": 2, "blocked": 3}[status]


def _cli_summary(payload: Mapping[str, Any]) -> dict[str, Any]:
    fields = (
        "schema_version",
        "run_id",
        "dataset_id",
        "dataset_hash",
        "policy_version",
        "validation_status",
        "adjudication_ready",
        "tool_status",
        "live_status",
        "human_status",
        "diagnostic_status",
        "overall_status",
        "output",
        "case_count",
        "case_limit",
    )
    return {field: payload[field] for field in fields if field in payload}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the 5X49 Analysis V2 Gate B evaluation")
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate", help="Validate the fixed Gate B dataset")
    validate.add_argument("--dataset", required=True, type=Path)
    validate.add_argument("--policy", type=Path)
    rehearse = subparsers.add_parser("rehearse", help="Run the offline Gate B tooling rehearsal")
    rehearse.add_argument("--dataset", required=True, type=Path)
    rehearse.add_argument("--run-dir", required=True, type=Path)
    rehearse.add_argument("--policy", type=Path)
    live = subparsers.add_parser("run", help="Run the strict live model evaluation")
    live.add_argument("--dataset", required=True, type=Path)
    live.add_argument("--run-dir", required=True, type=Path)
    live.add_argument("--provider", required=True, choices=("openrouter",))
    live.add_argument("--model", required=True)
    live.add_argument("--pricing-file", required=True, type=Path)
    live.add_argument("--allow-public-network", action="store_true")
    live.add_argument(
        "--reasoning-effort",
        choices=("low", "medium", "high", "max"),
    )
    live.add_argument("--max-output-tokens", type=int)
    live.add_argument("--policy", type=Path)
    pilot = subparsers.add_parser(
        "pilot",
        help="Run a bounded tuning diagnostic that is never valid Gate B evidence",
    )
    pilot.add_argument("--dataset", required=True, type=Path)
    pilot.add_argument("--run-dir", required=True, type=Path)
    pilot.add_argument("--provider", required=True, choices=("openrouter",))
    pilot.add_argument("--model", required=True)
    pilot.add_argument("--pricing-file", required=True, type=Path)
    pilot.add_argument("--allow-public-network", action="store_true")
    pilot.add_argument("--case-limit", type=int, default=6)
    pilot.add_argument(
        "--reasoning-effort",
        choices=("low", "medium", "high", "max"),
    )
    pilot.add_argument("--max-output-tokens", type=int)
    pilot.add_argument("--policy", type=Path)
    review = subparsers.add_parser("review-template", help="Create the bounded human review template")
    review.add_argument("--run-report", required=True, type=Path)
    review.add_argument("--output", required=True, type=Path)
    conclude_parser = subparsers.add_parser("conclude", help="Conclude strict Gate B evidence")
    conclude_parser.add_argument("--run-report", required=True, type=Path)
    conclude_parser.add_argument("--human-review", required=True, type=Path)
    conclude_parser.add_argument("--policy", type=Path)
    args = parser.parse_args(argv)

    try:
        if args.command == "validate":
            dataset = load_dataset(args.dataset)
            payload = validate_dataset(dataset, load_policy(args.policy or _default_policy_path(args.dataset)))
        elif args.command == "rehearse":
            payload = run_rehearsal(args.dataset, args.run_dir, policy_path=args.policy)
        elif args.command == "run":
            payload = run_live(
                args.dataset,
                args.run_dir,
                provider=args.provider,
                model=args.model,
                pricing_path=args.pricing_file,
                allow_public_network=args.allow_public_network,
                policy_path=args.policy,
                reasoning_effort=args.reasoning_effort,
                max_output_tokens=args.max_output_tokens,
            )
        elif args.command == "pilot":
            payload = run_pilot(
                args.dataset,
                args.run_dir,
                provider=args.provider,
                model=args.model,
                pricing_path=args.pricing_file,
                allow_public_network=args.allow_public_network,
                case_limit=args.case_limit,
                policy_path=args.policy,
                reasoning_effort=args.reasoning_effort,
                max_output_tokens=args.max_output_tokens,
            )
        elif args.command == "review-template":
            payload = create_review_template(args.run_report, args.output)
        elif args.command == "conclude":
            payload = conclude(args.run_report, args.human_review, policy_path=args.policy)
        else:  # pragma: no cover
            parser.error("unsupported command")
    except GateBBlocked as exc:
        print(f"Gate B blocked: {exc}", file=sys.stderr)
        return 3
    except GateBValidationError as exc:
        print(f"Gate B refused: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(_cli_summary(payload), ensure_ascii=True, indent=2, sort_keys=True))
    return _exit_code(str(payload.get("overall_status") or "blocked"))


if __name__ == "__main__":
    raise SystemExit(main())
