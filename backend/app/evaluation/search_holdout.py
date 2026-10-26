"""Frozen-config execution only. Independent labels are never loaded here.

Default invocation freezes configuration without network or key access. An
explicit live run accepts only id/locale/question, writes immutable per-case
outputs, and shares the original free-trial ledger. Scoring is independent.
"""
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
import re
import sqlite3
import time

from app.evaluation.search_corpus import CORPUS_SHA, documents, load_corpus, seed_projection_database
from app.evaluation.search_development import import_old_vectors
from app.evaluation.search_integration import RUN, authorization, write_json
from app.evaluation.openrouter_pilot import existing_credential
from app.services.content_request import split_content_request
from app.services.discovery_search import keyword_text
from app.services.integrated_search import IntegratedSearch, IntegratedSearchPolicy
from app.services.projections import ProjectionReader
from app.services.search_budget import SearchBudget
from app.services.search_index import CachedSearchEmbedding, SearchIndexStore
from app.services.search_local import LocalSearch
from app.services.search_providers import (ENDPOINTS, DecisionProvider, EgressScope,
    SearchEmbeddingProvider, SearchProviderClient, RerankProvider, embedding_spec)
from app.services.retrieval_policy import RetrievalPolicy
from app.services.semantic_search import SemanticError, _hash, _safe

SOURCES = ("app/services/search_providers.py", "app/services/integrated_search.py",
    "app/services/content_request.py", "app/services/search_local.py", "app/services/search_execution.py",
    "app/services/search_rules.py", "app/services/retrieval_policy.py", "app/services/semantic_search.py",
    "app/services/search_privacy.py", "app/services/search_index.py", "app/services/search_budget.py",
    "app/contracts/search_plan.py", "app/services/structured_metadata_vocab.py",
    "app/services/discovery_search.py", "app/services/ask.py", "app/contracts/ask.py",
    "app/contracts/structured_metadata.py", "app/services/projections.py", "app/canonical_models.py",
    "app/services/search_runtime.py", "app/contracts/discovery_search.py", "app/api/explore.py",
    "app/evaluation/search_corpus.py", "app/evaluation/search_holdout.py")
SEAL = "b26dce46353c86f3b43e84db005301cf257fd734dc5498c408318d220e191703"


def configuration():
    backend = Path(__file__).resolve().parents[2]
    return {"version": "search-holdout-configuration.v3", "internal_evaluation_only": True,
        "supersedes_before_reveal": ["c8bce407aeb4cb83b052cd3838173daf3b3cb88c08f6571e6e0f2f733a355706",
            "68f891e3af819d6fd94a71f50a0bfbcc996a129af122dc69d43978b92d5078c0"],
        "base_commit": "10da4f31e63855550d0fd10dffed9de3c485623c", "corpus_sha256": CORPUS_SHA,
        "independent_annotated_package_precommit": SEAL,
        "models": [asdict(e) for e in ENDPOINTS], "embedding": asdict(embedding_spec()),
        "policy": asdict(IntegratedSearchPolicy()), "policy_hash": IntegratedSearchPolicy().fingerprint,
        "retrieval_policy": asdict(RetrievalPolicy(candidate_k=20)),
        "decision_route_min_confidence": .6, "uncertain_mode": "factual", "mode_min_confidence": .6,
        "timeouts_seconds": {"decision": 5, "query_embedding": 20, "rerank": 10, "public_preflight": 10},
        "quote_max_age_seconds": 300, "candidate_limit": 20, "index_batch_chunks": 4,
        "fallback": "explicit local admitted ranking; no alternate model/provider or retries",
        "index_fields": "exact corpus document_text; title/aliases retained locally for identity evidence",
        "sources": {name: sha256((backend / name).read_text(encoding="utf-8").encode()).hexdigest() for name in SOURCES}}


def freeze():
    path = RUN / "holdout-configuration.v3.json"
    config = configuration()
    envelope = {"configuration": config, "sha256": _hash(config)}
    if path.exists() and json.loads(path.read_text(encoding="utf-8")) != envelope:
        raise SemanticError("search_frozen_configuration_changed")
    if not path.exists():
        write_json(path, envelope)
    return envelope


