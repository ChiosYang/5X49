"""Offline contract fixtures by default; live inference is an explicit gated mode.

Never imports app.main or loads private dotenv files. Live mode uses only an
already exported OPENROUTER_API_KEY. It never changes credentials/settings.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import urllib.request

import httpx
from openai import APITimeoutError, OpenAI

from app.contracts.ask import AskQuestion
from app.evaluation.ask_budget import BudgetLedger, BudgetStop, amount, input_upper_bound, INPUT_LIMIT, OUTPUT_LIMIT, BILLING_INPUT_RESERVE, PROMPT_PRICE_CAP, COMPLETION_PRICE_CAP
from app.services.ask import AskError, AskInterpreter

MODEL = "deepseek/deepseek-v4.1-flash"
PROVIDER = "decart/fp4"
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
    try:
        interpreted = interpreter.interpret(AskQuestion(question=case["question"], locale=case["locale"], provider_consent=True))
        status, plan = interpreted.status, interpreted.plan.model_dump() if interpreted.plan else None
        observation = interpreted._observation
    except AskError as error:
        status, plan, observation = error.code, None, error.observation
    passed = status == case["expected"]["status"] and plan == case["expected"]["plan"]
    failure = None if passed else "status_mismatch" if status != case["expected"]["status"] else "constraint_mismatch"
    if not passed and case["expected"]["status"] in {"unsupported", "clarify"} and status == "ready":
        failure = "unsupported_requirement_dropped"
    return {"case_id": case["id"], "category": case["category"], "locale": case["locale"], "passed": passed,
            "failure_category": failure, "actual_status": status, "actual_plan": plan,
            "latency_ms": round((time.perf_counter()-started)*1000, 3), "observation": observation}


def offline():
    with patch.dict(os.environ, {"OPENROUTER_API_KEY": "synthetic-offline-fixture"}):
        rows = [evaluate_case(case, fixture_interpreter(case)) for case in corpus()]
    return {"version": "ask-evaluation.v1", "evidence_class": "offline_fixture_contract_only",
            "model": "offline/fixture-v1", "live_supported_accuracy": None,
            "fixture_cases": len(rows), "fixture_passed": sum(row["passed"] for row in rows),
            "cost_usd": None, "cost_evidence": "no_paid_requests", "cases": rows}


def official_preflight():
    with urllib.request.urlopen(BASE_URL + "/models/" + MODEL + "/endpoints", timeout=20) as response:
        data = json.load(response)["data"]
    endpoints = [item for item in data.get("endpoints", []) if item.get("tag") == PROVIDER]
    if data.get("id") != MODEL or len(endpoints) != 1:
        raise BudgetStop("model_or_provider_changed")
    endpoint = endpoints[0]
    pricing = endpoint.get("pricing") or {}
    if (amount(pricing.get("prompt")) > PROMPT_PRICE_CAP
            or amount(pricing.get("completion")) > COMPLETION_PRICE_CAP
            or amount(pricing.get("request", 0)) != 0
            or endpoint.get("status") != 0
            or type(endpoint.get("context_length")) is not int
            or not 0 < endpoint["context_length"] <= BILLING_INPUT_RESERVE
            or not {"response_format", "max_tokens", "reasoning"}.issubset(endpoint.get("supported_parameters", []))):
        raise BudgetStop("price_or_parameter_preflight_failed")
    return {"checked_at": datetime.now(timezone.utc).isoformat(), "source": BASE_URL + "/models/" + MODEL + "/endpoints",
            "model": MODEL, "provider_tag": PROVIDER, "provider_name": endpoint["provider_name"],
            "pricing": pricing, "token_upper_bound": INPUT_LIMIT, "output_limit": OUTPUT_LIMIT,
            "billing_input_reservation": BILLING_INPUT_RESERVE}


class PaidClient:
    def __init__(self, *, ledger, run_id, case_id, preflight, **options):
        self.ledger, self.run_id, self.case_id, self.preflight = ledger, run_id, case_id, preflight
        self.client = OpenAI(**options)
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.client.close()

    def create(self, **request):
        if request.get("model") != MODEL or request.get("extra_body") != POLICY or request.get("max_tokens") != OUTPUT_LIMIT:
            raise BudgetStop("request_policy_changed")
        bound = input_upper_bound(request["messages"])
        try:
            credit = self.client.get("/credits", cast_to=dict)["data"]
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
        except Exception:
            self.ledger.settle(attempt, cost=None, generation_id=None, outcome="transport_failure")
            raise
        generation_id = response.id
        usage = response.usage
        cost = getattr(usage, "cost", None)
        # Actual provider/model and billing must be corroborated by generation
        # metadata. Read-only lookup is not a second inference call.
        metadata = None
        for delay in (0, 0.5, 1.0):
            if delay:
                time.sleep(delay)
            try:
                metadata = self.client.get("/generation", cast_to=dict, options={"params": {"id": generation_id}})["data"]
                break
            except Exception:
                continue
        if (metadata is None or metadata.get("provider_name") != self.preflight["provider_name"]
                or metadata.get("model") != MODEL or response.model != MODEL
                or cost is None or metadata.get("total_cost") is None
                or abs(amount(cost)-amount(metadata["total_cost"])) > Decimal("0.000000001")):
            self.ledger.settle(attempt, cost=None, generation_id=generation_id, outcome="unknown_billing_or_provider")
        self.ledger.settle(attempt, cost=cost, generation_id=generation_id, outcome="response")
        reasoning_tokens = getattr(getattr(usage, "completion_tokens_details", None), "reasoning_tokens", None)
        if (reasoning_tokens is None or reasoning_tokens != 0
                or usage.prompt_tokens > bound or usage.completion_tokens > OUTPUT_LIMIT):
            self.ledger.block(attempt, "token_or_reasoning_contract_failed")
            raise BudgetStop("token_or_reasoning_contract_failed")
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
            credit = client.get("/credits", cast_to=dict)["data"]
            available = amount(credit["total_credits"]) - amount(credit["total_usage"])
        except Exception:
            raise BudgetStop("credit_balance_unavailable") from None
    worst_request = BILLING_INPUT_RESERVE * PROMPT_PRICE_CAP + OUTPUT_LIMIT * COMPLETION_PRICE_CAP
    if available < worst_request:
        raise BudgetStop("insufficient_existing_credits")
    for index, case in enumerate(cases):
        interpreter = AskInterpreter(provider_config={"model": MODEL, "base_url": BASE_URL, "request_options": POLICY},
            client_factory=lambda **options: PaidClient(ledger=ledger, run_id=args.run_id, case_id=case["id"], preflight=preflight, **options))
        row = evaluate_case(case, interpreter)
        rows.append(row)
        # Ask sanitizes exceptions for the application. The ledger remains the
        # source of truth for any uncertain transport/billing failure.
        summary = ledger.summary()
        if summary["uncertain_billing"] or summary["blocked"]:
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
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--canary-only", action="store_true")
    parser.add_argument("--authorization")
    parser.add_argument("--budget-usd", type=Decimal)
    parser.add_argument("--run-id", default=datetime.now(timezone.utc).strftime("ask-%Y%m%dT%H%M%SZ"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = live(args) if args.live else offline()
    except Exception as error:
        # Never emit provider/credential body strings.
        report = {"version": "ask-evaluation.v1", "evidence_class": "live_synthetic_questions" if args.live else "offline_fixture_contract_only",
                  "complete": False, "stop_reason": str(error) if isinstance(error, BudgetStop) else "evaluation_preflight_failed"}
        if args.live and report["stop_reason"] in {"explicit_1usd_authorization_required", "existing_exported_credential_missing"}:
            report.update(evidence_class="live_evaluation_preflight", paid_requests_in_run=0, cost_usd_in_run=0)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: report.get(key) for key in ("evidence_class", "fixture_cases", "fixture_passed", "complete", "stop_reason", "live_supported_accuracy", "accuracy_gate_passed")}))
    return 0 if (report.get("fixture_passed") == 50 or report.get("accuracy_gate_passed") or args.canary_only and report.get("complete")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
