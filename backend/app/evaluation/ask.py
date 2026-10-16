"""Offline contract fixtures by default; live inference is an explicit gated mode.

Never imports app.main or loads private dotenv files. Live mode uses only an
already exported OPENROUTER_API_KEY. It never changes credentials/settings.
"""
from __future__ import annotations

import argparse
import hashlib
from datetime import datetime, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import re
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import urllib.request

import httpx
from openai import APITimeoutError, OpenAI

from app.contracts.ask import AskQuestion
from app.evaluation.ask_budget import BudgetLedger, BudgetStop, amount, input_upper_bound, INPUT_LIMIT, OUTPUT_LIMIT, BILLING_INPUT_RESERVE, PROMPT_PRICE_CAP, COMPLETION_PRICE_CAP
from app.evaluation.ask_review import authorize_conservative_continuation, release_review_hold
from app.services.ask import AskError, AskInterpreter

MODEL = "deepseek/deepseek-v4.1-flash"
CANONICAL_MODEL = "deepseek/deepseek-v4.1-flash-20260910"
PROVIDER = "decart/fp4"
PROVIDER_NAME = "Decart"
BASE_URL = "https://openrouter.ai/api/v1"
FIXTURES = Path(__file__).parent / "fixtures/ask_acceptance.json"
ARTIFACTS = Path(__file__).resolve().parents[2] / ".evaluation-artifacts"
LEDGER = ARTIFACTS / "ask-live-budget.sqlite3"
AUTHORIZATION = "I_AUTHORIZE_SYNTHETIC_OPENROUTER_TESTS_WITHIN_1_USD_TOTAL"
POLICY = {"provider": {"only": [PROVIDER], "allow_fallbacks": False, "require_parameters": True,
                      "max_price": {"prompt": 0.10, "completion": 0.20, "request": 0}},
          "reasoning": {"enabled": False}}


def corpus():
    return json.loads(FIXTURES.read_text(encoding="utf-8"))["cases"]


def fixture_interpreter(case):
    expected = case["expected"]
    content = case.get("fixture_response", json.dumps({**expected, "reason": None if expected["status"] == "ready" else "unsupported_filter" if expected["status"] == "unsupported" else "ambiguous_request"}))
    client = MagicMock()
    client.__enter__.return_value = client
    client.chat.completions.create.return_value = SimpleNamespace(choices=[SimpleNamespace(
        message=SimpleNamespace(content=content), finish_reason="stop")], model="offline/fixture-v1", usage=None, id=None)
    if expected["status"] == "ask_timeout":
        client.chat.completions.create.side_effect = APITimeoutError(request=httpx.Request("POST", "https://example.test"))
    elif expected["status"] == "ask_provider_unavailable":
        client.chat.completions.create.side_effect = RuntimeError("synthetic failure")
    return AskInterpreter(client_factory=MagicMock(return_value=client), provider_config={"model": "offline/fixture-v1", "base_url": BASE_URL})


def evaluate_case(case, interpreter):
    started = time.perf_counter()
    observation = None
    transport_error = None
    receipt_error = None
    try:
        interpreted = interpreter.interpret(AskQuestion(question=case["question"], locale=case["locale"], provider_consent=True, provider_disclosure=interpreter.disclosure()["disclosure_id"]))
        status, plan = interpreted.status, interpreted.plan.model_dump() if interpreted.plan else None
        observation = interpreted._observation
    except AskError as error:
        status, plan, observation = error.code, None, error.observation
        transport_error = getattr(error, "_evaluation_transport_error", None)
        receipt_error = getattr(error, "_evaluation_receipt_error", None)
    passed = status == case["expected"]["status"] and plan == case["expected"]["plan"]
    failure = None if passed else "status_mismatch" if status != case["expected"]["status"] else "constraint_mismatch"
    if not passed and case["expected"]["status"] in {"unsupported", "clarify"} and status == "ready":
        failure = "unsupported_requirement_dropped"
    row = {"case_id": case["id"], "category": case["category"], "locale": case["locale"], "passed": passed,
           "failure_category": failure, "actual_status": status, "actual_plan": plan,
           "latency_ms": round((time.perf_counter()-started)*1000, 3), "observation": observation}
    if transport_error is not None:
        row["transport_error"] = transport_error
    if receipt_error is not None:
        row["receipt_error"] = receipt_error
    return row


