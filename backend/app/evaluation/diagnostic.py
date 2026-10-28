"""Offline diagnostic scoring. Never imports search, database or model clients."""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path

from .diagnostic_package import (FILES, GAINS, STAGES, VERSION, InvalidInput, Package,
    decode, eligible, finite_tree, load_package, require, review_register, sha256)

RUN_KEYS = frozenset({"query_id", "run_status", "observed_behavior", "clarification_text",
    "human_clarification_score", "human_review_note", "human_reviewer", "error",
    "scores", "latency_ms", "stage_status", "parsed_constraints", "filter_reasons", *STAGES})
METRICS = ("recall_at_20", "precision_at_5", "p5_ceiling_normalized", "ndcg_at_5",
           "answerable_hit_at_5", "false_empty", "unnecessary_clarification", "named_hard_negative_exposure_at_5")


def implementation_hashes():
    root = Path(__file__).parent
    return {name: sha256((root / name).read_bytes()) for name in ("diagnostic.py", "diagnostic_package.py")}


def _list_ids(value, name):
    require(isinstance(value, list) and len(value) <= 1000 and all(isinstance(x, str) and x for x in value), f"invalid {name} IDs")


def validate_results(package: Package, data: dict) -> tuple[dict, list[dict]]:
    finite_tree(data)
    require(isinstance(data, dict) and set(data) <= {"version", "status", "manifest_sha256", "runs"}, "invalid result schema")
    require(data.get("version") == VERSION, "result version mismatch")
    require(data.get("manifest_sha256") == package.binding, "result/package hash mismatch")
    require(data.get("status") in {"SIMULATED_RESULTS", "ACTUAL_RESULTS", "TEMPLATE_NOT_RESULTS"}, "unknown result provenance")
    runs = data.get("runs")
    require(isinstance(runs, list) and len(runs) <= 1000, "invalid runs")
    by_id, errors = {}, []
    for run in runs:
        require(isinstance(run, dict) and set(run) <= RUN_KEYS, "invalid run schema")
        require({"query_id", "run_status", "observed_behavior", "fused_ids", "displayed_ids", "clarification_text"} <= set(run), "missing required run fields")
        qid = run.get("query_id")
        require(isinstance(qid, str), "invalid query ID")
        if qid not in package.answers:
            errors.append({"query_id": qid, "code": "unknown_query"})
            continue
        if qid in by_id:
            errors.append({"query_id": qid, "code": "duplicate_query"})
            # Neither occurrence is trusted. Do not silently pick first/last.
            by_id[qid] = None
            continue
        by_id[qid] = run
        require(run.get("run_status") in {None, "not_run", "ok", "error"}, "unknown run status")
        require(run.get("observed_behavior") in {None, "ranked", "empty", "clarify"}, "unknown observed behavior")
        require(isinstance(run.get("clarification_text"), str), "missing/invalid clarification text")
        require(isinstance(run.get("human_review_note", ""), str), "invalid human review note")
        require(isinstance(run.get("human_reviewer", ""), str), "invalid reviewer")
        score = run.get("human_clarification_score")
        require(score is None or type(score) is int and 0 <= score <= 2, "invalid clarification score")
        require(run.get("run_status") != "ok" or run.get("observed_behavior") is not None, "successful run needs behavior")
        require(data["status"] != "TEMPLATE_NOT_RESULTS" or run.get("run_status") in {None, "not_run"}, "template cannot contain executed runs")
        for stage in STAGES:
            require(stage in run or stage not in {"fused_ids", "displayed_ids"}, "missing required candidate list")
            if stage not in run:
                continue
            values = run[stage]
            _list_ids(values, stage)
            seen = set()
            for position, fid in enumerate(values, 1):
                if fid not in package.index:
                    errors.append({"query_id": qid, "code": "unknown_candidate", "stage": stage, "position": position, "film_id": fid})
                if fid in seen:
                    errors.append({"query_id": qid, "code": "duplicate_candidate", "stage": stage, "position": position, "film_id": fid})
                seen.add(fid)
        scores = run.get("scores", {})
        require(isinstance(scores, dict) and set(scores) <= set(STAGES), "invalid score stages")
        for stage, values in scores.items():
            require(stage in run and isinstance(values, list) and len(values) == len(run[stage]), "score/list mapping mismatch")
            require(all(type(x) in {int, float} and math.isfinite(x) for x in values), "invalid finite numeric score")
        latency = run.get("latency_ms", {})
        require(isinstance(latency, dict) and all(type(v) in {int, float} and math.isfinite(v) and v >= 0 for v in latency.values()), "invalid latency")
        stage_status = run.get("stage_status", {})
        require(isinstance(stage_status, dict) and set(stage_status) <= set(STAGES)
                and all(s in {"ok", "error", "not_run"} for s in stage_status.values()), "invalid stage status")
        for stage in ("fused_ids", "displayed_ids"):
            if run["run_status"] == "ok" and stage_status.get(stage, "ok") != "ok":
                errors.append({"query_id": qid, "stage": stage, "code": "required_stage_not_successful"})
        reasons = run.get("filter_reasons", [])
        require(isinstance(reasons, list) and all(isinstance(r, dict) and set(r) == {"film_id", "reason"}
                and r["film_id"] in package.index and isinstance(r["reason"], str) for r in reasons), "invalid filter reasons")
        require(isinstance(run.get("parsed_constraints", {}), dict), "invalid parsed constraints")
        if run["run_status"] == "ok" and run["observed_behavior"] in {"empty", "clarify"} and run["displayed_ids"]:
            errors.append({"query_id": qid, "code": "behavior_contains_recommendations"})
    for qid in sorted(set(package.answers) - set(by_id)):
        errors.append({"query_id": qid, "code": "missing_query"})
    return by_id, errors


