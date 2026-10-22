"""Explicit synthetic-pilot transport. Never imported by production routing.

Only the reviewed fixture text allowlist may leave this adapter. The client has
no chat/rerank interface, automatic retries, redirects or startup side effects.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from threading import Lock
from time import perf_counter

import requests

from app.services.semantic_search import ProviderSpec, SemanticError, _vector
from app.services.search_privacy import has_private_input

MODEL = "qwen/qwen3-embedding-8b"
# OpenRouter's slug and the exact upstream identity published by Qwen/DeepInfra.
# No fuzzy model matching or automatic substitution.
RESPONSE_MODELS = {MODEL, "Qwen/Qwen3-Embedding-8B"}
PROVIDER = "deepinfra/us"
DIMENSIONS = 4096
ORIGIN = "https://openrouter.ai/api/v1"
PRICE_CEILING = Decimal("0.00000004")  # USD/input token, $0.04/M.
RESERVATION = Decimal("0.01")  # Deliberately far above this bounded payload.
MAX_POSTS, MAX_TEXTS, MAX_TOKENS = 32, 64, 20000
QUERY_PREFIX = "Instruct: Given a film-search query, retrieve relevant film plot descriptions.\nQuery: "


def _decimal(value):
    try:
        if isinstance(value, bool):
            raise ValueError
        result = Decimal(str(value))
        if not result.is_finite() or result < 0:
            raise ValueError
        return result
    except (InvalidOperation, ValueError, TypeError):
        raise SemanticError("invalid_billing") from None


def _json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError
            result[key] = value
        return result
    try:
        return json.loads(raw, object_pairs_hook=pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, TypeError):
        raise SemanticError("invalid_provider_response") from None


def http_session():
    session = requests.Session()
    session.trust_env = False  # No unrelated proxy credentials or netrc.
    session.mount("https://", requests.adapters.HTTPAdapter(max_retries=0))
    return session


def _response_json(response, maximum=8 * 1024 * 1024):
    try:
        if response.status_code != 200:
            raise SemanticError(f"provider_http_{response.status_code}")
        parts, size = [], 0
        for part in response.iter_content(65536):
            size += len(part)
            if size > maximum:
                raise SemanticError("provider_response_limit")
            parts.append(part)
        return _json(b"".join(parts))
    finally:
        response.close()


@dataclass(frozen=True)
class Quote:
    prompt_usd_per_token: Decimal
    model_created: int

    @classmethod
    def from_metadata(cls, payload):
        try:
            data = payload["data"]
            if data["id"] != MODEL or type(data["created"]) is not int or data["created"] <= 0:
                raise ValueError
            endpoints = [e for e in data["endpoints"] if e["tag"] == PROVIDER]
            if len(endpoints) != 1 or endpoints[0]["provider_name"] != "DeepInfra":
                raise ValueError
            endpoint = endpoints[0]
            if (type(endpoint["status"]) is not int or endpoint["status"] != 0
                    or type(endpoint["context_length"]) is not int or endpoint["context_length"] < 20000):
                raise ValueError
            pricing = endpoint["pricing"]
            price = _decimal(pricing["prompt"])
            if not 0 < price <= PRICE_CEILING:
                raise SemanticError("price_exceeds_plan")
            # No unbudgeted per-request, output, image or other nonzero charge.
            if any(_decimal(v) != 0 for k, v in pricing.items() if k not in {"prompt", "discount"}):
                raise SemanticError("unsupported_pricing")
            return cls(price, data["created"])
        except (KeyError, TypeError, ValueError):
            raise SemanticError("invalid_model_quote") from None


def fetch_quote(session):
    try:
        response = session.get(f"{ORIGIN}/models/{MODEL}/endpoints",
                               timeout=20, allow_redirects=False, stream=True)
        return Quote.from_metadata(_response_json(response, 1024 * 1024))
    except SemanticError:
        raise
    except Exception:
        raise SemanticError("quote_unavailable") from None


class BudgetLedger:
    """One durable authorization ledger; any interrupted attempt fails closed."""
    def __init__(self, root: Path, quote: Quote):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=False)
        self.path = root / "budget.json"
        self.data = {"version": "openrouter-synthetic-budget.v1", "limit_usd": "1",
                     "model": MODEL, "provider": PROVIDER,
                     "quoted_prompt_usd_per_token": str(quote.prompt_usd_per_token),
                     "created": datetime.now(timezone.utc).isoformat(),
                     "halted": False, "entries": []}
        self._write()

    def _write(self):
        temp = self.path.with_suffix(".pending")
        with temp.open("w", encoding="utf-8") as output:
            json.dump(self.data, output, ensure_ascii=False, indent=2)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temp, self.path)

    def reserve(self, texts, query):
        entries = self.data["entries"]
        token_bound = sum(len(t.encode("utf-8")) + 256 for t in texts)
        if (self.data["halted"] or any(e["status"] == "pending" for e in entries)
                or len(entries) >= MAX_POSTS
                or sum(e["texts"] for e in entries) + len(texts) > MAX_TEXTS
                or sum(e["reserved_tokens"] for e in entries) + token_bound > MAX_TOKENS
                or RESERVATION * (len(entries) + 1) > Decimal(self.data["limit_usd"])):
            raise SemanticError("pilot_budget_blocked")
        entry = {"number": len(entries) + 1, "status": "pending", "texts": len(texts),
                 "query": query, "reserved_tokens": token_bound,
                 "reserved_usd": str(RESERVATION),
                 "input_hash": sha256(json.dumps(texts, ensure_ascii=False).encode()).hexdigest()}
        entries.append(entry)
        self._write()  # Commit the reservation BEFORE dispatch.
        return entry

    def capture_response(self, entry, payload):
        """Durably retain reconciliation identity before any usage validation."""
        request_id = payload.get("id")
        if (isinstance(request_id, str)
                and re.fullmatch(r"(?:gen|emb|embd)-[A-Za-z0-9_-]{1,150}", request_id)
                and not has_private_input(request_id)):
            entry["request_id"] = request_id
        for field in ("model", "provider"):
            value = payload.get(field)
            if (isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9._/-]{1,160}", value)
                    and not has_private_input(value)):
                entry["response_" + field] = value
        entry["response_received_utc"] = datetime.now(timezone.utc).isoformat()
        self._write()

    def settle(self, entry, payload, quote, elapsed):
        try:
            usage = payload["usage"]
            if not isinstance(usage, dict):
                raise ValueError
            reported = usage.get("cost")
            if reported is not None:
                # An unexpectedly large charge is still an observed charge.
                # Preserve it before stopping; never relabel it as a small hold.
                observed = _decimal(reported)
                entry.update(status="reported", cost_usd=str(observed), cost_basis="usage.cost")
                self._write()
                if observed > RESERVATION:
                    raise SemanticError("cost_exceeds_reservation")
            prompt, total = usage["prompt_tokens"], usage["total_tokens"]
            if (type(prompt) is not int or type(total) is not int
                    or not 0 <= prompt <= total <= entry["reserved_tokens"]):
                raise ValueError
            cost = _decimal(reported) if reported is not None else quote.prompt_usd_per_token * total
            if cost > RESERVATION:
                raise SemanticError("cost_exceeds_reservation")
            entry.update(status="reported" if reported is not None else "estimated",
                         prompt_tokens=prompt, total_tokens=total, cost_usd=str(cost),
                         cost_basis="usage.cost" if reported is not None else "usage.total_tokens * pinned endpoint quote",
                         elapsed_ms=round(elapsed * 1000, 3))
            self._write()
        except (KeyError, TypeError, ValueError):
            raise SemanticError("billing_uncertain") from None

    def halt(self, entry, code, elapsed):
        self.data["halted"] = True
        if entry["status"] == "pending":
            entry["status"] = "uncertain"
        entry.update(error=code, elapsed_ms=round(elapsed * 1000, 3))
        self._write()

    def summary(self):
        entries = self.data["entries"]
        complete = all(e["status"] in {"reported", "estimated"} for e in entries)
        unknown = sum((_decimal(e.get("cost_upper_bound_usd", e["reserved_usd"])) for e in entries
                       if e["status"] in {"uncertain", "pending", "reserved_unknown"}), Decimal(0))
        known = sum((_decimal(e["cost_usd"]) for e in entries if "cost_usd" in e), Decimal(0))
        return {"requests": len(entries), "encoded_texts": sum(e["texts"] for e in entries),
                "total_tokens": sum(e.get("total_tokens", 0) for e in entries),
                "known_or_estimated_cost_usd": str(known),
                "unknown_cost_upper_bound_usd": str(unknown),
                "total_cost_upper_bound_usd": str(known + unknown),
                "cost_complete": complete,
                "all_costs_reported": complete and all(e["status"] == "reported" for e in entries),
                "reserved_usd": str(RESERVATION * len(entries)), "halted": self.data["halted"],
                "entries": entries}


class OpenRouterPilotProvider:
    """Only explicitly approved synthetic inputs; no production credential lookup."""
    def __init__(self, key, quote, ledger, allowed, *, session=None):
        if not isinstance(key, str) or not key.strip() or "\n" in key or "\r" in key:
            raise SemanticError("credential_unavailable")
        self._key, self.quote, self.ledger = key, quote, ledger
        self.allowed, self.session = frozenset(allowed), session or http_session()
        revision = sha256(json.dumps([ORIGIN, MODEL, PROVIDER, DIMENSIONS, QUERY_PREFIX,
            quote.model_created, "zdr-deny-no-fallback.pilot-v1"]).encode()).hexdigest()
        self.spec = ProviderSpec("openrouter:" + MODEL, revision, DIMENSIONS)
        self.memo = {}
        self._dispatch_lock = Lock()

    def close(self):
        self.session.close()

    def embed(self, texts, *, query):
        with self._dispatch_lock:
            return self._embed_serial(texts, query=query)

    def _embed_serial(self, texts, *, query):
        if type(query) is not bool or not isinstance(texts, (list, tuple)) or not 1 <= len(texts) <= 4:
            raise SemanticError("pilot_input_not_authorized")
        for text in texts:
            if (not isinstance(text, str) or (text, query) not in self.allowed
                    or len(text) > 600 or has_private_input(text)):
                raise SemanticError("pilot_input_not_authorized")
        keys = [(text, query) for text in texts]
        if all(key in self.memo for key in keys):
            return [list(self.memo[key]) for key in keys]
        outgoing = [(QUERY_PREFIX + text) if query else text for text in texts]
        if any(has_private_input(t) for t in outgoing):
            raise SemanticError("private_input")
        entry = self.ledger.reserve(outgoing, query)
        started = perf_counter()
        try:
            response = self.session.post(f"{ORIGIN}/embeddings",
                headers={"Authorization": "Bearer " + self._key, "Content-Type": "application/json"},
                json={"model": MODEL, "input": outgoing, "encoding_format": "float",
                      "provider": {"only": [PROVIDER], "allow_fallbacks": False,
                                   "data_collection": "deny", "zdr": True,
                                   "max_price": {"prompt": 0.04, "completion": 0, "request": 0}}},
                timeout=20, allow_redirects=False, stream=True)
            payload = _response_json(response)
            if not isinstance(payload, dict):
                raise SemanticError("invalid_provider_response")
            # Preserve safe accounting/diagnostic metadata even if subsequent
            # model, route or vector validation fails. Never persist vectors.
            self.ledger.capture_response(entry, payload)
            self.ledger.settle(entry, payload, self.quote, perf_counter() - started)
            if payload.get("model") not in RESPONSE_MODELS:
                raise SemanticError("invalid_provider_model")
            if payload.get("provider") not in (None, "DeepInfra", "deepinfra", PROVIDER):
                raise SemanticError("invalid_provider_route")
            rows = payload.get("data")
            if (not isinstance(rows, list) or len(rows) != len(texts)
                    or any(not isinstance(r, dict) or type(r.get("index")) is not int for r in rows)
                    or {r["index"] for r in rows} != set(range(len(texts)))):
                raise SemanticError("invalid_provider_vectors")
            values = [None] * len(texts)
            for row in rows:
                # Validate but retain the original vector; core owns normalization.
                _vector(row.get("embedding"), DIMENSIONS)
                values[row["index"]] = tuple(row["embedding"])
            for key, value in zip(keys, values):
                self.memo[key] = value
            return [list(v) for v in values]
        except Exception as exc:
            code = exc.code if isinstance(exc, SemanticError) else "provider_unavailable"
            self.ledger.halt(entry, code, perf_counter() - started)
            raise SemanticError(code) from None