def offline():
    with patch.dict(os.environ, {"OPENROUTER_API_KEY": "synthetic-offline-fixture"}):
        rows = [evaluate_case(case, fixture_interpreter(case)) for case in corpus()]
    return {"version": "ask-evaluation.v1", "evidence_class": "offline_fixture_contract_only",
            "model": "offline/fixture-v1", "live_supported_accuracy": None,
            "fixture_cases": len(rows), "fixture_passed": sum(row["passed"] for row in rows),
            "cost_usd": None, "cost_evidence": "no_paid_requests", "cases": rows}


def official_preflight():
    directory_source = BASE_URL + "/models"
    with urllib.request.urlopen(directory_source, timeout=20) as response:
        models = json.load(response)["data"]
    matches = [item for item in models if item.get("id") == MODEL]
    if len(matches) != 1 or matches[0].get("canonical_slug") != CANONICAL_MODEL:
        raise BudgetStop("official_model_mapping_changed")
    with urllib.request.urlopen(BASE_URL + "/models/" + MODEL + "/endpoints", timeout=20) as response:
        data = json.load(response)["data"]
    endpoints = [item for item in data.get("endpoints", []) if item.get("tag") == PROVIDER]
    if data.get("id") != MODEL or len(endpoints) != 1:
        raise BudgetStop("model_or_provider_changed")
    endpoint = endpoints[0]
    pricing = endpoint.get("pricing") or {}
    if (endpoint.get("provider_name") != PROVIDER_NAME
            or amount(pricing.get("prompt")) > PROMPT_PRICE_CAP
            or amount(pricing.get("completion")) > COMPLETION_PRICE_CAP
            or amount(pricing.get("request", 0)) != 0
            or endpoint.get("status") != 0
            or type(endpoint.get("context_length")) is not int
            or not 0 < endpoint["context_length"] <= BILLING_INPUT_RESERVE
            or not {"response_format", "max_tokens", "reasoning"}.issubset(endpoint.get("supported_parameters", []))):
        raise BudgetStop("price_or_parameter_preflight_failed")
    return {"checked_at": datetime.now(timezone.utc).isoformat(), "source": BASE_URL + "/models/" + MODEL + "/endpoints",
            "directory_source": directory_source, "model": MODEL, "canonical_model": CANONICAL_MODEL,
            "provider_tag": PROVIDER, "provider_name": endpoint["provider_name"],
            "pricing": pricing, "token_upper_bound": INPUT_LIMIT, "output_limit": OUTPUT_LIMIT,
            "billing_input_reservation": BILLING_INPUT_RESERVE}


def verify_preflight_identity(preflight):
    # Both accepted strings are pinned and corroborated by the official directory.
    # No prefix/suffix matching, inferred dates or automatic version upgrades.
    if (preflight.get("model") != MODEL or preflight.get("canonical_model") != CANONICAL_MODEL
            or preflight.get("directory_source") != BASE_URL + "/models"
            or preflight.get("source") != BASE_URL + "/models/" + MODEL + "/endpoints"
            or preflight.get("provider_tag") != PROVIDER or preflight.get("provider_name") != PROVIDER_NAME):
        raise BudgetStop("official_model_mapping_changed")


def verify_generation_identity(preflight, metadata, generation_id, response_model=None):
    verify_preflight_identity(preflight)
    if (not isinstance(metadata, dict) or not generation_id
            or metadata.get("id") != generation_id or metadata.get("provider_name") != PROVIDER_NAME
            or metadata.get("model") not in {MODEL, CANONICAL_MODEL}
            or response_model is not None and response_model not in {MODEL, CANONICAL_MODEL}):
        raise BudgetStop("generation_identity_unverified")


def token_count(value, limit):
    if type(value) is not int or not 0 <= value <= limit:
        raise BudgetStop("token_or_reasoning_contract_failed")
    return value


