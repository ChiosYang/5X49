from __future__ import annotations

import ipaddress
import json
import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import uuid4

from app.contracts.analysis_v2 import AnalysisPredicate, AnalysisQualifier
from app.contracts.structured_metadata import (
    MAX_REVIEW_RAW_BYTES,
    canonical_json_hash,
    normalize_metadata_text,
    validate_provenance_ref,
    validate_review_raw_value,
)


PREDICATE_VOCABULARY_VERSION = "assertion-predicate.v1"
STRUCTURED_GENRE_IMPORT_POLICY_VERSION = "structured-genre-import.v1"
MAX_EVIDENCE_URI_LENGTH = 2048


class AssertionPredicateKey(StrEnum):
    HAS_GENRE = "HAS_GENRE"
    INFLUENCED_BY = "INFLUENCED_BY"
    REMAKE_OF = "REMAKE_OF"
    ADAPTED_FROM = "ADAPTED_FROM"
    VISUALLY_SIMILAR_TO = "VISUALLY_SIMILAR_TO"
    HAS_THEME = "HAS_THEME"
    HAS_MOVEMENT = "HAS_MOVEMENT"
    HAS_VISUAL_STYLE = "HAS_VISUAL_STYLE"
    HAS_MICRO_GENRE = "HAS_MICRO_GENRE"


@dataclass(frozen=True)
class AssertionPredicateDefinition:
    key: AssertionPredicateKey
    subject_entity_type: str
    object_entity_type: str
    object_concept_kind: str | None
    evidence_policy: str


ASSERTION_PREDICATE_DEFINITIONS = (
    AssertionPredicateDefinition(
        AssertionPredicateKey.HAS_GENRE,
        "film",
        "concept",
        "genre",
        "provenance_only",
    ),
    AssertionPredicateDefinition(
        AssertionPredicateKey.INFLUENCED_BY,
        "film",
        "film",
        None,
        "preferred",
    ),
    AssertionPredicateDefinition(
        AssertionPredicateKey.REMAKE_OF,
        "film",
        "film",
        None,
        "preferred",
    ),
    AssertionPredicateDefinition(
        AssertionPredicateKey.ADAPTED_FROM,
        "film",
        "film",
        None,
        "preferred",
    ),
    AssertionPredicateDefinition(
        AssertionPredicateKey.VISUALLY_SIMILAR_TO,
        "film",
        "film",
        None,
        "optional",
    ),
    AssertionPredicateDefinition(
        AssertionPredicateKey.HAS_THEME,
        "film",
        "concept",
        "theme",
        "optional",
    ),
    AssertionPredicateDefinition(
        AssertionPredicateKey.HAS_MOVEMENT,
        "film",
        "concept",
        "movement",
        "optional",
    ),
    AssertionPredicateDefinition(
        AssertionPredicateKey.HAS_VISUAL_STYLE,
        "film",
        "concept",
        "visual_style",
        "optional",
    ),
    AssertionPredicateDefinition(
        AssertionPredicateKey.HAS_MICRO_GENRE,
        "film",
        "concept",
        "micro_genre",
        "optional",
    ),
)
ASSERTION_PREDICATE_REGISTRY = {
    definition.key: definition for definition in ASSERTION_PREDICATE_DEFINITIONS
}

_MODEL_PREDICATES = frozenset(predicate.value for predicate in AnalysisPredicate)
_PERSISTED_PREDICATES = frozenset(predicate.value for predicate in AssertionPredicateKey)
if _MODEL_PREDICATES != _PERSISTED_PREDICATES - {AssertionPredicateKey.HAS_GENRE.value}:
    raise RuntimeError("Analysis predicate and persistence predicate registries have drifted")

_SENSITIVE_QUERY_KEYS = {
    "access_token",
    "api_key",
    "apikey",
    "auth",
    "authorization",
    "key",
    "secret",
    "sig",
    "signature",
    "token",
}
_REVIEW_ALLOWED_KEYS = {
    "claim",
    "direction_note",
    "display_name",
    "entity_id",
    "entity_type",
    "evidence",
    "external_id",
    "period_end_year",
    "period_start_year",
    "predicate",
    "provider",
    "publisher",
    "qualifiers",
    "relationship_type",
    "release_year",
    "source_title",
    "source_uri",
    "stance",
    "target",
}
_GENRE_IMPORT_ORIGINS = frozenset({"nfo", "tmdb", "legacy_movie"})