def _dcg(values):
    return sum(value / math.log2(position + 1) for position, value in enumerate(values[:5], 1))


def _slots(package, answer, displayed):
    judgments = {j["film_id"]: j for j in answer["judgments"]}
    slots, seen, violations = [], set(), []
    for position, fid in enumerate(displayed, 1):
        if fid not in judgments:
            slots.append({"position": position, "film_id": fid, "grade": None, "gain": None,
                          "violations": ["unknown_candidate"]})
            seen.add(fid)
            continue
        judgment = judgments[fid]
        reasons = []
        if fid in seen:
            reasons.append("duplicate_candidate")
        if fid == answer.get("reference_id"):
            reasons.append("excluded_reference")
        if not eligible(package.index[fid], answer) and "excluded_reference" not in reasons:
            reasons.append("hard_constraint_failed")
        if judgment.get("reason_code") == "hard_constraint_failed" and "hard_constraint_failed" not in reasons:
            reasons.append("hard_constraint_failed")
        grade = judgment["grade"]
        gain = None if grade is None else (0 if reasons else GAINS[grade])
        slots.append({"position": position, "film_id": fid, "grade": grade, "gain": gain, "violations": reasons})
        violations.extend({"position": position, "film_id": fid, "code": code} for code in reasons)
        seen.add(fid)
    return slots, violations


def _ranking(package, answer, run, slots):
    judgments = {j["film_id"]: j for j in answer["judgments"]}
    if any(j["grade"] is None for j in judgments.values()):
        return None
    relevant = {fid for fid, j in judgments.items() if j["grade"] >= 2}
    top = slots[:5]
    hits = {s["film_id"] for s in top if s["grade"] >= 2 and not s["violations"]}
    ideal = _dcg(sorted((GAINS[j["grade"]] for j in judgments.values()), reverse=True))
    require(ideal > 0 and relevant, "undefined answerable ideal ranking")
    named = any(judgments[s["film_id"]]["is_named_hard_negative"] for s in top)
    fused = {fid for fid in run["fused_ids"][:20] if eligible(package.index[fid], answer)
             and judgments[fid].get("reason_code") not in {"hard_constraint_failed", "excluded_reference"}}
    return {"recall_at_20": len(fused & relevant) / len(relevant),
            "precision_at_5": len(hits) / 5,
            "p5_ceiling_normalized": len(hits) / min(5, len(relevant)),
            "ndcg_at_5": _dcg([s["gain"] for s in top]) / ideal,
            "answerable_hit_at_5": int(bool(hits)), "false_empty": int(run["observed_behavior"] == "empty"),
            "unnecessary_clarification": int(run["observed_behavior"] == "clarify"),
            "named_hard_negative_exposure_at_5": int(named)}


