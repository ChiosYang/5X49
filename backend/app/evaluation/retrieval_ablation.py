"""Zero-HTTP diagnostic ablation of already recorded public vectors.

Never execute/extend a provider pilot. The known 24 cases are regression data,
not an independent test. Output goes to stdout; this module writes no run files.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from hashlib import sha256
import json
import math
from pathlib import Path
from statistics import median
from time import perf_counter

from app.evaluation import public_movie_pilot as historical
from app.evaluation.public_movies import hard_ids, score
from app.services.retrieval_policy import RetrievalIndex, RetrievalPolicy, VERSION
from app.services.semantic_search import SemanticError, _hash

ROOT = historical.BACKEND.parent
VECTOR_SHA = "e389c28c39f965d44ad403515f263488eaa3b18283601c24bab4a1758abd8b0d"
HISTORICAL_RESULTS = ROOT / "docs/evaluations/public-movies-v1-results.json"
STAGES = ("baseline", "candidates", "lexical", "admission")
METHODS = ("lexical", "dense", "hybrid")


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def average(rows, field):
    return sum(row[field] for row in rows) / len(rows) if rows else None


def aggregate(rows):
    answerable = [r for r in rows if r["expected_ids"]]
    no_answer = [r for r in rows if r["kind"] == "no_answer"]
    times = sorted(r["elapsed_ms"] for r in rows)
    return {
        "answerable_cases": len(answerable),
        "pure_ranking": {field: average(answerable, field) for field in
            ("top1_hit", "recall_at_3", "ndcg_at_10")},
        "candidate_recall": {str(k): average(answerable, f"candidate_recall_at_{k}") for k in (5, 10, 20)},
        "candidate_union_recall": average(answerable, "candidate_union_recall"),
        "answerable_false_abstentions": sum(not r["actual_ids"] for r in answerable),
        "no_answer_cases": len(no_answer),
        "no_answer_false_positives": sum(bool(r["actual_ids"]) for r in no_answer),
        "hard_condition_violations": sum(len(r["hard_condition_violations"]) for r in rows),
        "local_retrieval_median_ms": median(times) if times else None,
        "local_retrieval_p95_ms": times[math.ceil(len(times) * .95) - 1] if times else None,
    }


def summarize(rows):
    return {"all_semantic": aggregate(rows),
        "by_kind": {kind: aggregate([r for r in rows if r["kind"] == kind])
                    for kind in sorted({r["kind"] for r in rows})},
        "by_locale": {locale: aggregate([r for r in rows if r["locale"] == locale]) for locale in ("en", "zh")},
        "admission_reasons": dict(sorted(Counter(c["reason"] for r in rows for c in r["candidates"]).items())),
        "results": rows}


def case_row(case, actual, candidate_ids, *, candidates, elapsed_ms, mode):
    row = score(case, actual)
    expected = set(case.expected_ids)
    for k in (5, 10, 20):
        row[f"candidate_recall_at_{k}"] = len(set(candidate_ids[:k]) & expected) / len(expected) if expected else None
    row.update(candidate_union_recall=len(set(candidate_ids) & expected) / len(expected) if expected else None,
        candidate_ids=candidate_ids, candidates=candidates, elapsed_ms=elapsed_ms,
        question=case.question, reference_id=case.reference_id,
        intent_mode=mode, intent_source="existing fixture category annotation; not NLP inference")
    return row


def evaluate(fixture, vectors, baseline, *, policy=None):
    """All encodings must already exist. The supplied replay provider cannot call HTTP."""
    policy = policy or RetrievalPolicy()
    docs = tuple(f.document() for f in fixture.films)
    started = perf_counter()
    index = RetrievalIndex(docs,
        {film.id: vectors.embed([film.document_text], query=False)[0] for film in fixture.films},
        vectors.spec, policy)
    build_ms = (perf_counter() - started) * 1000
    semantic = [case for case in fixture.cases if case.kind not in {"identity", "hard_conditions"}]
    stages = {}
    for stage in STAGES:
        methods = {}
        for method in METHODS:
            original = {row["id"]: row for row in baseline[method]["results"]}
            rows = []
            for case in semantic:
                mode = "exploratory" if case.kind == "theme" else "factual"
                if stage == "baseline":
                    old = original[case.id]
                    ids = old["actual_ids"]
                    row = case_row(case, ids, ids, candidates=[{"film_id": key,
                        "reason": "historical_display_and_candidate_gate", "admitted": True} for key in ids],
                        elapsed_ms=old["elapsed_ms"], mode="historical unsplit retrieval")
                else:
                    query = vectors.embed([case.embedding_query], query=True)[0] if case.embedding_query is not None and method != "lexical" else None
                    started = perf_counter()
                    outcome = index.search(case.question, eligible_ids=case.allowed_ids, query_vector=query,
                        reference_id=case.reference_id, mode=mode, strategy=method, stage=stage)
                    elapsed = (perf_counter() - started) * 1000
                    row = case_row(case, outcome.displayed_ids,
                        [c.film_id for c in outcome.candidates], candidates=[asdict(c) for c in outcome.candidates],
                        elapsed_ms=elapsed, mode=outcome.mode)
                    row.update(dense_ids=list(outcome.dense_ids), lexical_ids=list(outcome.lexical_ids))
                rows.append(row)
            methods[method] = summarize(rows)
        stages[stage] = methods
    shared = []
    for case in fixture.cases:
        if case.kind not in {"identity", "hard_conditions"}:
            continue
        ids = sorted(hard_ids(fixture.films, fixture.people, case.hard)) if case.kind == "hard_conditions" else next(
            r["actual_ids"] for r in baseline["lexical"]["results"] if r["id"] == case.id)
        shared.append(score(case, ids))
    return {"index_build_ms": build_ms, "stages": stages,
            "shared_local_cases": {"results": shared, "scope":
                "original four exact identities and four injected plans; unchanged SQL executor covered by backend regressions; NOT NLP extraction"}}


def experiment():
    # This checks every historical implementation/input hash without changing it.
    fixture, _, freeze_id = historical.approved_fixture()
    vector_path = historical.RUN_ROOT / "vectors.json"
    if digest(vector_path) != VECTOR_SHA:
        raise SemanticError("unexpected_saved_vectors")
    readonly = [historical.FIXTURE, historical.EVIDENCE, historical.LOCK, HISTORICAL_RESULTS,
        vector_path, historical.RUN_ROOT / "budget.json", historical.RUN_ROOT / "report.json"]
    before = {str(p.relative_to(ROOT)): digest(p) for p in readonly}
    vectors = historical.SavedVectors.replay(fixture, freeze_id, vector_path)
    published = json.loads(HISTORICAL_RESULTS.read_text(encoding="utf-8"))
    # Historical helper uses its own in-memory DB; replay has no remote provider.
    baseline = historical.evaluate_fixture(fixture, vectors, ":memory:")["methods"]
    for method in METHODS:
        old = {r["id"]: r["actual_ids"] for r in published["methods"][method]["results"]}
        current = {r["id"]: r["actual_ids"] for r in baseline[method]["results"]}
        if old != current:
            raise SemanticError("historical_rank_replay_mismatch")
    policy = RetrievalPolicy()
    result = evaluate(fixture, vectors, baseline, policy=policy)
    after = {str(p.relative_to(ROOT)): digest(p) for p in readonly}
    if before != after:
        raise SemanticError("historical_artifact_changed")
    files = [Path(__file__), historical.BACKEND / "app/services/retrieval_policy.py"]
    code = {str(p.relative_to(ROOT)): historical.file_hash(p) for p in files}
    result.update(version="public-retrieval-ablation.diagnostic.v1", policy_version=VERSION,
        policy=asdict(policy), policy_fingerprint=policy.fingerprint,
        experiment_fingerprint=_hash([freeze_id, policy.fingerprint, code, before]),
        original_freeze_id=freeze_id, immutable_inputs_sha256=before, implementation_sha256=code,
        model_new_calls=0, chat_calls=0, rerank_calls=0, private_library_read=False,
        production_enabled=False, original_ranked_lists_reproduced=72,
        dataset_role="previously observed diagnostic/regression set; NOT independent test",
        qrels_status="theme grades provisional; unchanged",
        intent_scope="fixture annotations, NOT automatic intent routing or NLP validation",
        latency_scope="local saved-vector replay only; no network / no new latency measurement of provider",
        parameter_tuning="single declared v1 policy; no sweeps or qrel/data edits",
        titles={f.id: {"en": f.title_en, "zh": f.title_zh} for f in fixture.films})
    return result


def main():
    try:
        result = experiment()
    except (OSError, SemanticError, ValueError) as exc:
        code = exc.code if isinstance(exc, SemanticError) else "offline_input_unavailable"
        print(json.dumps({"status": "stopped", "reason": code, "new_model_calls": 0}))
        return 1
    print(json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