def verify_reconciliation(report, attempt, preflight, metadata, expected_cost):
    """Validate a historical receipt without claiming the lost completion passed."""
    original_attempts = report.get("ledger", {}).get("attempts", [])
    original = [row for row in original_attempts if row.get("id") == attempt["id"]]
    cases = [case for case in corpus() if case["id"] == attempt["case_id"]]
    old = report.get("preflight", {})
    if (len(original) != 1 or len(cases) != 1 or report.get("mode") != "canary"
            or report.get("evidence_class") != "live_synthetic_questions" or report.get("complete") is not False
            or report.get("stop_reason") != "uncertain_billing_stop"
            or report.get("run_id") != attempt["run_id"] or report.get("model") != MODEL
            or report.get("request_policy") != POLICY or len(report.get("cases", [])) != 1
            or report["cases"][0].get("case_id") != attempt["case_id"]
            or original[0].get("generation_id") != attempt["generation_id"]
            or original[0].get("run_id") != attempt["run_id"] or original[0].get("case_id") != attempt["case_id"]
            or original[0].get("state") != "unknown" or original[0].get("cost") is not None
            or original[0].get("outcome") != "unknown_billing_or_provider"
            or original[0].get("reserved") != attempt["reserved"]
            or attempt["outcome"] != original[0]["outcome"]
            or old.get("source") != BASE_URL + "/models/" + MODEL + "/endpoints"
            or old.get("model") != MODEL or old.get("provider_tag") != PROVIDER
            or old.get("provider_name") != PROVIDER_NAME
            or old.get("token_upper_bound") != INPUT_LIMIT or old.get("output_limit") != OUTPUT_LIMIT
            or old.get("billing_input_reservation") != BILLING_INPUT_RESERVE):
        raise BudgetStop("historical_attempt_evidence_mismatch")
    verify_generation_identity(preflight, metadata, attempt["generation_id"])
    if (metadata.get("finish_reason") != "stop" or metadata.get("cancelled") is not False
            or metadata.get("is_byok") is not False or type(metadata.get("native_tokens_cached")) is not int
            or metadata["native_tokens_cached"] != 0
            or metadata.get("cache_discount") not in (None, 0)):
        raise BudgetStop("historical_billing_contract_unverified")
    bound = input_upper_bound([{"content": AskInterpreter.prompt()}, {"content": cases[0]["question"]}])
    prompt = token_count(metadata.get("native_tokens_prompt"), bound)
    completion = token_count(metadata.get("native_tokens_completion"), OUTPUT_LIMIT)
    token_count(metadata.get("tokens_prompt"), bound)
    token_count(metadata.get("tokens_completion"), OUTPUT_LIMIT)
    if metadata.get("native_tokens_reasoning") != 0 or type(metadata.get("native_tokens_reasoning")) is not int:
        raise BudgetStop("token_or_reasoning_contract_failed")
    prices = {}
    for key in ("prompt", "completion", "request"):
        previous = amount(old.get("pricing", {}).get(key, 0 if key == "request" else None))
        current = amount(preflight.get("pricing", {}).get(key, 0 if key == "request" else None))
        if previous != current:
            raise BudgetStop("historical_price_evidence_mismatch")
        prices[key] = str(previous)
    if (amount(prices["request"]) != 0 or amount(prices["prompt"]) > PROMPT_PRICE_CAP
            or amount(prices["completion"]) > COMPLETION_PRICE_CAP):
        raise BudgetStop("historical_price_evidence_mismatch")
    cost = amount(metadata.get("total_cost"))
    calculated = prompt * amount(prices["prompt"]) + completion * amount(prices["completion"])
    if cost != amount(expected_cost) or cost != calculated or cost > amount(attempt["reserved"]):
        raise BudgetStop("historical_cost_evidence_mismatch")
    return {"version": "ask-reconciliation.v1", "requested_model": MODEL, "canonical_model": CANONICAL_MODEL,
            "generation_model": metadata["model"], "provider_tag": PROVIDER, "provider_name": PROVIDER_NAME,
            "directory_source": preflight["directory_source"], "endpoint_source": old["source"],
            "generation_source": BASE_URL + "/generation", "generation_id": metadata["id"],
            "cost_usd": str(cost), "cost_source": "generation.total_cost_and_native_token_arithmetic",
            "native_prompt_tokens": prompt, "native_completion_tokens": completion, "reasoning_tokens": 0,
            "cached_tokens": 0, "prices": prices, "input_upper_bound": bound,
            "completion_usage_available": False, "strict_json_validated": False,
            "original_report_sha256": hashlib.sha256(json.dumps(report, sort_keys=True).encode()).hexdigest()}