def _stage_evidence(package, answer, run):
    if answer["expected_behavior"] != "ranked":
        return {"stages": {}, "observations": [], "unavailable": list(STAGES)}
    relevant = set(answer["relevant_ids"])
    if any(j["grade"] is None for j in answer["judgments"]):
        return {"stages": {}, "observations": [], "unavailable": list(STAGES), "note": "Unresolved judgments; stage metrics unavailable"}
    stages, unavailable = {}, []
    for stage in STAGES:
        if stage not in run or run.get("stage_status", {}).get(stage, "ok") != "ok":
            unavailable.append(stage)
            continue
        ids = run[stage]
        if any(fid not in package.index for fid in ids):
            unavailable.append(stage)
            continue
        retained = relevant & set(ids)
        stages[stage] = {"positions": len(ids), "unique_candidates": len(set(ids)),
                         "relevant_retained": len(retained), "relevant_total": len(relevant),
                         "recall_at_20": len(relevant & set(ids[:20])) / len(relevant)}
    observations = []
    if "fused_ids" in stages and stages["fused_ids"]["recall_at_20"] < 1:
        observations.append("relevant_missing_from_fused_top20")
    for before, after, label in (("fused_ids", "filtered_ids", "relevant_removed_at_filter_stage"),
                                 ("reranked_ids", "displayed_ids", "relevant_removed_at_display_stage")):
        if before in stages and after in stages and (relevant & set(run[before])) - set(run[after]):
            observations.append(label)
    if "reranked_ids" in stages and relevant & set(run["reranked_ids"]) and not relevant & set(run["reranked_ids"][:5]):
        observations.append("relevant_below_reranked_top5")
    return {"stages": stages, "observations": observations, "unavailable": unavailable,
            "note": "Observed set/position losses only; absent logs cannot establish data, intent or model causation"}


