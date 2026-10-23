"""Explicit evaluation-only continuation; original uncertain receipts survive.

No activation on import. An operator must call authorize_repeat after a new
user authorization. Standard SearchBudget instances remain fail closed. This
view never converts an uncertain attempt into a reported or unexecuted one.
"""
from datetime import datetime, timezone
import json
import re

from app.services.openrouter_embeddings import _decimal
from app.services.search_budget import SearchBudget
from app.services.search_providers import EMBEDDING
from app.services.semantic_search import SemanticError, _hash

APPROVAL = "evaluation_single_document_repeat_v1"
REPEAT = "evaluation_single_document_repeat_number_v1"
COMPLETE = "evaluation_single_document_repeat_complete_v1"
NEW_HALT = "evaluation_continuation_halted_v1"


class ContinuedBudget(SearchBudget):
    """Opt-in view of the SAME durable ledger, with one appended exception."""
    @classmethod
    def view(cls, original):
        value = cls.__new__(cls)
        value.__dict__ = original.__dict__.copy()
        return value

    def _approval(self):
        try:
            approval = json.loads(self._value(APPROVAL) or "null")
            row = self.db.execute("SELECT * FROM search_budget_receipts WHERE number=?",
                (approval["unknown_number"],)).fetchone()
            if (approval["version"] != "explicit-single-document-repeat.v1"
                    or approval["grant"] != self.authorization.fingerprint
                    or not row or _hash(dict(row)) != approval["original_receipt_sha256"]
                    or row["state"] != "uncertain" or row["purpose"] != "document"
                    or row["scope"] != "public-evaluation.v2" or row["cost"] is not None
                    or self._value("authorization") != self.authorization.fingerprint
                    or _decimal(row["reservation"]) != 0
                    or _decimal(self.authorization.limit_usd) != 0
                    or self._value("halted") != "search_provider_unavailable"):
                raise ValueError
            return approval, dict(row)
        except (TypeError, KeyError, ValueError):
            raise SemanticError("search_recovery_not_authorized") from None

    def authorize_repeat(self, unknown_number, input_hash):
        if self._value(APPROVAL):
            saved, original = self._approval()
            if original["number"] != unknown_number or original["input_hash"] != input_hash:
                raise SemanticError("search_recovery_authorization_changed")
            return saved
        rows = super().summary()["receipts"]
        if (not rows or rows[-1]["number"] != unknown_number
                or self._value("authorization") != self.authorization.fingerprint
                or rows[-1]["input_hash"] != input_hash
                or any(r["state"] not in {"reported", "not_sent"} for r in rows[:-1])
                or rows[-1]["state"] != "uncertain" or rows[-1]["cost"] is not None
                or rows[-1]["purpose"] != "document" or rows[-1]["scope"] != "public-evaluation.v2"
                or _decimal(rows[-1]["reservation"]) != 0 or _decimal(self.authorization.limit_usd) != 0
                or self._value("halted") != "search_provider_unavailable"):
            raise SemanticError("search_recovery_authorization_invalid")
        value = {"version":"explicit-single-document-repeat.v1", "grant":self.authorization.fingerprint,
            "unknown_number":unknown_number, "input_hash":input_hash,
            "original_receipt_sha256":_hash(rows[-1]), "max_additional_repeats":1,
            "model":EMBEDDING.model, "provider":EMBEDDING.provider,
            "note":"New explicit user authorization; original execution/usage remains unknown"}
        with self.db:
            self.db.execute("INSERT INTO search_budget_meta VALUES (?,?)", (APPROVAL,json.dumps(value)))
        return value

    def reserve(self, purpose, scope, *, input_hash, tokens, reservation):
        if (purpose not in {"decision","document","query","rerank"}
                or scope not in {"public-evaluation.v2","persistent-test-library.v1"}
                or not isinstance(input_hash,str) or not re.fullmatch(r"[a-f0-9]{64}",input_hash)
                or type(tokens) is not int or not 0 < tokens <= 100000 or _decimal(reservation) != 0):
            raise SemanticError("search_reservation_invalid")
        try:
            self.db.execute("BEGIN IMMEDIATE")
            approval, original = self._approval()
            rows = [dict(r) for r in self.db.execute("SELECT * FROM search_budget_receipts ORDER BY number")]
            others = [r for r in rows if r["number"] != original["number"]]
            repeat = self._value(REPEAT)
            if (self.clock() >= self.authorization.expires or self._value(NEW_HALT)
                    or len(rows) >= self.authorization.max_posts
                    or any(r["state"] not in {"reported","not_sent"} for r in others)
                    or any(_decimal(r["cost"] or 0) != 0 for r in rows)):
                raise SemanticError("search_budget_blocked")
            if not self._value(COMPLETE):
                if (repeat is not None or rows[-1]["number"] != original["number"]
                        or purpose != original["purpose"] or scope != original["scope"]
                        or input_hash != original["input_hash"] or tokens != original["tokens"]):
                    raise SemanticError("search_recovery_repeat_mismatch")
            elif purpose == "document" and input_hash == original["input_hash"]:
                raise SemanticError("search_recovery_repeat_exhausted")
            cursor = self.db.execute("""INSERT INTO search_budget_receipts
                (purpose,scope,input_hash,tokens,reservation,state,evidence)
                VALUES (?,?,?,?,'0','pending','{}')""",(purpose,scope,input_hash,tokens))
            if repeat is None:
                self.db.execute("INSERT INTO search_budget_meta VALUES (?,?)",(REPEAT,str(cursor.lastrowid)))
            self.db.commit()
            return cursor.lastrowid
        except Exception:
            self.db.rollback()
            raise

    def fail(self, number, code, elapsed):
        if not isinstance(code,str) or not re.fullmatch(r"[a-z_0-9]{1,80}",code):
            code = "search_provider_unavailable"
        # Preserve the historical halt too. New failures have their own marker.
        with self.db:
            self.db.execute("UPDATE search_budget_receipts SET state=CASE WHEN state='reported'"
                " THEN state ELSE 'uncertain' END,elapsed_ms=? WHERE number=?",(round(elapsed*1000,3),number))
            self.db.execute("INSERT OR REPLACE INTO search_budget_meta VALUES (?,?)",
                (NEW_HALT,json.dumps({"number":number,"code":code})))

    def complete_repeat(self, store, spec, texts):
        approval, original = self._approval()
        number = self._value(REPEAT)
        row = self.db.execute("SELECT * FROM search_budget_receipts WHERE number=?",(number,)).fetchone()
        body = {"input":list(texts),"encoding_format":"float","input_type":"passage"}
        evidence = json.loads(row["evidence"]) if row else {}
        if (self._value(COMPLETE) or self._value(NEW_HALT) or not row
                or row["state"] != "reported" or _decimal(row["cost"]) != 0
                or row["input_hash"] != original["input_hash"]
                or _hash([body,"document"]) != original["input_hash"]
                or evidence.get("model") not in {EMBEDDING.model,EMBEDDING.model.removesuffix(":free")}
                or evidence.get("provider") not in {None,EMBEDDING.provider,EMBEDDING.provider_name}
                or not evidence.get("id")
                or any(store.cached_vector(text,spec,query=False) is None for text in texts)):
            raise SemanticError("search_recovery_incomplete")
        value = {"unknown_number":original["number"],"repeat_number":row["number"],
            "input_hash":original["input_hash"],"cached_text_hashes":[_hash(t) for t in texts],
            "spec":spec.fingerprint,"original_status":"uncertain","original_cost":None}
        with self.db:
            self.db.execute("INSERT INTO search_budget_meta VALUES (?,?)",(COMPLETE,json.dumps(value)))
        return value

    def summary(self):
        result = super().summary()
        result["historical_halted"] = result["halted"]
        result["recovery_complete"] = bool(self._value(COMPLETE))
        result["acknowledged_uncertain_receipts"] = []
        if self._value(NEW_HALT):
            result["halted"] = json.loads(self._value(NEW_HALT))["code"]
        try:
            approval, original = self._approval()
            other_unsettled = any(r["number"] != original["number"] and r["state"] not in {"reported","not_sent"}
                for r in result["receipts"])
            if self._value(COMPLETE) and not self._value(NEW_HALT) and not other_unsettled:
                result["halted"] = None
                result["acknowledged_uncertain_receipts"] = [original["number"]]
        except SemanticError:
            pass
        return result


