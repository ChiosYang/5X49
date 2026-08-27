from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy import text
from sqlmodel import Session, select

from app.canonical_models import (
    Assertion,
    Concept,
    Credit,
    CreditProvenance,
    ExternalIdentity,
    Film,
    FilmCountry,
    FilmCountryProvenance,
    FilmProfileState,
    FilmTitle,
    GraphEntity,
    Person,
    Viewing,
    FRESH_SCHEMA_EPOCH,
)
from app.database import engine


EXPORT_FORMAT_VERSION = "library-export.v1"
DATA_FILE = "library.json"
MANIFEST_FILE = "manifest.json"
PACKAGE_FILES = frozenset({MANIFEST_FILE, DATA_FILE})
MAX_PACKAGE_MEMBER_BYTES = 32 * 1024 * 1024
_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
_CURATED_ORIGINS = frozenset({"curated", "user"})


class PortabilityError(RuntimeError):
    pass


def _json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _row(model: Any, *fields: str) -> dict[str, Any]:
    return {field: getattr(model, field) for field in fields}


def build_export_payload(database_engine=engine) -> tuple[dict[str, Any], int]:
    """Build a stable, path-free portable snapshot without mutating the database."""
    with Session(database_engine) as session:
        epoch = session.exec(
            text("SELECT epoch FROM schema_metadata WHERE id = 1")
        ).one_or_none()
        epoch = epoch[0] if epoch is not None else None
        if epoch != FRESH_SCHEMA_EPOCH:
            raise PortabilityError("database epoch is not exportable")
        schema_version = session.exec(
            text("SELECT MAX(version) FROM schema_migrations WHERE status = 'applied'")
        ).one_or_none()
        schema_version = schema_version[0] if schema_version is not None else None
        if not isinstance(schema_version, int) or schema_version < 1:
            raise PortabilityError("database schema version is unavailable")

        films = session.exec(
            select(Film).where(Film.lifecycle_status != "tombstoned").order_by(Film.id)
        ).all()
        film_ids = {film.id for film in films}
        identities = session.exec(
            select(ExternalIdentity)
            .where(ExternalIdentity.entity_id.in_(film_ids or {""}))
            .where(ExternalIdentity.identity_status != "disputed")
            .order_by(ExternalIdentity.entity_id, ExternalIdentity.provider, ExternalIdentity.external_id)
        ).all()
        titles = session.exec(
            select(FilmTitle)
            .where(FilmTitle.film_id.in_(film_ids or {""}))
            .where(FilmTitle.superseded_at.is_(None))
            .order_by(FilmTitle.film_id, FilmTitle.locale, FilmTitle.title_type, FilmTitle.id)
        ).all()
        profile_states = session.exec(
            select(FilmProfileState)
            .where(FilmProfileState.film_id.in_(film_ids or {""}))
            .order_by(FilmProfileState.film_id)
        ).all()
        viewings = session.exec(
            select(Viewing)
            .where(Viewing.film_id.in_(film_ids or {""}))
            .order_by(Viewing.film_id, Viewing.watched_at, Viewing.id)
        ).all()
        decisions = session.exec(
            select(Assertion)
            .where(Assertion.review_method == "user")
            .where(Assertion.review_status.in_(("accepted", "rejected")))
            .order_by(Assertion.assertion_key)
        ).all()
        decision_entity_ids = {
            entity_id
            for assertion in decisions
            for entity_id in (assertion.subject_entity_id, assertion.object_entity_id)
            if entity_id not in film_ids
        }
        graph_types = {
            entity.id: entity.entity_type
            for entity in session.exec(
                select(GraphEntity).where(GraphEntity.id.in_(decision_entity_ids or {""}))
            ).all()
        }
        concepts = session.exec(
            select(Concept)
            .where(Concept.id.in_(decision_entity_ids or {""}))
            .order_by(Concept.id)
        ).all()
        people = session.exec(
            select(Person)
            .where(Person.id.in_(decision_entity_ids or {""}))
            .order_by(Person.id)
        ).all()

        curated_title_ids = [title.id for title in titles if title.origin_kind in _CURATED_ORIGINS]
        curated_countries = _curated_countries(session, film_ids)
        curated_credits = _curated_credits(session, film_ids)

        payload = {
            "format_version": EXPORT_FORMAT_VERSION,
            "films": [
                _row(
                    film,
                    "id",
                    "canonical_title",
                    "original_title",
                    "release_date",
                    "release_year",
                    "runtime_minutes",
                    "lifecycle_status",
                    "merged_into_id",
                    "updated_at",
                )
                for film in films
            ],
            "external_identities": [
                _row(
                    identity,
                    "id",
                    "entity_id",
                    "provider",
                    "external_id",
                    "identity_status",
                    "verified_at",
                )
                for identity in identities
            ],
            "film_titles": [
                _row(
                    title,
                    "id",
                    "film_id",
                    "locale",
                    "title_type",
                    "title",
                    "origin_kind",
                    "observed_at",
                )
                for title in titles
            ],
            "profile_states": [
                _row(state, "film_id", "favorite", "rating", "notes", "created_at", "updated_at")
                for state in profile_states
            ],
            "viewings": [
                _row(
                    viewing,
                    "id",
                    "film_id",
                    "watched_at",
                    "watched_at_precision",
                    "source",
                    "review_status",
                    "created_at",
                    "updated_at",
                    "deleted_at",
                )
                for viewing in viewings
            ],
            "curated_metadata": {
                "film_title_ids": sorted(curated_title_ids),
                "countries": curated_countries,
                "credits": curated_credits,
            },
            "assertion_decisions": [
                _row(
                    assertion,
                    "id",
                    "assertion_key",
                    "subject_entity_id",
                    "predicate",
                    "object_entity_id",
                    "qualifiers",
                    "source_scope",
                    "review_status",
                    "rationale",
                    "reviewed_at",
                    "updated_at",
                )
                for assertion in decisions
            ],
            "decision_entities": {
                "concepts": [
                    _row(concept, "id", "kind", "canonical_key", "canonical_name", "lifecycle_status")
                    for concept in concepts
                ],
                "people": [
                    _row(person, "id", "canonical_name", "sort_name", "lifecycle_status")
                    for person in people
                ],
                "types": {key: graph_types[key] for key in sorted(graph_types)},
            },
        }
        _validate_payload(payload)
        return payload, schema_version