def score(package: Package, data: dict) -> dict:
    runs, errors = validate_results(package, data)
    rows = []
    for qid, answer in sorted(package.answers.items()):
        run = runs.get(qid)
        row = {"query_id": qid, "category": answer["category"], "expected_behavior": answer["expected_behavior"],
               "run_status": "missing" if qid not in runs else "invalid" if run is None else run.get("run_status") or "not_run",
               "metrics": None, "clarification_score": None, "hard_constraint_violations": [],
               "contract_valid": not any(e["query_id"] == qid for e in errors)}
        rows.append(row)
        if run is not None:
            row.update(observed_behavior=run["observed_behavior"], fused_ids=run["fused_ids"],
                       displayed_ids=run["displayed_ids"], error=run.get("error"), stage_status=run.get("stage_status", {}))
        if run is None or run.get("run_status") != "ok":
            continue
        row.update(observed_behavior=run["observed_behavior"], fused_ids=run["fused_ids"], displayed_ids=run["displayed_ids"],
                   stage_evidence=_stage_evidence(package, answer, run), clarification_text=run["clarification_text"])
        unknown = any(e["query_id"] == qid and e["code"] == "unknown_candidate" for e in errors)
        slots, violations = _slots(package, answer, run["displayed_ids"])
        row["display_slots"] = slots
        row["hard_constraint_violations"] = [v for v in violations if v["code"] in {"hard_constraint_failed", "excluded_reference"}]
        if unknown:
            row["unscored_reason"] = "unknown_candidate_invalidates_metrics"
            continue
        if answer["expected_behavior"] == "ranked":
            row["metrics"] = _ranking(package, answer, run, slots)
            if row["metrics"] is None:
                row["unscored_reason"] = "unresolved_null_judgment"
        elif answer["expected_behavior"] == "empty":
            row["metrics"] = {"noanswer_false_positive": int(bool(run["displayed_ids"])),
                              "noanswer_correct": int(run["observed_behavior"] == "empty" and not run["displayed_ids"])}
        else:
            if run["observed_behavior"] != "clarify" or run["displayed_ids"] or not run["clarification_text"].strip():
                row["clarification_score"] = 0
                row["clarification_score_source"] = "structural_behavior_failure"
            elif run.get("human_clarification_score") is not None:
                require(bool(run.get("human_review_note", "").strip()), "human clarification score needs a review note")
                row["clarification_score"] = run["human_clarification_score"]
                row["clarification_score_source"] = "simulated_review" if data["status"] == "SIMULATED_RESULTS" else "supplied_human_review_not_independently_verified"
                row["human_review_note"] = run["human_review_note"]
                row["human_reviewer"] = run.get("human_reviewer")
            else:
                row["unscored_reason"] = "human_clarification_review_pending"
    def aggregate(subset, kind, keys):
        population = [r for r in subset if r["expected_behavior"] == kind]
        measured = [r for r in population if r["metrics"] is not None and r["contract_valid"]]
        partial = {k: sum(r["metrics"][k] for r in measured) / len(measured) if measured else None for k in keys}
        return {"expected": len(population), "measured": len(measured), "complete": len(measured) == len(population),
                "macro": partial if len(measured) == len(population) else None, "partial_macro": partial,
                "numerators": {k: sum(r["metrics"][k] for r in measured) for k in keys if k not in {"recall_at_20", "precision_at_5", "p5_ceiling_normalized", "ndcg_at_5"}}}
    ranked = aggregate(rows, "ranked", METRICS)
    empty = aggregate(rows, "empty", ("noanswer_false_positive", "noanswer_correct"))
    clarify = [r for r in rows if r["expected_behavior"] == "clarify"]
    stage_summary = {}
    for stage in STAGES:
        values = [r["stage_evidence"]["stages"][stage]["recall_at_20"] for r in rows
                  if r["expected_behavior"] == "ranked" and r["contract_valid"]
                  and stage in r.get("stage_evidence", {}).get("stages", {})]
        stage_summary[stage] = {"expected": 15, "measured": len(values),
                                "partial_macro_recall_at_20": sum(values) / len(values) if values else None}
    complete = (not errors and all(r["run_status"] == "ok" for r in rows)
                and ranked["complete"] and empty["complete"] and all(r["clarification_score"] is not None for r in clarify))
    return {"report_version": "diagnostic-score-report.v1", "implementation_sha256": implementation_hashes(), "package_version": VERSION,
            "manifest_sha256": package.binding, "simulation": data["status"] == "SIMULATED_RESULTS",
            "run_provenance": data["status"], "run_counts": dict(Counter(r["run_status"] for r in rows)),
            "contract_errors": errors, "diagnostic_complete": complete, "official_aggregate_valid": False,
            "acceptance": "not_assessed", "limitations": ["Draft labels are not human gold; thresholds are uncalibrated proposals",
                "This is diagnostic scoring, not independent search-quality acceptance",
                "Null judgments and missing/error runs are not zero-relevance or correct empty answers"],
            "ranking": ranked, "empty": empty,
            "by_category": {c: aggregate([r for r in rows if r["category"] == c], "ranked", METRICS) for c in sorted({r["category"] for r in rows})},
            "clarification": {"expected": len(clarify), "reviewed_or_structurally_failed": sum(r["clarification_score"] is not None for r in clarify),
                "total": sum(r["clarification_score"] for r in clarify) if all(r["clarification_score"] is not None for r in clarify) else None,
                "partial_total": sum(r["clarification_score"] for r in clarify if r["clarification_score"] is not None), "maximum": len(clarify) * 2},
            "hard_constraint_violation_count": sum(len(r["hard_constraint_violations"]) for r in rows),
            "stage_summary": stage_summary, "review_summary": review_register(package)["summary"], "cases": rows}


