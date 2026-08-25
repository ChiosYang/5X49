from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any


PROVISIONAL_PERSON_PROVIDER = "legacy.local.person"
MAX_REVIEW_RAW_BYTES = 4096
_SENSITIVE_REVIEW_KEYS = {
    "absolute_path",
    "api_key",
    "authorization",
    "file_path",
    "media_path",
    "path",
    "secret",
    "token",
}


def normalize_metadata_text(value: str) -> str:
    """Return the stable search/deduplication form for metadata text."""
    if not isinstance(value, str):
        raise TypeError("metadata text must be a string")
    normalized = unicodedata.normalize("NFKC", value)
    return " ".join(normalized.split()).casefold()


def canonical_json_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def provisional_person_external_id(source_instance_id: str, name: str) -> str:
    source_instance_id = validate_provenance_ref(source_instance_id)
    normalized_name = normalize_metadata_text(name)
    if not normalized_name:
        raise ValueError("person name must not be empty")
    digest = canonical_json_hash(
        {
            "normalized_name": normalized_name,
            "source_instance_id": source_instance_id,
        }
    )
    return f"sha256:{digest}"


def credit_semantic_key(
    film_id: str,
    person_id: str,
    department: str,
    job: str,
    character: str = "",
) -> str:
    values = {
        "film_id": _required_identifier(film_id, "film_id"),
        "person_id": _required_identifier(person_id, "person_id"),
        "department": normalize_metadata_text(department),
        "job": normalize_metadata_text(job),
        "character": normalize_metadata_text(character),
    }
    if not values["department"] or not values["job"]:
        raise ValueError("credit department and job must not be empty")
    return canonical_json_hash(values)


def structured_metadata_review_key(
    *,
    film_id: str,
    field_kind: str,
    reason_code: str,
    origin_kind: str,
    origin_ref: str,
    raw_value: Any,
) -> tuple[str, str]:
    normalized = {
        "film_id": _required_identifier(film_id, "film_id"),
        "field_kind": normalize_metadata_text(field_kind),
        "reason_code": normalize_metadata_text(reason_code),
        "origin_kind": normalize_metadata_text(origin_kind),
        "origin_ref": validate_provenance_ref(origin_ref),
    }
    if not all(normalized.values()):
        raise ValueError("review identity fields must not be empty")
    raw_value = validate_review_raw_value(raw_value)
    raw_value_hash = canonical_json_hash(raw_value)
    return canonical_json_hash({**normalized, "raw_value_hash": raw_value_hash}), raw_value_hash


def validate_review_raw_value(value: Any) -> Any:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    if len(encoded) > MAX_REVIEW_RAW_BYTES:
        raise ValueError("review raw value exceeds the size limit")
    _reject_sensitive_review_value(value)
    return value


def validate_provenance_ref(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("provenance reference must be a string")
    normalized = unicodedata.normalize("NFKC", value).strip()
    if not normalized:
        raise ValueError("provenance reference must not be empty")
    if "\x00" in normalized:
        raise ValueError("provenance reference contains a null byte")
    if normalized.casefold().startswith("file:"):
        raise ValueError("provenance reference must not be a file URI")
    if PureWindowsPath(normalized).is_absolute() or PurePosixPath(normalized).is_absolute():
        raise ValueError("provenance reference must not be an absolute path")
    if re.match(r"^[a-zA-Z]:[\\/]", normalized):
        raise ValueError("provenance reference must not be an absolute path")
    return normalized


def _required_identifier(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized


def _reject_sensitive_review_value(value: Any) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized_key = normalize_metadata_text(str(key)).replace("-", "_")
            if normalized_key in _SENSITIVE_REVIEW_KEYS:
                raise ValueError("review raw value contains a sensitive field")
            _reject_sensitive_review_value(child)
        return
    if isinstance(value, (list, tuple)):
        for child in value:
            _reject_sensitive_review_value(child)
        return
    if isinstance(value, str):
        candidate = value.strip()
        if candidate.casefold().startswith("file:"):
            raise ValueError("review raw value must not contain a file URI")
        if PureWindowsPath(candidate).is_absolute() or PurePosixPath(candidate).is_absolute():
            raise ValueError("review raw value must not contain an absolute path")
        if re.search(r"\bsk-[a-zA-Z0-9_-]{8,}\b", candidate):
            raise ValueError("review raw value must not contain an API credential")
