"""Five sealed reference-focus reranks; prepare offline, execute only explicitly.

Only the public corpus and existing cache are read. No Decision, embedding,
private-library input, index rebuild, automatic retry or production integration.
All plans, responses and outputs remain in the ignored local evaluation root.
"""
from contextlib import closing, contextmanager
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import time

from sqlmodel import create_engine

from app.evaluation.search_continuation import immutable
from app.evaluation.search_corpus import documents, load_corpus
from app.evaluation.search_focus_budget import FocusBudget, MAX_REQUESTS
from app.evaluation.search_holdout import execution_questions
from app.evaluation.search_integration import RUN, authorization
from app.evaluation.search_seen_replay import _read_only, source_configuration
from app.services.integrated_search import IntegratedSearch
from app.services.content_request import split_content_request
from app.contracts.bound_search_plan import SearchPlan
from app.services.search_index import SearchIndexStore
from app.services.search_local import LocalSearch
from app.services.search_providers import EgressScope, RERANK, RerankProvider, SearchProviderClient, embedding_spec
from app.services.semantic_search import SemanticError, _hash

DIRECTORY = "focus-validation-v1"
FILES = ("public-holdout-corpus-v1.json", "execution-queries.v2.json",
         "holdout/public-library.sqlite3", "resumption-20261026/seen/index.sqlite3")


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def source_hashes(value):
    """Compare report-relative keys portably without rewriting sealed evidence."""
    if not isinstance(value, dict):
        raise SemanticError("search_focus_source_keys_invalid")
    normalized = {}
    for name, fingerprint in value.items():
        if not isinstance(name, str) or ":" in name or "\0" in name:
            raise SemanticError("search_focus_source_keys_invalid")
        key = name.replace("\\", "/")
        if any(part in {"", ".", ".."} for part in key.split("/")) or key in normalized:
            raise SemanticError("search_focus_source_keys_invalid")
        normalized[key] = fingerprint
    return normalized


def code_revision():
    backend = Path(__file__).resolve().parents[2]
    names = ("app/evaluation/search_focus_budget.py", "app/evaluation/search_focus_validation.py",
             "app/evaluation/search_recovery.py", "app/evaluation/search_continuation.py",
             "app/evaluation/search_integration.py", "app/evaluation/openrouter_pilot.py")
    return _hash([source_configuration(), {n: digest(backend / n) for n in names}])


def request_record(body):
    if not isinstance(body, dict) or set(body) != {"query", "documents", "top_n"}:
        raise SemanticError("search_focus_input_mismatch")
    texts, query = body["documents"], body["query"]
    # Reuse the real adapter's validation and existing privacy limits.
    class Capture:
        def request(self, endpoint, actual, **options):
            if endpoint != RERANK or actual != body:
                raise SemanticError("search_focus_input_mismatch")
            scope = EgressScope("public-evaluation.v2", frozenset(_hash(t) for t in texts),
                                frozenset({_hash(query)}), True)
            scope.check(texts, query=False); scope.check((query,), query=True)
    RerankProvider(Capture()).rank(query, texts)
    if type(body["top_n"]) is not int or body["top_n"] != len(texts):
        raise SemanticError("search_focus_input_mismatch")
    return {"input_hash": _hash([body, "rerank"]),
            "tokens": sum(len(t.encode()) + len(query.encode()) + 256 for t in texts)}


class CaptureClient:
    def __init__(self):
        self.bodies = []

    def request(self, endpoint, body, **options):
        if endpoint != RERANK or options["purpose"] != "rerank" or options["timeout"] != 10:
            raise SemanticError("search_focus_unexpected_stage")
        request_record(body)
        self.bodies.append(body)
        raise SemanticError("search_focus_not_executed")


@contextmanager
def context(root):
    _, films = load_corpus(root / FILES[0])
    expected = {d.film_id: d.digest for d in documents(films)}
    with closing(sqlite3.connect(":memory:")) as memory:
        with closing(_read_only(root / FILES[3])) as source:
            source.backup(memory)
        store = SearchIndexStore(memory); spec = embedding_spec()
        docs, _, _ = store.read(spec)
        if {d.film_id: d.digest for d in docs} != expected:
            raise SemanticError("search_focus_corpus_changed")
        engine = create_engine("sqlite:///file:" + (root / FILES[2]).resolve().as_posix() + "?mode=ro&uri=true")
        local = LocalSearch(engine)
        search = IntegratedSearch(store, spec, local_interpret=local.interpret, known_literal=local.known_literal,
            resolve_hard=local.executor.resolve, eligible=lambda p, ids: local.executor.eligible_ids(p, people_ids=ids),
            summaries=local.summaries, corpus_revision=lambda: store.meta("revision"),
            reference_candidates=local.reference_candidates, title_mentions=local.title_mentions)
        try:
            yield search, store, spec, docs
        finally:
            engine.dispose()


