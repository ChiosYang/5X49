"""Database-only display overrides; automatic Film/source/identity rows stay intact."""
from uuid import uuid4
from sqlmodel import Session, select

from app.canonical_models import Film, FilmMetadataOverride, FilmMetadataEdit, LibraryItem, ExternalIdentity
from app.contracts.film_metadata import MetadataUpdate
from app.contracts.structured_metadata import canonical_json_hash
from app.services.provenance_resolver import provenance_resolver


FIELD_ATTRIBUTES = {"title": "canonical_title", "original_title": "original_title",
                    "year": "release_year", "overview": "overview"}


class MetadataConflict(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def effective_film(session: Session, film: Film | None) -> Film | None:
    if film is None:
        return None
    row = session.get(FilmMetadataOverride, film.id)
    if row is None or not row.values:
        return film
    # A detached copy prevents display overrides becoming automatic observations.
    updates = {FIELD_ATTRIBUTES[key]: value for key, value in row.values.items() if key in FIELD_ATTRIBUTES}
    if "year" in row.values:
        updates["release_date"] = None  # An automatic exact date cannot qualify a corrected year.
    return film.model_copy(update=updates)


def metadata_view(session: Session, film_id: str) -> dict:
    film = session.get(Film, film_id)
    if film is None:
        raise LookupError("Film not found")
    if film.lifecycle_status != "active":
        raise MetadataConflict("metadata_film_changed", "Film identity changed; reopen the current Film")
    row = session.get(FilmMetadataOverride, film_id)
    overrides = row.values if row else {}
    automatic = {key: getattr(film, attribute) for key, attribute in FIELD_ATTRIBUTES.items()}
    sources = provenance_resolver.resolve_film(session, film_id).public_sources()
    from app.services.language_metadata import resolved_languages
    languages=resolved_languages(session,film_id,ignore_manual=True)
    for kind,field in (("original","original_language"),("spoken","spoken_languages")):
        automatic[field]=languages[field]
        sources[field]=languages["language_sources"][kind]
    # Historical scalar columns have no per-field provenance. Do not infer an
    # NFO/TMDB owner from a preferred edition or overwrite source history.
    fields = {}
    for key, value in automatic.items():
        source = sources.get(key, {"source_kind": "library", "observed_at": None,
                                  "policy_version": "automatic-scalar.v1", "conflicted": False})
        fields[key] = {"value": overrides.get(key, value), "manual": key in overrides,
                       "automatic_value": value, "automatic_source": source}
    editions = [(item.id, item.film_id, item.availability_status) for item in session.exec(
        select(LibraryItem).where(LibraryItem.film_id == film_id).order_by(LibraryItem.id)).all()]
    identities = [(item.provider, item.external_id, item.identity_status) for item in session.exec(
        select(ExternalIdentity).where(ExternalIdentity.entity_id == film_id).order_by(ExternalIdentity.id)).all()]
    revision = canonical_json_hash({"film_id": film_id, "revision": row.revision if row else 0,
        "fields": fields, "editions": editions, "identities": identities, "lifecycle": film.lifecycle_status})
    return {"film_id": film_id, "revision": revision, "fields": fields}


def update_metadata(database_engine, film_id: str, request: MetadataUpdate) -> dict:
    from app.models import EventRecord, utc_now_iso

    request_hash = canonical_json_hash(request.model_dump(exclude_unset=True))
    with Session(database_engine) as session:
        session.connection().exec_driver_sql("BEGIN IMMEDIATE")
        receipt = session.exec(select(FilmMetadataEdit).where(
            FilmMetadataEdit.film_id == film_id,
            FilmMetadataEdit.idempotency_key == request.idempotency_key)).first()
        if receipt is not None:
            if receipt.request_hash != request_hash:
                raise MetadataConflict("metadata_retry_conflict", "Retry key was already used for another request")
            # Return current state, never reapply an old edit over a subsequent one.
            return {**metadata_view(session, film_id), "replayed": True}
        before = metadata_view(session, film_id)
        if request.revision != before["revision"]:
            raise MetadataConflict("metadata_stale", "Film metadata changed; reload and review before saving")
        row = session.get(FilmMetadataOverride, film_id) or FilmMetadataOverride(film_id=film_id)
        previous = dict(row.values)
        values = dict(previous)
        for field, change in request.changes.items():
            if change.action == "reset":
                values.pop(field, None)
            else:
                values[field] = change.value
        row.values = values
        row.revision += 1
        row.updated_at = utc_now_iso()
        session.add(row)
        edit_id = f"medit_{uuid4().hex}"
        session.add(FilmMetadataEdit(id=edit_id, film_id=film_id,
            idempotency_key=request.idempotency_key, request_hash=request_hash,
            before_values=previous, after_values=values,
            automatic_snapshot={key: {"value": field["automatic_value"], "source": field["automatic_source"]}
                                for key, field in before["fields"].items()}))
        session.add(EventRecord(aggregate_type="film", aggregate_id=film_id,
            type="FilmMetadataEdited", actor_type="user", command_id=edit_id,
            payload={"fields": {key: change.action for key, change in request.changes.items()},
                     "revision": row.revision}))
        session.flush()
        result = {**metadata_view(session, film_id), "replayed": False}
        session.commit()  # Includes synchronous projections; failures roll everything back.
        return result


def display_sources(session: Session, film_id: str, sources: dict) -> dict:
    row = session.get(FilmMetadataOverride, film_id)
    result = dict(sources)
    for key in ("year", "overview"):
        result[key] = {"source_kind": "library", "observed_at": None,
                       "policy_version": "automatic-scalar.v1", "conflicted": False}
    if row:
        for key in row.values:
            result[key] = {"source_kind": "user", "observed_at": row.updated_at,
                           "policy_version": "manual-metadata.v1", "conflicted": False}
    return result
