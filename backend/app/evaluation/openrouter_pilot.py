"""Explicit, bounded real-provider smoke on the committed fictional fixture.

No application database, production settings loader, chat, reranker or local
model runtime is imported. Default invocation is a non-billable preflight.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
from statistics import median
from time import perf_counter

from dotenv import dotenv_values

from app.evaluation.semantic_search import SemanticCase, canonical_fixture_id, evaluate, load_fixture
from app.services.openrouter_embeddings import (BudgetLedger, DIMENSIONS, MODEL, PROVIDER,
    QUERY_PREFIX, OpenRouterPilotProvider, fetch_quote, http_session)
from app.services.semantic_search import SemanticCache, SemanticError, SemanticSearch

BACKEND = Path(__file__).resolve().parents[2]
FIXTURE = BACKEND / "fixtures/semantic_search/quality-v1.json"
FIXTURE_SHA = "2a1309d20b4c745fa453f23fb738effed39d6c6415b2964658c42e5004e123a9"
RUN_ROOT = BACKEND.parent / ".mcp-artifacts/openrouter-embedding-smoke-v1"


def approved_fixture():
    if sha256(FIXTURE.read_text(encoding="utf-8").encode()).hexdigest() != FIXTURE_SHA:
        raise SemanticError("fixture_not_authorized")
    fixture = load_fixture(FIXTURE)
    if len(fixture.films) != 8 or len(fixture.cases) != 24:
        raise SemanticError("fixture_not_authorized")
    return fixture


def approved_inputs(fixture):
    return frozenset([(chunk, False) for film in fixture.films for chunk in film.document().chunks]
        + [(case.content_query, True) for case in fixture.cases if case.reference is None])


def existing_credential(path=None):
    key = os.getenv("OPENROUTER_API_KEY")
    if not key and path is not None:
        if path.name not in {".env", ".env.local"} or not path.is_file():
            raise SemanticError("credential_unavailable")
        # Reuse the deployment secret source in memory only. Never copy the
        # file/key to a report, argument, persistent setting or test environment.
        key = dotenv_values(path, interpolate=False).get("OPENROUTER_API_KEY")
    if (not isinstance(key, str) or not key.strip() or key.startswith(("your_", "$" + "{"))
            or any(c.isspace() for c in key)):
        raise SemanticError("credential_unavailable")
    return key


def evaluate_fixture(fixture, provider):
    """Prefetch each approved query once; all compared retrieval modes are warm."""
    with closing(sqlite3.connect(":memory:")) as db:
        cache = SemanticCache(db)
        revision = cache.replace(tuple(f.document() for f in fixture.films), provider)
        for case in fixture.cases:
            if case.reference is None:
                provider.embed([case.content_query], query=True)
        by_name = {case.id: case for case in fixture.cases}
        cases = [SemanticCase(c.id, c.content_query,
            tuple(canonical_fixture_id(i) for i in c.expected),
            tuple(canonical_fixture_id(i) for i in c.allowed)) for c in fixture.cases]
        methods = {}
        for strategy in ("lexical", "dense", "hybrid"):
            engine = SemanticSearch(cache, provider.spec, provider=provider, strategy=strategy)
            def execute(case, engine=engine):
                reference = by_name[case.name].reference
                result = engine.submit(case.question, eligible_ids=case.hard_allowed_ids,
                    expected_revision=revision,
                    reference_id=canonical_fixture_id(reference) if reference is not None else None)
                return [item["film_id"] for item in result["items"]]
            methods[strategy] = execute
        metrics = evaluate(cases, methods)["methods"]
        for method in metrics.values():
            rows = method["results"]
            method["top1_hit_rate"] = sum(bool(r["actual_ids"]) and r["actual_ids"][0] in
                {canonical_fixture_id(i) for i in by_name[r["name"]].expected} for r in rows) / len(rows)
            method["recall_at_3"] = sum(len(set(r["actual_ids"][:3]) &
                {canonical_fixture_id(i) for i in by_name[r["name"]].expected}) /
                len(by_name[r["name"]].expected) for r in rows) / len(rows)
            method["latency_scope"] = "warm local retrieval; remote encoding measured separately"
            if method["hard_condition_violations"]:
                raise SemanticError("hard_condition_violation")
        return metrics


def run(*, execute=False, credential_env=None):
    fixture = approved_fixture()
    session = http_session()
    provider = ledger = None
    started = perf_counter()
    report = {"version": "openrouter-semantic-smoke.v1", "dataset": "fictional-eight-films-24-en-zh",
              "fixture_sha256": FIXTURE_SHA, "model": MODEL, "requested_provider": PROVIDER,
              "real_model": False, "real_library_quality_verified": False,
              "natural_language_router_evaluated": False, "production_enabled": False,
              "rerank_requests": 0, "chat_requests": 0}
    try:
        if execute and RUN_ROOT.exists():
            raise SemanticError("existing_run_requires_reconciliation")
        quote = fetch_quote(session)  # Anonymous, non-billable metadata only.
        report["quote"] = {"prompt_usd_per_token": str(quote.prompt_usd_per_token),
                           "model_created": quote.model_created}
        report["limits"] = {"usd": "1", "posts": 32, "encoded_texts": 64,
                            "reserved_tokens": 20000, "questions": 24, "films": 8}
        if not execute:
            report["status"] = "preflight_only_no_inference"
            return report
        key = existing_credential(credential_env)
        ledger = BudgetLedger(RUN_ROOT, quote)
        provider = OpenRouterPilotProvider(key, quote, ledger, approved_inputs(fixture), session=session)
        report["provider_fingerprint"] = provider.spec.fingerprint
        report["dimensions"] = DIMENSIONS
        report["query_policy"] = QUERY_PREFIX
        report["methods"] = evaluate_fixture(fixture, provider)
        report["real_model"] = True
        report["status"] = "completed_synthetic_smoke"
    except SemanticError as exc:
        report.update(status="stopped", error=exc.code)
    except Exception:
        report.update(status="stopped", error="pilot_failed")
    finally:
        report["wall_ms"] = round((perf_counter() - started) * 1000, 3)
        if ledger is not None:
            billing = ledger.summary()
            report["billing"] = billing
            times = [e["elapsed_ms"] for e in billing["entries"]]
            report["remote_request_median_ms"] = median(times) if times else None
            (RUN_ROOT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        if provider is not None:
            provider.close()
        else:
            session.close()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true",
                        help="Perform only the separately authorized fictional embedding smoke.")
    parser.add_argument("--credential-env", type=Path,
                        help="Existing deployment .env/.env.local; never copied or displayed.")
    args = parser.parse_args()
    report = run(execute=args.execute, credential_env=args.credential_env)
    # Do not print vectors, inputs, credential locations or provider bodies.
    summary = {k: v for k, v in report.items() if k not in {"methods", "query_policy"}}
    if "methods" in report:
        summary["methods"] = {name: {k: v for k, v in method.items() if k != "results"}
                              for name, method in report["methods"].items()}
    print(json.dumps(summary, ensure_ascii=False))
    return 1 if report["status"] == "stopped" else 0


if __name__ == "__main__":
    raise SystemExit(main())