def export_package(output: Path, *, database_engine=engine, exported_at: str | None = None) -> dict[str, Any]:
    output = output.resolve()
    if output.exists():
        raise PortabilityError("output package already exists")
    if output.suffix.casefold() != ".zip":
        raise PortabilityError("output package must use the .zip extension")
    payload, schema_version = build_export_payload(database_engine)
    data_bytes = _json_bytes(payload)
    content_digest = _sha256(data_bytes)
    manifest = {
        "format_version": EXPORT_FORMAT_VERSION,
        "database_epoch": FRESH_SCHEMA_EPOCH,
        "schema_version": schema_version,
        "content_digest": content_digest,
        "exported_at": exported_at or datetime.now(timezone.utc).isoformat(),
        "logical_clock": None,
        "future_sync": {
            "device_identity_version": None,
            "incremental_cursor_version": None,
            "conflict_policy_version": None,
        },
        "files": [{"name": DATA_FILE, "sha256": content_digest, "bytes": len(data_bytes)}],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as package:
            _write_member(package, MANIFEST_FILE, _json_bytes(manifest))
            _write_member(package, DATA_FILE, data_bytes)
    except Exception:
        if output.exists():
            output.unlink()
        raise
    return manifest


def validate_package(package_path: Path) -> dict[str, Any]:
    package_path = package_path.resolve()
    if not package_path.is_file():
        raise PortabilityError("input package does not exist")
    try:
        with zipfile.ZipFile(package_path, "r") as package:
            names = package.namelist()
            if len(names) != len(set(names)) or set(names) != PACKAGE_FILES:
                raise PortabilityError("package must contain only manifest.json and library.json")
            for info in package.infolist():
                if info.filename.startswith(("/", "\\")) or ".." in Path(info.filename).parts:
                    raise PortabilityError("package contains an unsafe member path")
                if info.file_size > MAX_PACKAGE_MEMBER_BYTES:
                    raise PortabilityError("package member exceeds the size limit")
            manifest = _decode_json(package.read(MANIFEST_FILE), MANIFEST_FILE)
            payload_bytes = package.read(DATA_FILE)
            payload = _decode_json(payload_bytes, DATA_FILE)
    except (zipfile.BadZipFile, KeyError) as exc:
        raise PortabilityError("package is not a valid library export") from exc

    _validate_manifest(manifest)
    _validate_payload(payload)
    digest = _sha256(payload_bytes)
    file_entry = manifest["files"][0]
    if digest != manifest["content_digest"] or digest != file_entry["sha256"]:
        raise PortabilityError("package content digest does not match")
    if file_entry["bytes"] != len(payload_bytes):
        raise PortabilityError("package content length does not match")
    return {
        "status": "passed",
        "format_version": EXPORT_FORMAT_VERSION,
        "database_epoch": manifest["database_epoch"],
        "schema_version": manifest["schema_version"],
        "content_digest": digest,
    }


def _curated_countries(session: Session, film_ids: set[str]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    rows = session.exec(
        select(FilmCountryProvenance)
        .where(FilmCountryProvenance.origin_kind.in_(tuple(_CURATED_ORIGINS)))
        .where(FilmCountryProvenance.superseded_at.is_(None))
        .order_by(FilmCountryProvenance.film_country_id, FilmCountryProvenance.id)
    ).all()
    for provenance in rows:
        country = session.get(FilmCountry, provenance.film_country_id)
        if country is not None and country.film_id in film_ids:
            result.append(
                {
                    "id": country.id,
                    "film_id": country.film_id,
                    "iso_3166_1": country.iso_3166_1,
                    "origin_kind": provenance.origin_kind,
                    "observed_at": provenance.observed_at,
                }
            )
    return sorted(result, key=lambda item: (item["film_id"], item["iso_3166_1"], item["id"]))


def _curated_credits(session: Session, film_ids: set[str]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    rows = session.exec(
        select(CreditProvenance)
        .where(CreditProvenance.origin_kind.in_(tuple(_CURATED_ORIGINS)))
        .where(CreditProvenance.superseded_at.is_(None))
        .order_by(CreditProvenance.credit_id, CreditProvenance.id)
    ).all()
    for provenance in rows:
        credit = session.get(Credit, provenance.credit_id)
        person = session.get(Person, credit.person_id) if credit is not None else None
        if credit is None or person is None or credit.film_id not in film_ids:
            continue
        result.append(
            {
                "id": credit.id,
                "film_id": credit.film_id,
                "person": {
                    "id": person.id,
                    "canonical_name": person.canonical_name,
                    "sort_name": person.sort_name,
                },
                "department": credit.department,
                "job": credit.job,
                "character": credit.character,
                "billing_order": credit.billing_order,
                "origin_kind": provenance.origin_kind,
                "observed_at": provenance.observed_at,
            }
        )
    return sorted(result, key=lambda item: (item["film_id"], item["department"], item["billing_order"] or 0, item["id"]))


def _write_member(package: zipfile.ZipFile, name: str, content: bytes) -> None:
    info = zipfile.ZipInfo(name, date_time=_ZIP_TIMESTAMP)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o600 << 16
    package.writestr(info, content)


def _decode_json(content: bytes, label: str) -> Any:
    if len(content) > MAX_PACKAGE_MEMBER_BYTES:
        raise PortabilityError(f"{label} exceeds the size limit")

    def reject_duplicates(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise PortabilityError(f"{label} contains duplicate JSON keys")
            result[key] = value
        return result

    def reject_constant(value: str) -> Any:
        raise PortabilityError(f"{label} contains a non-finite number: {value}")

    try:
        return json.loads(
            content.decode("utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PortabilityError(f"{label} is not valid UTF-8 JSON") from exc


def _validate_manifest(manifest: Any) -> None:
    expected = {
        "format_version",
        "database_epoch",
        "schema_version",
        "content_digest",
        "exported_at",
        "logical_clock",
        "future_sync",
        "files",
    }
    if not isinstance(manifest, dict) or set(manifest) != expected:
        raise PortabilityError("manifest contract is invalid")
    if manifest["format_version"] != EXPORT_FORMAT_VERSION:
        raise PortabilityError("export contract version is unsupported")
    if manifest["database_epoch"] != FRESH_SCHEMA_EPOCH:
        raise PortabilityError("database epoch is unsupported")
    if not isinstance(manifest["schema_version"], int) or manifest["schema_version"] < 1:
        raise PortabilityError("schema version is invalid")
    if not isinstance(manifest["exported_at"], str):
        raise PortabilityError("export timestamp is invalid")
    try:
        exported_at = datetime.fromisoformat(manifest["exported_at"])
    except ValueError as exc:
        raise PortabilityError("export timestamp is invalid") from exc
    if exported_at.tzinfo is None:
        raise PortabilityError("export timestamp must include a timezone")
    if not _is_sha256(manifest["content_digest"]):
        raise PortabilityError("content digest is invalid")
    if manifest["logical_clock"] is not None:
        raise PortabilityError("library-export.v1 logical clock must be empty")
    if manifest["future_sync"] != {
        "device_identity_version": None,
        "incremental_cursor_version": None,
        "conflict_policy_version": None,
    }:
        raise PortabilityError("future sync contract is invalid")
    files = manifest["files"]
    if not isinstance(files, list) or len(files) != 1:
        raise PortabilityError("manifest file list is invalid")
    entry = files[0]
    if not isinstance(entry, dict) or set(entry) != {"name", "sha256", "bytes"}:
        raise PortabilityError("manifest file entry is invalid")
    if entry["name"] != DATA_FILE or not _is_sha256(entry["sha256"]):
        raise PortabilityError("manifest file identity is invalid")
    if not isinstance(entry["bytes"], int) or not 0 <= entry["bytes"] <= MAX_PACKAGE_MEMBER_BYTES:
        raise PortabilityError("manifest file length is invalid")


def _validate_payload(payload: Any) -> None:
    expected = {
        "format_version",
        "films",
        "external_identities",
        "film_titles",
        "profile_states",
        "viewings",
        "curated_metadata",
        "assertion_decisions",
        "decision_entities",
    }
    if not isinstance(payload, dict) or set(payload) != expected:
        raise PortabilityError("library payload contract is invalid")
    if payload["format_version"] != EXPORT_FORMAT_VERSION:
        raise PortabilityError("library payload version is unsupported")
    for field in expected - {"format_version", "curated_metadata", "decision_entities"}:
        if not isinstance(payload[field], list):
            raise PortabilityError(f"library payload field {field} must be an array")
    if not isinstance(payload["curated_metadata"], dict) or set(payload["curated_metadata"]) != {
        "film_title_ids",
        "countries",
        "credits",
    }:
        raise PortabilityError("curated metadata contract is invalid")
    if not isinstance(payload["decision_entities"], dict) or set(payload["decision_entities"]) != {
        "concepts",
        "people",
        "types",
    }:
        raise PortabilityError("decision entity contract is invalid")
    _require_unique_ids(payload["films"], "films")
    _require_unique_ids(payload["external_identities"], "external identities")
    _require_unique_ids(payload["film_titles"], "film titles")
    _require_unique_ids(payload["viewings"], "viewings")
    _require_unique_ids(payload["assertion_decisions"], "assertion decisions")
    _require_row_contract(
        payload["films"],
        "films",
        {"id", "canonical_title", "original_title", "release_date", "release_year", "runtime_minutes", "lifecycle_status", "merged_into_id", "updated_at"},
    )
    _require_row_contract(
        payload["external_identities"],
        "external identities",
        {"id", "entity_id", "provider", "external_id", "identity_status", "verified_at"},
    )
    _require_row_contract(
        payload["film_titles"],
        "film titles",
        {"id", "film_id", "locale", "title_type", "title", "origin_kind", "observed_at"},
    )
    _require_row_contract(
        payload["profile_states"],
        "profile states",
        {"film_id", "favorite", "rating", "notes", "created_at", "updated_at"},
    )
    _require_row_contract(
        payload["viewings"],
        "viewings",
        {"id", "film_id", "watched_at", "watched_at_precision", "source", "review_status", "created_at", "updated_at", "deleted_at"},
    )
    _require_row_contract(
        payload["assertion_decisions"],
        "assertion decisions",
        {"id", "assertion_key", "subject_entity_id", "predicate", "object_entity_id", "qualifiers", "source_scope", "review_status", "rationale", "reviewed_at", "updated_at"},
    )
    _validate_nested_payload(payload)
    serialized_keys = {key.casefold() for key in _walk_keys(payload)}
    forbidden_keys = {
        "locator",
        "source_item_key",
        "origin_ref",
        "provenance_ref",
        "api_key",
        "secret",
        "token",
        "job",
        "workflow",
        "event",
        "setting",
        "read_model",
    }
    if serialized_keys & forbidden_keys:
        raise PortabilityError("library payload contains operational or secret fields")


def _walk_keys(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        for key, child in value.items():
            yield str(key)
            yield from _walk_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_keys(child)


def _require_unique_ids(rows: Any, label: str) -> None:
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise PortabilityError(f"{label} must be an object array")
    ids = [row.get("id") for row in rows]
    if any(not isinstance(value, str) or not value for value in ids) or len(ids) != len(set(ids)):
        raise PortabilityError(f"{label} contain invalid or duplicate IDs")


def _require_row_contract(rows: Any, label: str, fields: set[str]) -> None:
    if not isinstance(rows, list) or any(
        not isinstance(row, dict) or set(row) != fields for row in rows
    ):
        raise PortabilityError(f"{label} row contract is invalid")


def _validate_nested_payload(payload: dict[str, Any]) -> None:
    curated = payload["curated_metadata"]
    if not isinstance(curated["film_title_ids"], list) or any(
        not isinstance(value, str) for value in curated["film_title_ids"]
    ):
        raise PortabilityError("curated title references are invalid")
    if len(curated["film_title_ids"]) != len(set(curated["film_title_ids"])):
        raise PortabilityError("curated title references contain duplicates")
    _require_row_contract(
        curated["countries"],
        "curated countries",
        {"id", "film_id", "iso_3166_1", "origin_kind", "observed_at"},
    )
    _require_row_contract(
        curated["credits"],
        "curated credits",
        {"id", "film_id", "person", "department", "job", "character", "billing_order", "origin_kind", "observed_at"},
    )
    _require_unique_ids(curated["countries"], "curated countries")
    _require_unique_ids(curated["credits"], "curated credits")
    for credit in curated["credits"]:
        person = credit.get("person")
        if not isinstance(person, dict) or set(person) != {"id", "canonical_name", "sort_name"}:
            raise PortabilityError("curated credit person contract is invalid")

    entities = payload["decision_entities"]
    _require_unique_ids(entities["concepts"], "decision concepts")
    _require_unique_ids(entities["people"], "decision people")
    _require_row_contract(
        entities["concepts"],
        "decision concepts",
        {"id", "kind", "canonical_key", "canonical_name", "lifecycle_status"},
    )
    _require_row_contract(
        entities["people"],
        "decision people",
        {"id", "canonical_name", "sort_name", "lifecycle_status"},
    )
    if not isinstance(entities["types"], dict) or any(
        not isinstance(key, str) or value not in {"person", "concept"}
        for key, value in entities["types"].items()
    ):
        raise PortabilityError("decision entity types are invalid")
    concept_ids = {row["id"] for row in entities["concepts"]}
    person_ids = {row["id"] for row in entities["people"]}
    if set(entities["types"]) != concept_ids | person_ids:
        raise PortabilityError("decision entity type references are incomplete")
    if any(entities["types"][entity_id] != "concept" for entity_id in concept_ids) or any(
        entities["types"][entity_id] != "person" for entity_id in person_ids
    ):
        raise PortabilityError("decision entity types do not match their rows")

    film_ids = {row["id"] for row in payload["films"]}
    title_ids = {row["id"] for row in payload["film_titles"]}
    decision_entity_ids = set(entities["types"])
    if any(row["entity_id"] not in film_ids for row in payload["external_identities"]):
        raise PortabilityError("external identity references an unknown Film")
    for field in ("film_titles", "profile_states", "viewings"):
        if any(row["film_id"] not in film_ids for row in payload[field]):
            raise PortabilityError(f"{field} references an unknown Film")
    if len({row["film_id"] for row in payload["profile_states"]}) != len(payload["profile_states"]):
        raise PortabilityError("profile states contain duplicate Film rows")
    if not set(curated["film_title_ids"]).issubset(title_ids):
        raise PortabilityError("curated title reference is missing")
    if any(row["film_id"] not in film_ids for row in curated["countries"] + curated["credits"]):
        raise PortabilityError("curated metadata references an unknown Film")
    for decision in payload["assertion_decisions"]:
        for entity_id in (decision["subject_entity_id"], decision["object_entity_id"]):
            if entity_id not in film_ids and entity_id not in decision_entity_ids:
                raise PortabilityError("assertion decision references an unknown entity")


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="5X49 local-first portability tools")
    subparsers = parser.add_subparsers(dest="command", required=True)
    export_parser = subparsers.add_parser("export", help="Create a read-only library-export.v1 package")
    export_parser.add_argument("--output", type=Path, required=True)
    validate_parser = subparsers.add_parser("validate", help="Validate a library-export.v1 package")
    validate_parser.add_argument("--input", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "export":
            result = export_package(args.output)
        else:
            result = validate_package(args.input)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
        return 0
    except PortabilityError as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "EXPORT_FORMAT_VERSION",
    "PortabilityError",
    "build_export_payload",
    "export_package",
    "validate_package",
]