def reconcile_canary(report_path, expected_cost):
    if expected_cost is None or not os.getenv("OPENROUTER_API_KEY"):
        raise BudgetStop("reconciliation_cost_and_existing_credential_required")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    original = report.get("ledger", {}).get("attempts", [])
    if len(original) != 1:
        raise BudgetStop("historical_attempt_evidence_mismatch")
    ledger = BudgetLedger(LEDGER)
    attempt = ledger.attempt(original[0]["id"])
    preflight = official_preflight()
    with OpenAI(api_key=os.getenv("OPENROUTER_API_KEY"), base_url=BASE_URL, timeout=20, max_retries=0) as client:
        metadata, lookup = read_generation_receipt(client, attempt["generation_id"])
    evidence = verify_reconciliation(report, attempt, preflight, metadata, expected_cost)
    applied = ledger.reconcile(attempt["id"], evidence=evidence)
    return {"version": "ask-reconciliation.v1", "evidence_class": "read_only_historical_billing_reconciliation",
            "applied": applied, "paid_requests_in_run": 0, "strict_json_validated": False,
            "review_required": True, "evidence": evidence, "receipt_lookup": lookup, "ledger": ledger.summary()}


def transport_error_summary(error):
    # Select only structured exception attributes. Never inspect exception text,
    # request/response objects, headers, bodies, URLs or authentication material.
    status = getattr(error, "status_code", None)
    request_id = getattr(error, "request_id", None)
    allowed_id = (r"(?:req[_-][A-Za-z0-9_-]{8,80}|gen-[0-9]{8,20}-[A-Za-z0-9]{8,80}|"
                  r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12})")
    if (not isinstance(request_id, str) or re.fullmatch(allowed_id, request_id) is None
            or re.search(r"sk-|gh[pousr]_|github_pat|authorization|bearer|password|secret|token|api[_-]?key", request_id, re.I)):
        request_id = None
    chain = []
    seen = set()
    current = error
    while current is not None and id(current) not in seen and len(chain) < 8:
        seen.add(id(current))
        chain.append(type(current).__name__)
        current = current.__cause__ or current.__context__
    return {"exception_type": type(error).__name__,
            "exception_chain_types": chain,
            "http_status": status if type(status) is int and 100 <= status <= 599 else None,
            "request_id": request_id, "settlement_exception_type": None}


class ReceiptLookupError(ValueError):
    def __init__(self, diagnostic):
        super().__init__("generation_receipt_lookup_unverified")
        self.diagnostic = diagnostic