def execution_questions(path):
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload if isinstance(payload, list) else payload.get("queries") if isinstance(payload, dict) else None
    if isinstance(payload, dict) and set(payload) - {"version", "queries"}:
        raise SemanticError("search_annotated_input_forbidden")
    if (not isinstance(rows, list) or len(rows) != 60 or any(not isinstance(r, dict)
            or set(r) != {"id", "locale", "question"} for r in rows)):
        raise SemanticError("search_execution_questions_invalid")
    for row in rows:
        if (not isinstance(row["id"], str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", row["id"])
                or row["locale"] not in {"en", "zh"}):
            raise SemanticError("search_execution_questions_invalid")
        _safe(row["question"], 600)
    if (len({r["id"] for r in rows}) != 60 or len({r["question"] for r in rows}) != 60
            or sum(r["locale"] == "en" for r in rows) != 30):
        raise SemanticError("search_execution_questions_invalid")
    return rows


def execute(path, *, credential_path, run_live=False):
    frozen = freeze()  # Refuse changed source/policy before opening the questions.
    if not run_live:
        return {"status": "frozen", "configuration_sha256": frozen["sha256"], "requests": 0}
    rows = execution_questions(path)
    from sqlmodel import create_engine
    directory = RUN / "holdout"
    directory.mkdir(exist_ok=True)
    input_hash = sha256(path.read_bytes()).hexdigest()
    binding = {"configuration_sha256": frozen["sha256"], "execution_questions_sha256": input_hash}
    if (directory / "binding.json").exists() and json.loads((directory / "binding.json").read_text()) != binding:
        raise SemanticError("search_execution_binding_changed")
    write_json(directory / "binding.json", binding)
    corpus, films = load_corpus(RUN / "public-holdout-corpus-v1.json")
    docs = documents(films)
    queries = {r["question"] for r in rows}
    queries.update(request.text for r in rows if not (request := split_content_request(r["question"])).issue)
    queries.update(t for doc in docs for t in doc.chunks)
    scope = EgressScope("public-evaluation.v2", frozenset(_hash(t) for doc in docs for t in doc.chunks),
        frozenset(_hash(q) for q in queries), accept_logged_public=True)
    ledger = SearchBudget(RUN / "shared-budget.sqlite3", authorization(RUN))
    client = SearchProviderClient(ledger, scope, lambda: existing_credential(credential_path),
        response_sink=lambda number, payload: write_json(RUN / f"response-{number:03}.json", payload))
    database_engine = create_engine("sqlite:///" + (directory / "public-library.sqlite3").as_posix())
    connection = sqlite3.connect(directory / "index.sqlite3")
    store = SearchIndexStore(connection)
    try:
        if ledger.summary()["halted"]:
            raise SemanticError("search_budget_blocked")
        client.preflight()
        native = SearchEmbeddingProvider(client)
        if native.spec != embedding_spec():
            raise SemanticError("search_frozen_model_changed")
        reused = import_old_vectors(store, native.spec)
        embedding = CachedSearchEmbedding(store, native)
        state = store.begin(docs, native.spec)
        while state["state"] != "complete":
            if ledger.summary()["halted"]:
                raise SemanticError("search_budget_blocked")
            if any(time.monotonic() - checked > 240 for _quote, checked in client.quotes.values()):
                client.preflight()
            state = store.step(state["id"], embedding)
            print(json.dumps({"index_state": state["state"], "remaining_chunks": state["remaining_chunks"],
                "posts": ledger.summary()["requests"]}), flush=True)
        from sqlalchemy import inspect
        if not inspect(database_engine).get_table_names():
            seed_projection_database(database_engine, corpus, films)
        local = LocalSearch(database_engine)
        engine = IntegratedSearch(store, native.spec, local_interpret=local.interpret,
            known_literal=local.known_literal, resolve_hard=local.executor.resolve,
            eligible=lambda plan, ids: local.executor.eligible_ids(plan, people_ids=ids),
            summaries=local.summaries, corpus_revision=lambda: store.meta("revision"),
            reference_candidates=local.reference_candidates, decision=DecisionProvider(client),
            embedding=embedding, reranker=RerankProvider(client))
        outputs = []
        for row in rows:
            target = directory / (row["id"] + ".json")
            if target.exists():
                outputs.append(json.loads(target.read_text(encoding="utf-8")))
                continue
            if ledger.summary()["halted"]:
                break
            preflight_start = time.monotonic()
            refresh = any(time.monotonic() - checked > 240 for _quote, checked in client.quotes.values())
            if refresh:
                client.preflight()
            preflight_ms = (time.monotonic() - preflight_start) * 1000 if refresh else 0
            before = ledger.summary()["attempts"]
            start = time.monotonic()
            result = engine.submit(row["question"])
            elapsed = (time.monotonic() - start) * 1000
            if result["status"] == "keyword":
                ordinary = ProjectionReader().film_page(database_engine, query=keyword_text(row["question"]), rank_exact=True)
                actual_ids = [film["id"] for film in ordinary["items"]]
            else:
                actual_ids = [item["film"]["id"] for item in (result.get("results") or {}).get("items", [])]
            candidates = []
            baselines = {}
            if result.get("snapshot") and result["status"] == "ready":
                saved = store.snapshot(result["snapshot"], row["question"])
                index, _ = engine._index()
                candidates = [{"id": c.film_id, "cosine": c.cosine, "bm25": c.lexical.bm25,
                    "rrf": c.rrf, "rerank": saved["scores"].get(c.film_id), "local_admitted": c.admitted}
                    for c in engine._retrieve(index, saved, result).candidates]
                from app.contracts.bound_search_plan import SearchPlan
                allowed = local.executor.eligible_ids(SearchPlan.model_validate(saved["hard"]),
                    people_ids=saved["people_ids"])["eligible_ids"]
                for strategy in ("lexical", "dense", "hybrid"):
                    baseline = index.search(saved["text"], eligible_ids=allowed,
                        query_vector=saved["query_vector"], reference_id=saved["reference_id"],
                        mode="exploratory" if saved["mode"] == "exploratory" else "factual",
                        stage="admission", strategy=strategy)
                    baselines[strategy] = {"candidate_ids": [c.film_id for c in baseline.candidates[:20]],
                        "displayed_ids": [c.film_id for c in baseline.candidates[:20] if c.admitted]}
            output = {**row, **binding, "status": result["status"], "reason": result.get("reason"),
                "source": result.get("source"), "semantic": result.get("semantic"), "hard_plan": result.get("plan"),
                "issues": result.get("issues"), "people_ids": result.get("people_ids"),
                "snapshot": result.get("snapshot"), "candidate_ids": [c["id"] for c in candidates],
                "candidates": candidates, "actual_ids": actual_ids, "pipeline_elapsed_ms": elapsed,
                "baselines": baselines,
                "preflight_ms": preflight_ms, "step_timings_ms": engine.timings,
                "receipts": [r for r in ledger.summary()["receipts"] if r["number"] > before]}
            write_json(target, output)
            outputs.append(output)
            print(json.dumps({"case_id": row["id"], "status": result["status"],
                "returned": len(actual_ids), "posts": ledger.summary()["requests"]}), flush=True)
        report = {"version": "search-holdout-execution.v1", **binding, "labels_not_loaded": True,
            "reused_verified_vectors": reused, "completed_cases": len(outputs), "results": outputs,
            "accounting": ledger.summary()}
        write_json(directory / "execution-report.json", report)
        return {"completed_cases": len(outputs), "posts": report["accounting"]["requests"],
            "cost": report["accounting"]["reported_cost_usd"], **binding}
    finally:
        connection.close()
        database_engine.dispose()
        client.close()
        ledger.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze-only", action="store_true")
    parser.add_argument("--run-live", action="store_true")
    parser.add_argument("--execution-queries", type=Path)
    parser.add_argument("--credential-file", type=Path)
    args = parser.parse_args()
    print(json.dumps(execute(args.execution_queries, credential_path=args.credential_file,
        run_live=args.run_live and not args.freeze_only)))