def summary(report: dict) -> str:
    lines = ["SIMULATED — NOT SEARCH RESULTS" if report["simulation"] else "DIAGNOSTIC DRAFT — NOT QUALITY ACCEPTANCE",
             f"Version: {report['package_version']}; manifest: {report['manifest_sha256']}",
             f"Runs: {json.dumps(report['run_counts'], sort_keys=True)}; contract errors: {len(report['contract_errors'])}"]
    for label, group in (("Ranked", report["ranking"]), ("Conditional empty", report["empty"])):
        lines.append(f"{label}: measured {group['measured']}/{group['expected']}; complete macro: {json.dumps(group['macro'], sort_keys=True)}")
        lines.append(f"{label} event counts: {json.dumps(group['numerators'], sort_keys=True)}")
    for category, group in report["by_category"].items():
        lines.append(f"Category {category}: {group['measured']}/{group['expected']}; {json.dumps(group['macro'], sort_keys=True)}")
    for stage, group in report["stage_summary"].items():
        lines.append(f"Stage {stage}: logged {group['measured']}/{group['expected']}; partial recall@20 {group['partial_macro_recall_at_20']}")
    group = report["clarification"]
    lines += [f"Clarification: {group['reviewed_or_structurally_failed']}/{group['expected']} scored; total {group['total']}/{group['maximum']}",
              f"Confirmed hard-condition/reference violations: {report['hard_constraint_violation_count']}",
              "Official aggregate/acceptance: unavailable (draft labels, uncalibrated rules)."]
    return "\n".join(lines) + "\n"


def bound_template(package: Package) -> dict:
    value = decode(package.members["input/result-template.json"])
    require(value.get("version") == VERSION and value.get("status") == "TEMPLATE_NOT_RESULTS", "invalid supplied template")
    value["manifest_sha256"] = package.binding
    return value


def _write(path: Path, data: bytes, package_path: Path, results_path: Path | None = None):
    resolved = path.resolve()
    require(not (package_path.is_dir() and resolved.is_relative_to(package_path.resolve())), "output would alter frozen package")
    require(resolved != package_path.resolve() and (results_path is None or resolved != results_path.resolve()), "output would overwrite input")
    require(not path.exists(), "output already exists; choose a new version/path")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(data)


def _bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate-package", "freeze", "template", "score"))
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument("--results", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--summary", type=Path)
    args = parser.parse_args(argv)
    try:
        require(not args.summary or args.command == "score", "--summary requires score")
        require(not (args.output and args.summary and args.output.resolve() == args.summary.resolve()), "report and summary paths must differ")
        require(all(not p.exists() for p in (args.output, args.summary) if p is not None), "output already exists; choose a new version/path")
        package = load_package(args.package)
        if args.command == "validate-package":
            value = {"status": "valid_diagnostic_draft", "version": VERSION, "manifest_sha256": package.binding,
                     "queries": len(package.questions), "candidates": len(package.index), "pairs": 576,
                     "review_summary": review_register(package)["summary"]}
        elif args.command == "freeze":
            value = {"freeze_version": "diagnostic-freeze.v1", "package_version": VERSION, "manifest_sha256": package.binding,
                     "implementation_sha256": implementation_hashes(),
                     "file_hashes": {name: sha256(data) for name, data in sorted(package.members.items())},
                     "original_archive_sha256": package.original_archive_sha256,
                     "label_changes": [], "human_adjudication": False, "review_register": review_register(package)}
        elif args.command == "template":
            value = bound_template(package)
        else:
            require(args.results is not None, "score requires --results")
            results_bytes = args.results.read_bytes()
            value = score(package, decode(results_bytes))
            value["results_sha256"] = sha256(results_bytes)
        if args.output:
            _write(args.output, _bytes(value), args.package, args.results)
        else:
            print(_bytes(value).decode("utf-8"), end="")
        if args.summary:
            require(args.command == "score", "--summary requires score")
            _write(args.summary, summary(value).encode("utf-8"), args.package, args.results)
        return 0 if args.command != "score" or value["diagnostic_complete"] else 1
    except (InvalidInput, OSError, KeyError, TypeError, ValueError) as exc:
        print(json.dumps({"status": "invalid_input", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
