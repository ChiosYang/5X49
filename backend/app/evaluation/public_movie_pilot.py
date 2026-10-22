"""Explicit public-film pilot; default preparation/replay is completely offline.

No application database or production settings are imported. Live execution is
restricted to the frozen 24-film corpus, existing credentials and NVIDIA free.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import sqlite3
from statistics import median
from time import perf_counter

from app.contracts.structured_metadata import normalize_metadata_text
from app.evaluation.openrouter_pilot import existing_credential, related_qwen_run
from app.evaluation.public_movies import CONFIGURATION, hard_ids, load_fixture, score, summarize
from app.services.openrouter_embeddings import (BudgetLedger, NvidiaFreeQuote, OpenRouterPilotProvider,
    _json, fetch_quote, free_quota_preflight, http_session)
from app.services.semantic_search import ProviderSpec, SemanticCache, SemanticError, SemanticSearch, _vector

BACKEND = Path(__file__).resolve().parents[2]
FIXTURE = BACKEND / "fixtures/semantic_search/public-movies-v1.json"
EVIDENCE = BACKEND / "fixtures/semantic_search/public-movies-sources-v1.json"
LOCK = BACKEND / "fixtures/semantic_search/public-movies-v1.freeze.json"
RUN_ROOT = BACKEND.parent / ".mcp-artifacts/openrouter-public-movies-v1"
# Filled only after offline source/qrels/config verification, before dispatch.
FIXTURE_SHA = "1e8e52f991866c2d8240c464b1b45d4720bc6b6a0002de4f2bcaaefe162884ad"
EVIDENCE_SHA = "c0f9e3e9693d61c01c0ff0539b2110631e82b62bf5745d5a9bd66fd8f977c475"
LOCK_FILES = (
    "app/evaluation/public_movies.py", "app/evaluation/public_movie_pilot.py",
    "app/services/semantic_search.py", "app/services/openrouter_embeddings.py",
    "app/services/search_privacy.py",
    "app/evaluation/openrouter_pilot.py", "app/contracts/structured_metadata.py",
    "app/contracts/search_plan.py", "test_public_movies.py",
    "fixtures/semantic_search/public-movies-v1.json",
    "fixtures/semantic_search/public-movies-sources-v1.json",
)


def file_hash(path):
    # Stable across Git LF/CRLF checkouts; never strip or alter content otherwise.
    return sha256(path.read_text(encoding="utf-8").encode()).hexdigest()


def atomic_json(path, data):
    temporary = path.with_suffix(path.suffix + ".pending")
    with temporary.open("w", encoding="utf-8") as output:
        json.dump(data, output, ensure_ascii=False, allow_nan=False, indent=2)
        output.write("\n")
        output.flush()
        os.fsync(output.fileno())
    os.replace(temporary, path)


def approved_fixture():
    if file_hash(FIXTURE) != FIXTURE_SHA or file_hash(EVIDENCE) != EVIDENCE_SHA:
        raise SemanticError("public_fixture_not_frozen")
    fixture = load_fixture(FIXTURE)
    lock = _json(LOCK.read_bytes())
    expected = {name: file_hash(BACKEND / name) for name in LOCK_FILES}
    if (lock.get("version") != "public-movie-evaluation.freeze.v1"
            or lock.get("files") != expected or lock.get("configuration") != CONFIGURATION):
        raise SemanticError("public_protocol_changed")
    evidence = _json(EVIDENCE.read_bytes())
    source_map = {s.id: s for s in fixture.sources}
    for film in fixture.films:
        original = evidence["films"][film.qid]
        if str(original["lastrevid"]) != source_map["wikidata-" + film.qid].revision:
            raise SemanticError("public_source_revision_mismatch")
        names = set(original["labels"].values()) | {n for ns in original["aliases"].values() for n in ns}
        if any(t.value not in names for t in film.titles):
            raise SemanticError("public_title_not_grounded")
    freeze_id = sha256(json.dumps(lock, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    return fixture, lock, freeze_id


def preparation(fixture, freeze_id):
    return {"version": "public-movie-pilot.v1", "status": "frozen_preparation_no_inference",
        "freeze_id": freeze_id, "fixture_sha256": FIXTURE_SHA, "evidence_sha256": EVIDENCE_SHA,
        "films": len(fixture.films), "questions": len(fixture.cases),
        "question_counts": {kind: sum(c.kind == kind for c in fixture.cases) for kind in
            ("identity", "plot_fact", "theme", "hard_conditions", "no_answer")},
        "locales": {locale: sum(c.locale == locale for c in fixture.cases) for locale in ("en", "zh")},
        "expected_requests": len(fixture.inputs()), "maximum_requests": 42,
        "document_encodings": 24, "query_encodings": 14,
        "reserved_token_bound": sum(len(text.encode()) + 256 for text, _ in fixture.inputs()),
        "qrels_status": fixture.qrels_status, "configuration": fixture.configuration,
        "real_model": False, "production_enabled": False, "private_library_read": False,
        "chat_requests": 0, "rerank_requests": 0}


def vector_key(text, query):
    return sha256(json.dumps([text, query], ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


class SavedVectors:
    """Persist every validated public vector atomically, then replay with no HTTP."""
    def __init__(self, provider, fixture, freeze_id, path):
        self.provider, self.spec = provider, provider.spec
        self.allowed, self.path = fixture.inputs(), path
        self.memo = {}
        self.data = {"version": "public-movie-vectors.v1", "freeze_id": freeze_id,
            "fixture_sha256": FIXTURE_SHA, "provider_spec": vars(self.spec), "entries": {}}
        if path.exists():
            raise SemanticError("existing_public_vectors")
        atomic_json(path, self.data)

    @classmethod
    def replay(cls, fixture, freeze_id, path):
        if path.stat().st_size > 20 * 1024 * 1024:
            raise SemanticError("public_vector_limit")
        data = _json(path.read_bytes())
        if (not isinstance(data, dict) or data.get("version") != "public-movie-vectors.v1"
                or data.get("freeze_id") != freeze_id or data.get("fixture_sha256") != FIXTURE_SHA):
            raise SemanticError("public_vector_manifest_mismatch")
        result = object.__new__(cls)
        result.provider = None
        result.spec = ProviderSpec(**data["provider_spec"])
        if result.spec.fingerprint != CONFIGURATION["provider_fingerprint"]:
            raise SemanticError("public_vector_provider_mismatch")
        result.allowed, result.path = fixture.inputs(), path
        result.data, result.memo = data, {}
        valid = {vector_key(text, query): (text, query) for text, query in result.allowed}
        entries = data.get("entries")
        if not isinstance(entries, dict) or set(entries) != set(valid):
            raise SemanticError("public_vectors_incomplete")
        for key, item in entries.items():
            if not isinstance(item, dict) or item.get("query") is not valid[key][1]:
                raise SemanticError("public_vector_input_mismatch")
            vector = item.get("vector")
            _vector(vector, result.spec.dimensions)
            result.memo[valid[key]] = tuple(vector)
        return result

    def embed(self, texts, *, query):
        if type(query) is not bool or not isinstance(texts, (list, tuple)) or not texts:
            raise SemanticError("public_input_not_authorized")
        keys = [(text, query) for text in texts]
        if any(key not in self.allowed for key in keys):
            raise SemanticError("public_input_not_authorized")
        missing = [key for key in keys if key not in self.memo]
        if missing:
            if self.provider is None:
                raise SemanticError("public_vectors_incomplete")
            values = self.provider.embed([key[0] for key in missing], query=query)
            if len(values) != len(missing):
                raise SemanticError("invalid_provider_vectors")
            for key, vector in zip(missing, values):
                _vector(vector, self.spec.dimensions)
                self.memo[key] = tuple(vector)
                self.data["entries"][vector_key(*key)] = {"query": key[1], "vector": vector}
            atomic_json(self.path, self.data)
        return [list(self.memo[key]) for key in keys]


def evaluate_fixture(fixture, provider, cache_path):
    with closing(sqlite3.connect(cache_path)) as db:
        cache = SemanticCache(db)
        revision = cache.replace(tuple(f.document() for f in fixture.films), provider)
        for case in fixture.cases:
            if case.embedding_query is not None:
                provider.embed([case.embedding_query], query=True)
        methods = {}
        for strategy in ("lexical", "dense", "hybrid"):
            engine = SemanticSearch(cache, provider.spec, provider=provider,
                strategy=strategy, minimum_similarity=CONFIGURATION["minimum_similarity"])
            rows = []
            for case in fixture.cases:
                start = perf_counter()
                if case.kind == "identity":
                    wanted = normalize_metadata_text(case.question)
                    actual = sorted(f.id for f in fixture.films if wanted in
                        {normalize_metadata_text(t.value) for t in f.titles})
                elif case.kind == "hard_conditions":
                    actual = sorted(hard_ids(fixture.films, fixture.people, case.hard))
                else:
                    result = engine.submit(case.question, eligible_ids=case.allowed_ids,
                        expected_revision=revision, reference_id=case.reference_id)
                    actual = [item["film_id"] for item in result["items"]]
                row = score(case, actual)
                row["elapsed_ms"] = round((perf_counter() - start) * 1000, 3)
                rows.append(row)
            method = summarize(rows)
            times = sorted(r["elapsed_ms"] for r in rows if r["kind"] not in {"identity", "hard_conditions"})
            method["semantic_warm_median_ms"] = median(times)
            method["semantic_warm_p95_ms"] = times[math.ceil(len(times) * .95) - 1]
            method["latency_scope"] = "warm local retrieval; remote requests timed separately"
            methods[strategy] = method
        return {"corpus_revision": revision, "methods": methods,
            "hard_scope": "source-backed oracle cross-checked against existing SQL executor in offline tests; not a live NLP-model gate",
            "shared_local_fast_paths": "four exact identities and four hard-only plans; excluded from semantic aggregate"}


def replay():
    fixture, _, freeze_id = approved_fixture()
    vectors = SavedVectors.replay(fixture, freeze_id, RUN_ROOT / "vectors.json")
    report = preparation(fixture, freeze_id)
    report.update(status="offline_replay_no_inference", real_model=True,
        new_model_calls=0, **evaluate_fixture(fixture, vectors, ":memory:"))
    return report


def run(*, execute=False, credential_env=None, accept_nvidia_logging=False):
    fixture, lock, freeze_id = approved_fixture()
    report = preparation(fixture, freeze_id)
    if not execute:
        return report  # No HTTP, credential lookup or library DB import.
    if accept_nvidia_logging is not True:
        raise SemanticError("nvidia_logging_confirmation_required")
    if RUN_ROOT.exists():
        raise SemanticError("existing_run_requires_reconciliation")
    prior = related_qwen_run()  # Original receipt is read/hash-linked, never rewritten.
    session, provider, ledger = http_session(), None, None
    started = perf_counter()
    try:
        quote = fetch_quote(session, nvidia_free=True)
        if (not isinstance(quote, NvidiaFreeQuote) or quote.model_created != CONFIGURATION["model_created"]):
            raise SemanticError("public_model_revision_changed")
        key = existing_credential(credential_env)
        quota = free_quota_preflight(session, key, minimum_posts=len(fixture.inputs()))
        ledger = BudgetLedger(RUN_ROOT, quote, scope="public-movies.v1")
        ledger.data.update(related_prior_run=prior, freeze_id=freeze_id,
            nvidia_logging_trial_terms_accepted=True, public_movie_scope_authorized=True)
        ledger._write()
        atomic_json(RUN_ROOT / "frozen-protocol.json", lock)
        provider = OpenRouterPilotProvider(key, quote, ledger, fixture.inputs(),
            session=session, accept_nvidia_logging=True)
        if provider.spec.fingerprint != CONFIGURATION["provider_fingerprint"]:
            raise SemanticError("public_model_revision_changed")
        recording = SavedVectors(provider, fixture, freeze_id, RUN_ROOT / "vectors.json")
        report.update(quote={"model_created": quote.model_created, "prompt_usd_per_token": str(quote.prompt_usd_per_token)},
            related_prior_run=prior, free_quota=quota,
            data_policy={"scope": "frozen public film facts and test questions only", "zdr": False,
                         "nvidia_input_logging_accepted": True})
        report.update(evaluate_fixture(fixture, recording, RUN_ROOT / "semantic-cache.sqlite3"))
        if ledger.summary()["requests"] != len(fixture.inputs()) or len(recording.memo) != len(fixture.inputs()):
            raise SemanticError("public_encoding_count_mismatch")
        report.update(status="completed_public_movie_pilot", real_model=True,
            human_quality_verified=False, real_private_library_quality_verified=False,
            natural_language_model_router_evaluated=False)
    except SemanticError as exc:
        report.update(status="stopped", error=exc.code)
    except Exception:
        report.update(status="stopped", error="public_pilot_failed")
    finally:
        report["wall_ms"] = round((perf_counter() - started) * 1000, 3)
        if ledger is not None:
            report["billing"] = ledger.summary()
            times = sorted(e["elapsed_ms"] for e in report["billing"]["entries"] if "elapsed_ms" in e)
            report["remote_request_median_ms"] = median(times) if times else None
            report["remote_request_p95_ms"] = times[math.ceil(len(times) * .95) - 1] if times else None
            atomic_json(RUN_ROOT / "report.json", report)
        if provider is not None:
            provider.close()
        else:
            session.close()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--execute", action="store_true")
    mode.add_argument("--replay", action="store_true")
    parser.add_argument("--credential-env", type=Path)
    parser.add_argument("--accept-nvidia-logging", action="store_true")
    args = parser.parse_args()
    try:
        report = replay() if args.replay else run(execute=args.execute, credential_env=args.credential_env,
            accept_nvidia_logging=args.accept_nvidia_logging)
    except SemanticError as exc:
        report = {"status": "stopped", "error": exc.code}
    # No credentials, file locations, full inputs or vectors in console output.
    output = {k: v for k, v in report.items() if k not in {"methods", "configuration"}}
    if "methods" in report:
        output["methods"] = {method: {k: v for k, v in values.items() if k != "results"}
                             for method, values in report["methods"].items()}
    print(json.dumps(output, ensure_ascii=False))
    return 1 if report["status"] == "stopped" else 0


if __name__ == "__main__":
    raise SystemExit(main())