class IndexTimeoutClient:
    """Only passage indexing timeout changes; the native wire body is intact."""
    def __init__(self, client):
        self.client = client
        self.quotes = client.quotes

    def request(self, endpoint, body, **options):
        if options["purpose"] == "document":
            options = {**options,"timeout":60}
        return self.client.request(endpoint,body,**options)


class TraceSession:
    """Append safe transport timing/headers; never inputs or auth headers."""
    def __init__(self, session, ledger, directory):
        self.session,self.ledger,self.directory = session,ledger,directory

    def get(self,*args,**kwargs):
        return self.session.get(*args,**kwargs)

    def post(self,url,**kwargs):
        number = self.ledger.summary()["attempts"]
        path = self.directory / f"transport-{number:03}.jsonl"
        def record(event,**fields):
            import os
            with path.open('a',encoding='utf-8') as output:
                output.write(json.dumps({"event":event,"utc":datetime.now(timezone.utc).isoformat(),**fields})+'\n')
                output.flush(); os.fsync(output.fileno())
        record("transport_invoked",number=number,timeout=kwargs["timeout"],
            model=kwargs["json"]["model"],request_body_hash=_hash(kwargs["json"]))
        try:
            response = self.session.post(url,**kwargs)
            headers = {k:v[:180] for k,v in response.headers.items()
                if k.lower() in {"x-request-id","x-openrouter-request-id","cf-ray","date"}}
            record("headers_received",status=response.status_code,headers=headers)
        except Exception as error:
            record("transport_exception",exception_type=type(error).__name__)
            raise
        class TracedResponse:
            status_code=response.status_code
            def iter_content(self,size):
                try:
                    yield from response.iter_content(size)
                    record("body_complete")
                except Exception as error:
                    record("body_exception",exception_type=type(error).__name__)
                    raise
            def close(self): response.close()
        return TracedResponse()

    def close(self):
        self.session.close()
