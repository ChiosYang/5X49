from __future__ import annotations

import json
import os
import re
from pathlib import Path
from uuid import uuid4


_REFERENCE_PATTERN = re.compile(r"^private_[0-9a-f]{32}$")
_SCHEMA_VERSION = "private-operation-payload.v1"


class PrivatePayloadError(RuntimeError):
    pass


class PrivatePayloadStore:
    def __init__(self, root: Path | None = None):
        configured = Path(os.getenv("OPERATION_MANIFEST_DIR", "data/operation-manifests"))
        self.root = (root or configured).resolve()

    def put(self, payload_kind: str, payload: dict) -> str:
        if not payload_kind or len(payload_kind) > 80:
            raise PrivatePayloadError("Private payload kind is invalid")
        reference = f"private_{uuid4().hex}"
        value = {
            "schema_version": _SCHEMA_VERSION,
            "reference": reference,
            "payload_kind": payload_kind,
            "payload": payload,
        }
        path = self._path(reference)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        temporary.replace(path)
        return reference

    def get(self, reference: str, payload_kind: str) -> dict:
        try:
            value = json.loads(self._path(reference).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PrivatePayloadError("Private operation payload is unavailable") from exc
        if (
            value.get("schema_version") != _SCHEMA_VERSION
            or value.get("reference") != reference
            or value.get("payload_kind") != payload_kind
            or not isinstance(value.get("payload"), dict)
        ):
            raise PrivatePayloadError("Private operation payload contract is invalid")
        return value["payload"]

    def _path(self, reference: str) -> Path:
        if not _REFERENCE_PATTERN.fullmatch(reference or ""):
            raise PrivatePayloadError("Private operation payload reference is invalid")
        return self.root / f"{reference}.json"


private_payload_store = PrivatePayloadStore()


__all__ = ["PrivatePayloadError", "PrivatePayloadStore", "private_payload_store"]