def assertion_id() -> str:
    return f"ast_{uuid4().hex}"


def evidence_id() -> str:
    return f"evd_{uuid4().hex}"


def assertion_evidence_id() -> str:
    return f"aev_{uuid4().hex}"


def assertion_provenance_id() -> str:
    return f"aprov_{uuid4().hex}"


def analysis_run_id() -> str:
    return f"arun_{uuid4().hex}"


def analysis_resolution_review_id() -> str:
    return f"arev_{uuid4().hex}"


def assertion_qualifier_hash(qualifiers: AnalysisQualifier | dict[str, Any] | None) -> str:
    if qualifiers is None:
        normalized: dict[str, Any] = {}
    elif isinstance(qualifiers, AnalysisQualifier):
        normalized = qualifiers.model_dump(exclude_none=True)
    else:
        normalized = AnalysisQualifier.model_validate(qualifiers).model_dump(exclude_none=True)
    return canonical_json_hash(normalized)


def assertion_semantic_key(
    *,
    subject_entity_id: str,
    predicate: AssertionPredicateKey | str,
    object_entity_id: str,
    qualifier_hash: str,
) -> str:
    subject = _required_text(subject_entity_id, "subject_entity_id")
    object_id = _required_text(object_entity_id, "object_entity_id")
    if subject == object_id:
        raise ValueError("assertion subject and object must be different")
    predicate_value = AssertionPredicateKey(predicate).value
    return canonical_json_hash(
        {
            "object_entity_id": object_id,
            "predicate": predicate_value,
            "qualifier_hash": _sha256_hex(qualifier_hash, "qualifier_hash"),
            "subject_entity_id": subject,
        }
    )


def analysis_run_idempotency_key(
    *,
    film_id: str,
    analysis_kind: str,
    provider: str,
    model: str,
    prompt_version: str,
    schema_version: str,
    resolver_version: str,
    policy_version: str,
    app_version: str,
    input_hash: str,
) -> str:
    return canonical_json_hash(
        {
            "analysis_kind": _required_text(analysis_kind, "analysis_kind"),
            "app_version": _required_text(app_version, "app_version"),
            "film_id": _required_text(film_id, "film_id"),
            "input_hash": _sha256_hex(input_hash, "input_hash"),
            "model": _required_text(model, "model"),
            "policy_version": _required_text(policy_version, "policy_version"),
            "prompt_version": _required_text(prompt_version, "prompt_version"),
            "provider": _required_text(provider, "provider"),
            "resolver_version": _required_text(resolver_version, "resolver_version"),
            "schema_version": _required_text(schema_version, "schema_version"),
        }
    )


