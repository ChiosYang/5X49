"""Explicit evaluation-only native API contract check on frozen old public data.

No inference by default. One shared 320-POST/zero-USD ledger is reused by later
development, holdout and persistent-test-library stages. A partial run is not
automatically replayed. Credentials remain in their existing source/in memory.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import time

from app.evaluation.openrouter_pilot import existing_credential
from app.evaluation.public_movies import load_fixture
from app.services.search_budget import SearchAuthorization, SearchBudget
from app.services.search_providers import (DECISION, EMBEDDING, RERANK, DecisionProvider,
    EgressScope, RerankProvider, SearchEmbeddingProvider, SearchProviderClient)
from app.services.semantic_search import SemanticError, _hash

BACKEND = Path(__file__).resolve().parents[2]
WORKTREE = BACKEND.parent
RUN = WORKTREE / ".mcp-artifacts/search-integration-evaluation-v1"
FIXTURE = BACKEND / "fixtures/semantic_search/public-movies-v1.json"


def write_json(path, value):
    temporary = path.with_suffix(".pending")
    with temporary.open("w", encoding="utf-8") as output:
        json.dump(value, output, ensure_ascii=False, allow_nan=False, indent=2)
        output.flush()
        import os
        os.fsync(output.fileno())
    temporary.replace(path)


def authorization(root):
    root.mkdir(parents=True, exist_ok=True)
    path = root / "authorization.json"
    if path.exists():
        return SearchAuthorization(**json.loads(path.read_text(encoding="utf-8")))
    if (root / "shared-budget.sqlite3").exists():
        raise SemanticError("search_authorization_missing")
    grant = SearchAuthorization("search-integration-free-evaluation-v1", 320, "0", int(time.time()) + 3 * 86400)
    write_json(path, asdict(grant))
    return grant


def contract_inputs():
    fixture = load_fixture(FIXTURE)
    # The old public data are development material. No new holdout is opened.
    question = next(c.question for c in fixture.cases if c.kind == "theme" and c.locale == "en")
    documents = tuple(f.document_text for f in fixture.films[:2])
    return question, documents


def contract_check(credential_path=None, *, root=RUN, continue_after_alias=False):
    question, documents = contract_inputs()
    result_path = root / ("contract-check-alias-recheck.json" if continue_after_alias else "contract-check.json")
    if result_path.exists():
        raise SemanticError("search_contract_check_already_attempted")
    grant = authorization(root)
    ledger = SearchBudget(root / "shared-budget.sqlite3", grant)
    if continue_after_alias:
        previous = json.loads((root / "contract-check.json").read_text(encoding="utf-8"))
        if previous.get("reason") != "search_route_mismatch" or previous.get("stages"):
            ledger.close()
            raise SemanticError("search_contract_check_requires_review")
        ledger.acknowledge_published_alias()
    before = ledger.summary()
    if before["halted"] or before["requests"] != (1 if continue_after_alias else 0):
        ledger.close()
        raise SemanticError("search_contract_check_requires_review")
    scope = EgressScope("public-evaluation.v2", frozenset(_hash(d) for d in documents),
                        frozenset({_hash(question)}), accept_logged_public=True)
    client = SearchProviderClient(ledger, scope, lambda: existing_credential(credential_path),
        response_sink=lambda number, payload: write_json(root / f"response-{number:03}.json", payload))
    report = {"version": "search-integration-contract.v1", "internal_evaluation_only": True,
        "started_utc": datetime.now(timezone.utc).isoformat(), "models": [e.model for e in (DECISION, EMBEDDING, RERANK)],
        "scope": "old frozen public development samples only", "input_hash": _hash([question, documents]),
        "status": "preflight", "stages": {}}
    write_json(result_path, report)
    try:
        quotes = client.preflight()
        report["quotes"] = [{"model": e.model, "provider": e.provider, "price": str(q.prompt_price), "created": q.created}
                            for e, q in quotes.items()]
        write_json(result_path, report)
        start = time.monotonic()
        decision = DecisionProvider(client).decide(question)
        report["stages"]["decision"] = {**asdict(decision), "elapsed_ms": (time.monotonic() - start) * 1000}
        write_json(result_path, report)
        time.sleep(3.2)  # Proactive pacing, never a retry.
        start = time.monotonic()
        provider = SearchEmbeddingProvider(client)
        vectors = provider.embed((documents[0],), query=False)
        write_json(root / "contract-vectors.json", {"model_fingerprint": provider.spec.fingerprint,
            "text_hashes": [_hash(documents[0])], "vectors": vectors, "query": False})
        report["stages"]["embedding"] = {"dimensions": len(vectors[0]), "encoded_texts": 1,
            "elapsed_ms": (time.monotonic() - start) * 1000}
        write_json(result_path, report)
        time.sleep(3.2)
        start = time.monotonic()
        scores = RerankProvider(client).rank(question, documents)
        report["stages"]["rerank"] = {"scores": scores, "candidates": 2,
            "elapsed_ms": (time.monotonic() - start) * 1000}
        report["status"] = "contract_passed_not_quality_acceptance"
    except SemanticError as exc:
        report.update(status="stopped", reason=exc.code)
    finally:
        report["accounting"] = ledger.summary()
        report["finished_utc"] = datetime.now(timezone.utc).isoformat()
        write_json(result_path, report)
        client.close()
        ledger.close()
    return {k: report[k] for k in ("status", "stages", "accounting")}


def rerank_contract_recheck(credential_path=None, *, root=RUN):
    """Only rerank is repeated after its zero-cost response alias was verified."""
    question, documents = contract_inputs()
    path = root / "contract-rerank-recheck.json"
    if path.exists():
        raise SemanticError("search_contract_check_already_attempted")
    grant = authorization(root)
    ledger = SearchBudget(root / "shared-budget.sqlite3", grant)
    before = ledger.summary()
    if before["requests"] != 4 or before["halted"] != "search_route_mismatch":
        ledger.close()
        raise SemanticError("search_contract_check_requires_review")
    ledger.acknowledge_published_alias()
    scope = EgressScope("public-evaluation.v2", frozenset(_hash(d) for d in documents),
                        frozenset({_hash(question)}), accept_logged_public=True)
    client = SearchProviderClient(ledger, scope, lambda: existing_credential(credential_path),
        response_sink=lambda number, payload: write_json(root / f"response-{number:03}.json", payload))
    report = {"status": "preflight", "only_stage": "rerank", "prior_receipts_retained": True,
              "started_utc": datetime.now(timezone.utc).isoformat()}
    write_json(path, report)
    try:
        client.preflight((RERANK,))
        report["scores"] = RerankProvider(client).rank(question, documents)
        report["status"] = "rerank_contract_passed_not_quality_acceptance"
    except SemanticError as exc:
        report.update(status="stopped", reason=exc.code)
    finally:
        report["accounting"] = ledger.summary()
        report["finished_utc"] = datetime.now(timezone.utc).isoformat()
        write_json(path, report)
        client.close()
        ledger.close()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract-check", action="store_true")
    parser.add_argument("--run-live", action="store_true")
    parser.add_argument("--continue-after-verified-alias", action="store_true")
    parser.add_argument("--rerank-recheck", action="store_true")
    parser.add_argument("--credential-file", type=Path)
    args = parser.parse_args()
    if not args.contract_check or not args.run_live:
        print(json.dumps({"status": "offline", "live_requests": 0, "requires_explicit_run_live": True}))
        return
    try:
        result = (rerank_contract_recheck(args.credential_file) if args.rerank_recheck else
            contract_check(args.credential_file, continue_after_alias=args.continue_after_verified_alias))
        print(json.dumps(result, ensure_ascii=False))
    except SemanticError as exc:
        print(json.dumps({"status": "stopped_before_dispatch", "reason": exc.code}))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