def capture_cases(search, store, rows):
    capture = CaptureClient(); search.reranker = RerankProvider(capture)
    cases = []
    for row in rows:
        request = split_content_request(row["question"], lookup=search.reference_candidates,
                                        mentions=search.title_mentions)
        if request.issue or not request.reference or not request.reference_focus:
            raise SemanticError("search_focus_extent_changed")
        before = len(capture.bodies)
        result = search.submit(row["question"])
        if result["status"] != "ready" or not result.get("snapshot") or len(capture.bodies) != before + 1:
            raise SemanticError("search_focus_extent_changed")
        snapshot = store.snapshot(result["snapshot"], row["question"])
        if (not snapshot.get("reference_id") or not snapshot.get("reference_focus")
                or snapshot.get("query_vector") is not None
                or snapshot["fallback"] != "search_focus_not_executed"):
            raise SemanticError("search_focus_extent_changed")
        body = capture.bodies[-1]
        trace = local_trace(search, snapshot)
        index, _ = search._index()
        if ([index.documents[c["film_id"]].chunks[0] for c in trace["candidates"]] != body["documents"]
                or snapshot["reference_id"] in [c["film_id"] for c in trace["candidates"]]):
            raise SemanticError("search_focus_candidate_mismatch")
        cases.append({"id": row["id"], "question_sha256": _hash(row["question"]),
                      "reference_id": snapshot["reference_id"], "trace": trace,
                      "body": body, **request_record(body)})
    if len(cases) != MAX_REQUESTS or len({c["input_hash"] for c in cases}) != MAX_REQUESTS:
        raise SemanticError("search_focus_extent_changed")
    return cases


def local_trace(search, snapshot):
    """Diagnostic counts/scores use the same SQL filter and retrieval code."""
    hard = SearchPlan.model_validate(snapshot["hard"])
    resolved = search.resolve_hard(hard, snapshot["people_ids"])
    index, _ = search._index()
    retrieval = search._retrieve(index, snapshot, resolved)
    return {"eligible_count": retrieval.eligible_count,
            "candidates": [{"film_id": c.film_id, "cosine": c.cosine, "bm25": c.lexical.bm25,
                "coverage": c.lexical.coverage, "rrf": c.rrf, "local_admitted": c.admitted,
                "local_reason": c.reason} for c in retrieval.candidates[:search.policy.candidate_k]]}