def normalize_evidence_uri(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("evidence URI must be a string")
    candidate = unicodedata.normalize("NFKC", value).strip()
    if not candidate or len(candidate) > MAX_EVIDENCE_URI_LENGTH:
        raise ValueError("evidence URI is empty or exceeds the size limit")
    parsed = urlsplit(candidate)
    scheme = parsed.scheme.casefold()
    if scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("evidence URI must use HTTP or HTTPS")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("evidence URI must not contain user information")

    hostname = parsed.hostname.casefold().rstrip(".")
    if hostname == "localhost" or hostname.endswith(".localhost") or hostname.endswith(".local"):
        raise ValueError("evidence URI host is not public")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise ValueError("evidence URI address is not public")

    query = parse_qsl(parsed.query, keep_blank_values=True)
    for key, _ in query:
        normalized_key = normalize_metadata_text(key).replace("-", "_")
        if normalized_key in _SENSITIVE_QUERY_KEYS:
            raise ValueError("evidence URI contains a sensitive query parameter")
    normalized_query = urlencode(sorted(query), doseq=True)

    host_for_netloc = f"[{hostname}]" if ":" in hostname else hostname
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("evidence URI port is invalid") from exc
    if port is not None and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        host_for_netloc = f"{host_for_netloc}:{port}"
    path = parsed.path or "/"
    normalized = urlunsplit((scheme, host_for_netloc, path, normalized_query, ""))
    if len(normalized) > MAX_EVIDENCE_URI_LENGTH:
        raise ValueError("normalized evidence URI exceeds the size limit")
    return normalized


def evidence_semantic_key(*, source_uri: str, content_hash: str, claim: str) -> str:
    normalized_claim = normalize_metadata_text(claim)
    if not normalized_claim:
        raise ValueError("evidence claim must not be empty")
    return canonical_json_hash(
        {
            "claim": normalized_claim,
            "content_hash": _sha256_hex(content_hash, "content_hash"),
            "source_uri": normalize_evidence_uri(source_uri),
        }
    )


def validate_analysis_review_candidate(value: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError("analysis review candidate must be an object")
    _reject_unknown_review_keys(value)
    validate_review_raw_value(value)
    encoded_size = len(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    )
    if encoded_size > MAX_REVIEW_RAW_BYTES:
        raise ValueError("analysis review candidate exceeds the size limit")
    return value


def analysis_review_key(
    *,
    analysis_run_id: str,
    candidate_kind: str,
    reason_code: str,
    predicate: AssertionPredicateKey | str | None,
    candidate: dict[str, Any],
) -> tuple[str, str]:
    candidate = validate_analysis_review_candidate(candidate)
    candidate_hash = canonical_json_hash(candidate)
    payload = {
        "analysis_run_id": _required_text(analysis_run_id, "analysis_run_id"),
        "candidate_hash": candidate_hash,
        "candidate_kind": _required_text(candidate_kind, "candidate_kind"),
        "predicate": AssertionPredicateKey(predicate).value if predicate is not None else None,
        "reason_code": _required_text(reason_code, "reason_code"),
    }
    return canonical_json_hash(payload), candidate_hash


def validate_assertion_semantics(
    *,
    predicate: AssertionPredicateKey | str,
    subject_entity_type: str,
    object_entity_type: str,
    object_concept_kind: str | None = None,
) -> None:
    definition = ASSERTION_PREDICATE_REGISTRY[AssertionPredicateKey(predicate)]
    if subject_entity_type != definition.subject_entity_type:
        raise ValueError("assertion subject entity type does not match the predicate")
    if object_entity_type != definition.object_entity_type:
        raise ValueError("assertion object entity type does not match the predicate")
    if definition.object_concept_kind != object_concept_kind:
        raise ValueError("assertion object Concept kind does not match the predicate")


def validate_automatic_assertion_decision(
    *,
    predicate: AssertionPredicateKey | str,
    source_scope: str,
    review_status: str,
    review_method: str,
    origin_kind: str,
    review_policy_version: str | None = None,
) -> None:
    predicate_value = AssertionPredicateKey(predicate)
    if (
        predicate_value == AssertionPredicateKey.HAS_GENRE
        and source_scope == "factual"
        and review_status == "accepted"
        and review_method == "import_policy"
        and review_policy_version == STRUCTURED_GENRE_IMPORT_POLICY_VERSION
        and origin_kind in _GENRE_IMPORT_ORIGINS
    ):
        return
    if not (
        source_scope == "inferred"
        and review_status == "proposed"
        and review_method == "none"
        and review_policy_version is None
    ):
        raise ValueError("automatic assertions must be inferred proposals or trusted Genre facts")


def preserve_review_status(existing_status: str, requested_status: str) -> str:
    if existing_status not in {"proposed", "accepted", "rejected"}:
        raise ValueError("existing assertion review status is invalid")
    if requested_status not in {"proposed", "accepted", "rejected"}:
        raise ValueError("requested assertion review status is invalid")
    if existing_status in {"accepted", "rejected"}:
        return existing_status
    return requested_status


def _sha256_hex(value: str, field_name: str) -> str:
    normalized = _required_text(value, field_name)
    if not re.fullmatch(r"[0-9a-f]{64}", normalized):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 hex digest")
    return normalized


def _required_text(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = unicodedata.normalize("NFKC", value).strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized


def _reject_unknown_review_keys(value: Any) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key not in _REVIEW_ALLOWED_KEYS:
                raise ValueError("analysis review candidate contains an unsupported field")
            _reject_unknown_review_keys(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            _reject_unknown_review_keys(child)


def predicate_seed_rows() -> tuple[dict[str, str | None], ...]:
    return tuple(
        {
            "key": definition.key.value,
            "vocabulary_version": PREDICATE_VOCABULARY_VERSION,
            "subject_entity_type": definition.subject_entity_type,
            "object_entity_type": definition.object_entity_type,
            "object_concept_kind": definition.object_concept_kind,
            "evidence_policy": definition.evidence_policy,
        }
        for definition in ASSERTION_PREDICATE_DEFINITIONS
    )
