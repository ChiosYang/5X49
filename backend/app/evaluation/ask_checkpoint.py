"""Private, bounded response artifacts for synthetic Ask evaluation only."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import uuid

from app.evaluation.ask_budget import BudgetStop, amount

VERSION = "ask-response-checkpoint.v1"
MAX_BYTES = 131072
SOURCE_FILES = (
    "backend/app/evaluation/ask.py", "backend/app/evaluation/ask_checkpoint.py",
    "backend/app/evaluation/ask_budget.py", "backend/app/evaluation/ask_review.py",
    "backend/app/services/ask.py", "backend/app/contracts/ask.py",
)


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def code_identity():
    root = Path(__file__).resolve().parents[3]
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True)
    head = result.stdout.strip()
    if re.fullmatch(r"[0-9a-f]{40}", head) is None:
        raise BudgetStop("checkpoint_code_identity_unavailable")
    return {"head": head, "files": {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
                                   for name in SOURCE_FILES}}


def binding(case, run_id, request, preflight, corpus_path, prompt):
    return {"run_id": run_id, "case_id": case["id"], "locale": case["locale"],
            "case_sha256": digest(case), "request_sha256": digest(request),
            "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
            "corpus_sha256": hashlib.sha256(corpus_path.read_bytes()).hexdigest(),
            "preflight_sha256": digest(preflight), "code": code_identity()}


def linked_path(path):
    path = path.absolute()
    return any(item.is_symlink() or getattr(item, "is_junction", lambda: False)()
               for item in (path, *path.parents))


def atomic_private_json(path, value):
    """Publish a complete fsynced file without replacing any existing name."""
    path = Path(path)
    if linked_path(path):
        raise BudgetStop("checkpoint_path_invalid")
    raw = encoded(value)
    if len(raw) > MAX_BYTES:
        raise BudgetStop("checkpoint_too_large")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / (".checkpoint-" + uuid.uuid4().hex + ".tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        # Same-directory hard-link creation is atomic and refuses an existing
        # destination on Windows and POSIX; os.replace would overwrite evidence.
        os.link(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
    path.chmod(stat.S_IREAD)
    return {"file": path.name, "sha256": hashlib.sha256(raw).hexdigest()}


def _integer(value):
    return value if type(value) is int and value >= 0 else None


def response_fields(response):
    generation, model = response.id, response.model
    if (not isinstance(generation, str) or re.fullmatch(r"gen-[A-Za-z0-9_-]{1,180}", generation) is None
            or model not in {"deepseek/deepseek-v4.1-flash", "deepseek/deepseek-v4.1-flash-20260910"}
            or len(response.choices) != 1):
        raise BudgetStop("checkpoint_response_identity_invalid")
    choice = response.choices[0]
    content = choice.message.content
    if content is not None and (not isinstance(content, str) or len(content) > 12000):
        raise BudgetStop("checkpoint_content_invalid")
    finish = choice.finish_reason
    if finish is not None and (not isinstance(finish, str) or re.fullmatch(r"[a-z_]{1,40}", finish) is None):
        raise BudgetStop("checkpoint_finish_reason_invalid")
    usage = response.usage
    selected = None
    if usage is not None:
        try:
            cost = str(amount(getattr(usage, "cost", None)))
        except (BudgetStop, TypeError, ValueError):
            cost = None
        selected = {key: _integer(getattr(usage, key, None)) for key in
                    ("prompt_tokens", "completion_tokens", "total_tokens")}
        selected.update(cost=cost, reasoning_tokens=_integer(getattr(
            getattr(usage, "completion_tokens_details", None), "reasoning_tokens", None)))
    return {"id": generation, "model": model, "content": content, "finish_reason": finish, "usage": selected}


def save_checkpoint(directory, attempt, context, response):
    if re.fullmatch(r"[0-9a-f]{32}", attempt) is None:
        raise BudgetStop("checkpoint_attempt_invalid")
    payload = {"version": VERSION, "attempt_id": attempt, "binding": context,
               "response": response_fields(response)}
    reference = atomic_private_json(Path(directory) / (attempt + ".json"), payload)
    return {**reference, "binding_sha256": digest(context)}


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def read_verified_json(path, expected_sha256):
    path = Path(path)
    if (not isinstance(expected_sha256, str) or re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None
            or linked_path(path)):
        raise BudgetStop("checkpoint_input_identity_invalid")
    try:
        with path.open("rb") as handle:
            raw = handle.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES or hashlib.sha256(raw).hexdigest() != expected_sha256:
            raise ValueError("digest or length")
        return json.loads(raw, object_pairs_hook=_pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite")))
    except (OSError, ValueError, UnicodeError):
        raise BudgetStop("checkpoint_input_unverified") from None