def prepare(root, replay_report):
    root = root.resolve(); replay_report = replay_report.resolve()
    if not replay_report.is_relative_to(root):
        raise SemanticError("search_focus_report_outside_root")
    target = root / DIRECTORY / "plan.json"
    if target.exists():
        plan = json.loads(target.read_text(encoding="utf8")); verify_plan(root, plan)
        return plan
    report = json.loads(replay_report.read_text(encoding="utf8"))
    if (report.get("configuration") != source_configuration() or report.get("new_requests") != 0
            or not report.get("seen_regression_only") or report.get("independent_acceptance") is not False):
        raise SemanticError("search_focus_report_changed")
    sources = source_hashes(report["read_only_sources"])
    for name in FILES[1:]:
        if digest(root / name) != sources.get(name):
            raise SemanticError("search_focus_source_changed")
    missing = [r for r in report["results"] if r["unverified"]]
    if (len(missing) != MAX_REQUESTS or any(len(r["events"]) != 1 or r["events"][0]["purpose"] != "rerank"
            or r["events"][0]["verified_recording"] or r["events"][0]["new_requests"] != 0 for r in missing)):
        raise SemanticError("search_focus_extent_changed")
    by_id = {r["id"]: r for r in execution_questions(root / FILES[1])}
    rows = [by_id[r["id"]] for r in missing]
    with context(root) as (search, store, _, _):
        cases = capture_cases(search, store, rows)
    if any(c["input_hash"] != r["events"][0]["wire_body_sha256"] for c, r in zip(cases, missing)):
        raise SemanticError("search_focus_input_mismatch")
    with closing(_read_only(root / "shared-budget.sqlite3")) as db:
        db.row_factory = sqlite3.Row
        receipts = [dict(r) for r in db.execute("SELECT * FROM search_budget_receipts ORDER BY number")]
        meta = dict(db.execute("SELECT key,value FROM search_budget_meta"))
    # Refuse preparing a second plan after any supplement/attempt. The bound
    # original replay also commits to the exact initial ledger bytes.
    if (any(k.startswith("focus_validation_v1_") for k in meta)
            or digest(root / "shared-budget.sqlite3") != sources.get("shared-budget.sqlite3")):
        raise SemanticError("search_focus_baseline_changed")
    now = int(time.time())
    config = {"version": "focus-validation-plan.v1", "code_revision": code_revision(),
        "replay_report": str(replay_report.relative_to(root)), "replay_sha256": digest(replay_report),
        "files": {name: digest(root / name) for name in FILES}, "cases": cases,
        "embedding": embedding_spec().fingerprint, "evaluation_only": True, "original_fail_unchanged": True}
    grant = {"version": "focus-validation-grant.v1", "authorization": authorization(root).fingerprint,
        "baseline": len(receipts), "max_attempts": len(receipts) + MAX_REQUESTS, "issued": now, "expires": now + 86400,
        "rows_sha256": _hash(receipts), "meta_sha256": _hash(meta), "plan_sha256": _hash(config),
        "requests": [{k: c[k] for k in ("input_hash", "tokens")} for c in cases]}
    plan = {"configuration": config, "grant": grant}
    target.parent.mkdir(exist_ok=True)
    immutable(target, plan)
    return plan


def verify_plan(root, plan):
    config, grant = plan["configuration"], plan["grant"]
    if (config["version"] != "focus-validation-plan.v1" or config["code_revision"] != code_revision()
            or _hash(config) != grant["plan_sha256"] or set(config["files"]) != set(FILES)
            or config["embedding"] != embedding_spec().fingerprint
            or config["evaluation_only"] is not True or config["original_fail_unchanged"] is not True
            or any(digest(root / n) != value for n, value in config["files"].items())):
        raise SemanticError("search_focus_plan_changed")
    report = (root / config["replay_report"]).resolve()
    if not report.is_relative_to(root.resolve()) or digest(report) != config["replay_sha256"]:
        raise SemanticError("search_focus_report_changed")
    original = json.loads(report.read_text(encoding="utf8"))
    missing = [r for r in original["results"] if r["unverified"]]
    if (original["configuration"] != source_configuration() or len(missing) != MAX_REQUESTS
            or [r["id"] for r in missing] != [c["id"] for c in config["cases"]]
            or any(len(r["events"]) != 1 or r["events"][0]["purpose"] != "rerank"
                   or r["events"][0]["verified_recording"]
                   or r["events"][0]["wire_body_sha256"] != c["input_hash"]
                   for r, c in zip(missing, config["cases"]))):
        raise SemanticError("search_focus_extent_changed")
    by_id = {r["id"]: r for r in execution_questions(root / FILES[1])}
    rows = [by_id[c["id"]] for c in config["cases"]]
    with context(root) as (search, store, _, _):
        if capture_cases(search, store, rows) != config["cases"]:
            raise SemanticError("search_focus_input_mismatch")
    if grant["requests"] != [{k: c[k] for k in ("input_hash", "tokens")} for c in config["cases"]]:
        raise SemanticError("search_focus_input_mismatch")
    return rows


class FocusClient(SearchProviderClient):
    """Validate the entire native body before key lookup, not just text scope."""
    def __init__(self, *args, cases, **kwargs):
        super().__init__(*args, **kwargs)
        self.cases = cases

    def request(self, endpoint, body, **options):
        position = len(self.ledger.rows()) - self.ledger._grant()["baseline"]
        if (endpoint != RERANK or options.get("purpose") != "rerank" or options.get("timeout") != 10
                or not 0 <= position < len(self.cases) or body != self.cases[position]["body"]
                or list(options.get("texts", ())) != body["documents"]
                or tuple(options.get("query_texts", ())) != (body["query"],)):
            raise SemanticError("search_focus_input_mismatch")
        return super().request(endpoint, body, **options)