def read_generation_receipt(client, generation_id, *, retry_existing_reads=False):
    """Read one exact receipt; retain only an allowlisted query trace."""
    started = time.perf_counter()
    trace = {"stage": "generation_receipt_lookup", "attempt_count": 0, "elapsed_ms": None, "attempts": []}
    last_error = None
    if not isinstance(generation_id, str) or not generation_id:
        trace["schema_status"] = "requested_id_missing"
    else:
        # Preserve the previous live schedule; reconciliation remains one GET.
        for number, delay in enumerate((0, 0.5, 1.0) if retry_existing_reads else (0,), 1):
            if delay:
                time.sleep(delay)
            attempt_started = time.perf_counter()
            event = {"attempt": number, "http_status": None, "exception_type": None,
                     "schema_status": "not_checked", "id_match": None, "elapsed_ms": None}
            last_error = None
            data = None
            retry = True
            try:
                # Returning the raw response in memory preserves status for a
                # malformed 200 body. No response/body/header is serialized.
                response = client.get("/generation", cast_to=httpx.Response, options={"params": {"id": generation_id}})
                event["http_status"] = response.status_code
                event["schema_status"] = "malformed_json"
                payload = response.json()
                if not isinstance(payload, dict):
                    event["schema_status"] = "envelope_not_object"
                elif "data" not in payload:
                    event["schema_status"] = "missing_data"
                elif not isinstance(payload["data"], dict):
                    event["schema_status"] = "data_not_object"
                    retry = False
                else:
                    data = payload["data"]
                    event["schema_status"] = "valid_receipt_object" if isinstance(data.get("id"), str) and data["id"] else "id_missing_or_invalid"
                    event["id_match"] = data.get("id") == generation_id
                    retry = False
            except Exception as error:
                last_error = error
                summary = transport_error_summary(error)
                for key in ("exception_type", "exception_chain_types"):
                    event[key] = summary[key]
                if summary["http_status"] is not None:
                    event["http_status"] = summary["http_status"]
            event["elapsed_ms"] = round((time.perf_counter() - attempt_started) * 1000, 3)
            trace["attempts"].append(event)
            trace["attempt_count"] = number
            trace["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 3)
            if data is not None and event["id_match"]:
                return data, trace
            if not retry:
                break
    trace["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 3)
    raise ReceiptLookupError(trace) from last_error


class PaidClient:
    def __init__(self, *, ledger, run_id, case_id, preflight, receipt_check=None, **options):
        self.ledger, self.run_id, self.case_id, self.preflight = ledger, run_id, case_id, preflight
        self.receipt_check = receipt_check if receipt_check is not None else {}
        self.client = OpenAI(**options)
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.client.close()

    def _stop_unverified_receipt(self, attempt, generation_id, cause):
        try:
            self.ledger.settle(attempt, cost=None, generation_id=generation_id, outcome="unknown_billing_or_provider")
        except Exception as error:
            self.receipt_check["settlement_exception_type"] = type(error).__name__
        failure = AskError("ask_receipt_unverified", 502)
        failure._evaluation_receipt_error = dict(self.receipt_check)
        raise failure from cause

    def create(self, **request):
        if request.get("model") != MODEL or request.get("extra_body") != POLICY or request.get("max_tokens") != OUTPUT_LIMIT:
            raise BudgetStop("request_policy_changed")
        verify_preflight_identity(self.preflight)
        bound = input_upper_bound(request["messages"])
        try:
            credit = self.client.get("/credits", cast_to=dict[str, object])["data"]
            available = amount(credit["total_credits"]) - amount(credit["total_usage"])
        except Exception:
            raise BudgetStop("credit_balance_unavailable") from None
        if available < BILLING_INPUT_RESERVE * PROMPT_PRICE_CAP + OUTPUT_LIMIT * COMPLETION_PRICE_CAP:
            raise BudgetStop("insufficient_existing_credits")
        # Reserve before any possible paid transport. SQLite BEGIN IMMEDIATE also
        # blocks concurrent runners; an interrupted reservation stops future runs.
        attempt = self.ledger.reserve(self.run_id, self.case_id, bound, OUTPUT_LIMIT)
        try:
            response = self.client.chat.completions.create(**request)
        except Exception as original_error:
            diagnostic = transport_error_summary(original_error)
            try:
                self.ledger.settle(attempt, cost=None, generation_id=None, outcome="transport_failure")
            except Exception as settlement_error:
                # Unknown billing normally raises BudgetStop after persisting the
                # reserve. A settlement/storage failure must also keep the
                # original failure as the cause, without logging its raw text.
                diagnostic["settlement_exception_type"] = type(settlement_error).__name__
            failure = AskError("ask_timeout" if isinstance(original_error, APITimeoutError) else "ask_provider_unavailable",
                               504 if isinstance(original_error, APITimeoutError) else 502)
            failure._evaluation_transport_error = diagnostic
            raise failure from original_error
        generation_id = response.id
        usage = response.usage
        cost = getattr(usage, "cost", None)
        # Actual provider/model and billing must be corroborated by generation
        # metadata. Read-only lookup is not a second inference call.
        self.receipt_check.update(stage="generation_receipt_lookup", completion_response_received=True, receipt_verified=False)
        try:
            metadata, lookup = read_generation_receipt(self.client, generation_id, retry_existing_reads=True)
        except ReceiptLookupError as error:
            self.receipt_check["lookup"] = error.diagnostic
            self._stop_unverified_receipt(attempt, generation_id, error)
        self.receipt_check.update(stage="generation_receipt_verification", lookup=lookup)
        try:
            if response.model not in {MODEL, CANONICAL_MODEL}:
                raise BudgetStop("generation_identity_unverified")
            verify_generation_identity(self.preflight, metadata, generation_id, response.model)
            if cost is None or amount(cost) != amount(metadata.get("total_cost")):
                raise BudgetStop("usage_cost_evidence_mismatch")
        except (BudgetStop, TypeError, AttributeError) as error:
            self.receipt_check["exception_type"] = type(error).__name__
            self._stop_unverified_receipt(attempt, generation_id, error)
        self.ledger.settle(attempt, cost=cost, generation_id=generation_id, outcome="response")
        reasoning_tokens = getattr(getattr(usage, "completion_tokens_details", None), "reasoning_tokens", None)
        try:
            token_count(usage.prompt_tokens, bound)
            token_count(usage.completion_tokens, OUTPUT_LIMIT)
            token_count(metadata.get("native_tokens_prompt"), bound)
            token_count(metadata.get("native_tokens_completion"), OUTPUT_LIMIT)
            if (type(reasoning_tokens) is not int or reasoning_tokens != 0
                    or metadata.get("native_tokens_prompt") != usage.prompt_tokens
                    or metadata.get("native_tokens_completion") != usage.completion_tokens
                    or type(metadata.get("native_tokens_reasoning")) is not int
                    or metadata["native_tokens_reasoning"] != 0):
                raise BudgetStop("token_or_reasoning_contract_failed")
        except (BudgetStop, AttributeError) as error:
            self.ledger.block(attempt, "token_or_reasoning_contract_failed")
            self.receipt_check["exception_type"] = type(error).__name__
            failure = AskError("ask_receipt_unverified", 502)
            failure._evaluation_receipt_error = dict(self.receipt_check)
            raise failure from error
        self.receipt_check.update(stage="generation_receipt_verified", receipt_verified=True)
        return response


def live(args):
    if args.authorization != AUTHORIZATION or args.budget_usd != Decimal("1"):
        raise BudgetStop("explicit_1usd_authorization_required")
    if not os.getenv("OPENROUTER_API_KEY"):
        raise BudgetStop("existing_exported_credential_missing")
    preflight = official_preflight()
    ledger = BudgetLedger(LEDGER)
    rows = []
    stop = None
    # First supported case is a canary. A contract/JSON failure stops this run
    # before any further paid attempts. No automatic interpretation retries.
    cases = [case for case in corpus() if case["category"] not in {"interface_failure", "malicious_format"}]
    if args.canary_only:
        cases = cases[:1]
    # Read-only credits preflight. Unknown balance is a blocker, never an excuse
    # to discover insufficient funds through a paid request or to top up.
    with OpenAI(api_key=os.getenv("OPENROUTER_API_KEY"), base_url=BASE_URL, timeout=20, max_retries=0) as client:
        try:
            credit = client.get("/credits", cast_to=dict[str, object])["data"]
            available = amount(credit["total_credits"]) - amount(credit["total_usage"])
        except Exception:
            raise BudgetStop("credit_balance_unavailable") from None
    worst_request = BILLING_INPUT_RESERVE * PROMPT_PRICE_CAP + OUTPUT_LIMIT * COMPLETION_PRICE_CAP
    if available < worst_request:
        raise BudgetStop("insufficient_existing_credits")
    for index, case in enumerate(cases):
        receipt_check = {}
        interpreter = AskInterpreter(provider_config={"model": MODEL, "base_url": BASE_URL, "request_options": POLICY},
            client_factory=lambda **options: PaidClient(ledger=ledger, run_id=args.run_id, case_id=case["id"], preflight=preflight, receipt_check=receipt_check, **options))
        row = evaluate_case(case, interpreter)
        if receipt_check:
            row["receipt_check"] = receipt_check
        rows.append(row)
        # Ask sanitizes exceptions for the application. The ledger remains the
        # source of truth for any uncertain transport/billing failure.
        summary = ledger.summary()
        if summary["blocking_uncertainty"] or summary["blocked"]:
            stop = "uncertain_billing_stop"
            break
        if row["actual_status"].startswith("ask_") and row["actual_status"] != "ask_private_input":
            stop = "provider_or_contract_failure_stop"
            break
        if index == 0 and not row["passed"]:
            stop = "canary_failed_stop"
            break
    supported_ids = {case["id"] for case in cases if case["expected"]["status"] == "ready"}
    supported = [row for row in rows if row["case_id"] in supported_ids]
    complete = len(rows) == len(cases) and stop is None
    accuracy = sum(row["passed"] for row in supported)/len(supported) if supported else None
    rejected_ids = {case["id"] for case in cases if case["expected"]["status"] != "ready"}
    safety_failures = sum(not row["passed"] for row in rows if row["case_id"] in rejected_ids)
    return {"version": "ask-evaluation.v1", "evidence_class": "live_synthetic_questions", "model": MODEL,
            "run_id": args.run_id, "preflight": preflight, "request_policy": POLICY,
            "complete": complete, "stop_reason": stop, "live_supported_accuracy": accuracy,
            "supported_cases": len(supported), "expected_supported_cases": len(supported_ids),
            "accuracy_gate_passed": live_gate(complete, args.canary_only, accuracy, safety_failures),
            "rejected_case_failures": safety_failures, "mode": "canary" if args.canary_only else "acceptance",
            "unsupported_drop_count": sum(row["failure_category"] == "unsupported_requirement_dropped" for row in rows),
            "ledger": ledger.summary(), "cases": rows}


def live_gate(complete, canary_only, supported_accuracy, rejected_case_failures):
    # Supported accuracy alone cannot excuse silently dropped unsupported input.
    return bool(complete and not canary_only and supported_accuracy is not None
                and supported_accuracy >= 0.95 and rejected_case_failures == 0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--live", action="store_true")
    mode.add_argument("--reconcile-report", type=Path)
    mode.add_argument("--release-review", type=Path, metavar="PRIVATE_APPROVAL_JSON")
    mode.add_argument("--continue-conservatively", type=Path, metavar="PRIVATE_APPROVAL_JSON")
    parser.add_argument("--expected-cost-usd", type=Decimal)
    parser.add_argument("--canary-only", action="store_true")
    parser.add_argument("--authorization")
    parser.add_argument("--budget-usd", type=Decimal)
    parser.add_argument("--run-id", default=datetime.now(timezone.utc).strftime("ask-%Y%m%dT%H%M%SZ"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.continue_conservatively:
            report = authorize_conservative_continuation(args.continue_conservatively, authorization=args.authorization,
                                                        ledger_path=LEDGER, repo_root=Path(__file__).resolve().parents[3])
        elif args.release_review:
            report = release_review_hold(args.release_review, authorization=args.authorization,
                                         ledger_path=LEDGER, repo_root=Path(__file__).resolve().parents[3])
        elif args.reconcile_report:
            report = reconcile_canary(args.reconcile_report, args.expected_cost_usd)
        else:
            report = live(args) if args.live else offline()
    except Exception as error:
        # Never emit provider/credential body strings.
        report = {"version": "ask-evaluation.v1", "evidence_class": "single_full_reserve_continuation" if args.continue_conservatively else "audited_review_hold_release" if args.release_review else "read_only_historical_billing_reconciliation" if args.reconcile_report else "live_synthetic_questions" if args.live else "offline_fixture_contract_only",
                  "complete": False, "stop_reason": str(error) if isinstance(error, BudgetStop) else "evaluation_preflight_failed"}
        if args.live and report["stop_reason"] in {"explicit_1usd_authorization_required", "existing_exported_credential_missing"}:
            report.update(evidence_class="live_evaluation_preflight", paid_requests_in_run=0, cost_usd_in_run=0)
        if args.reconcile_report or args.release_review or args.continue_conservatively:
            report["paid_requests_in_run"] = 0
        if isinstance(error, ReceiptLookupError):
            report["stop_reason"] = "generation_receipt_lookup_unverified"
            report["receipt_error"] = {"stage": "generation_receipt_lookup", "receipt_verified": False,
                                       "lookup": error.diagnostic}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: report.get(key) for key in ("evidence_class", "fixture_cases", "fixture_passed", "complete", "stop_reason", "live_supported_accuracy", "accuracy_gate_passed", "applied", "review_required", "review_released", "continuation_authorized")}))
    if args.continue_conservatively:
        return 0 if report.get("continuation_authorized") else 1
    if args.release_review:
        return 0 if report.get("review_released") else 1
    if args.reconcile_report:
        return 0 if report.get("review_required") and "evidence" in report else 1
    return 0 if (report.get("fixture_cases", 0) >= 50 and report.get("fixture_passed") == report.get("fixture_cases") or report.get("accuracy_gate_passed") or args.canary_only and report.get("complete")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