def execute(root, plan, credential_path):
    # Called only after a separate review of this tool and explicit live action.
    # A missing output after a reported POST requires diagnosis, never resend.
    rows = verify_plan(root, plan); config, grant = plan["configuration"], plan["grant"]
    directory = root / DIRECTORY
    with closing(FocusBudget(root / "shared-budget.sqlite3", authorization(root))) as ledger:
        ledger.activate(grant)
        if ledger.summary()["focus_halted"]:
            raise SemanticError("search_budget_blocked")
        completed = len(ledger.rows()) - grant["baseline"]
        for i, receipt in enumerate(ledger.rows()[grant["baseline"]:]):
            output = directory / f"case-{i + 1}.json"
            saved = json.loads(output.read_text(encoding="utf8")) if output.exists() else {}
            if (receipt["state"] != "reported" or saved.get("receipt") != receipt
                    or saved.get("id") != rows[i]["id"]
                    or saved.get("configuration_sha256") != grant["plan_sha256"]
                    or (saved.get("result") or {}).get("status") != "ready"
                    or ((saved.get("result") or {}).get("semantic") or {}).get("fallback")):
                ledger.stop("search_focus_incomplete_output")
                raise SemanticError("search_budget_blocked")
        if completed == MAX_REQUESTS:
            return {"status": "complete", "new_posts": 0, "already_complete": True}
        scope = EgressScope("public-evaluation.v2",
            frozenset(_hash(t) for c in config["cases"] for t in c["body"]["documents"]),
            frozenset(_hash(c["body"]["query"]) for c in config["cases"]), True)
        from app.evaluation.openrouter_pilot import existing_credential
        from app.evaluation.search_recovery import TraceSession
        from app.services.openrouter_embeddings import http_session
        from app.services.search_providers import EMBEDDING, SearchEmbeddingProvider
        (directory / "transport").mkdir(exist_ok=True)
        client = FocusClient(ledger, scope, lambda: existing_credential(credential_path), cases=config["cases"],
            session=TraceSession(http_session(), ledger, directory / "transport"),
            response_sink=lambda n, p: immutable(directory / f"response-{n}.json", p))
        try:
            with context(root) as (search, store, spec, _):
                search.reranker = RerankProvider(client)
                for i in range(completed, MAX_REQUESTS):
                    # Only public GET metadata checks; no embedding POST.
                    client.preflight((RERANK, EMBEDDING))
                    if SearchEmbeddingProvider(client).spec != spec:
                        raise SemanticError("search_index_stale")
                    start = time.monotonic()
                    result = search.submit(rows[i]["question"])
                    receipt = next((r for r in ledger.rows()
                                    if r["number"] == grant["baseline"] + i + 1), None)
                    snapshot = store.snapshot(result["snapshot"], rows[i]["question"]) if result.get("snapshot") else None
                    value = {"id": rows[i]["id"], "configuration_sha256": grant["plan_sha256"],
                        "result": result, "receipt": receipt,
                        "trace": local_trace(search, snapshot) if snapshot else None,
                        "native_scores": snapshot["scores"] if snapshot else {}, "timings": search.timings,
                        "elapsed_ms": (time.monotonic() - start) * 1000,
                        "seen_regression_only": True, "independent_acceptance": False}
                    immutable(directory / f"case-{i + 1}.json", value)
                    if (receipt is None or receipt["state"] != "reported"
                            or result["status"] != "ready" or (result.get("semantic") or {}).get("fallback")
                            or ledger.summary()["focus_halted"]):
                        raise SemanticError("search_focus_incomplete")
        except Exception as error:
            ledger.stop(error.code if isinstance(error, SemanticError) else "search_focus_interrupted")
            raise
        finally:
            client.close()
        return {"status": "complete", "new_posts": MAX_REQUESTS - completed,
                "total_attempts": len(ledger.rows()), "independent_acceptance": False}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replay-report", required=True, type=Path)
    parser.add_argument("--run-live", action="store_true")
    parser.add_argument("--credential-file", type=Path)
    args = parser.parse_args()
    try:
        plan = prepare(RUN, args.replay_report)
        result = (execute(RUN, plan, args.credential_file) if args.run_live else
                  {"status": "prepared", "plan_sha256": plan["grant"]["plan_sha256"], "new_posts": 0})
        print(json.dumps(result))
    except SemanticError as error:
        print(json.dumps({"status": "stopped", "code": error.code}))
        raise SystemExit(1)
