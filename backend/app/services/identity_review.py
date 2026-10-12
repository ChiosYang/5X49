"""Read-only identity review evidence. Never resolves Film or edition ownership."""
from __future__ import annotations

import re
from typing import Any

from sqlalchemy import func, or_
from sqlmodel import Session, select

from app.contracts.structured_metadata import canonical_json_hash
from app.models import ExternalIdentity, Film, FilmProfileState, IdentityReview, LibraryItem, MediaAsset, Viewing
from app.services.file_identity import FileIdentityObservation
from app.utils.security import validate_resource_id


REASONS = frozenset({
    "identity_conflict", "relink_identity_conflict", "relink_live_copy_conflict",
    "relink_file_disappeared", "relink_full_hash_no_match", "relink_full_hash_duplicate",
})
MAX_CANDIDATES = 50


def safe_identities(identities: dict[str, Any]) -> dict[str, str]:
    patterns = {"tmdb.movie": r"[0-9]{1,20}", "imdb.title": r"tt[0-9]{1,20}"}
    return {provider: str(value) for provider, value in identities.items()
            if provider in patterns and re.fullmatch(patterns[provider], str(value))}


def _film_snapshot(session: Session, film_id: str) -> dict[str, Any] | None:
    film = session.get(Film, film_id)
    if film is None:
        return None
    identities = session.exec(select(ExternalIdentity)
        .where(ExternalIdentity.entity_id == film_id)
        .where(ExternalIdentity.identity_status == "active")).all()
    return {"id": film.id, "lifecycle": film.lifecycle_status,
            "merged_into_id": film.merged_into_id,
            "identities": sorted((i.provider, i.external_id) for i in identities)}


def _item_snapshot(session: Session, item_id: str) -> dict[str, Any] | None:
    item = session.get(LibraryItem, item_id)
    if item is None:
        return None
    assets = session.exec(select(MediaAsset).where(MediaAsset.library_item_id == item.id)
        .where(MediaAsset.availability_status != "retired").order_by(MediaAsset.id)).all()
    return {"id": item.id, "film_id": item.film_id, "availability": item.availability_status,
            "source_key": item.source_item_key,
            "film": _film_snapshot(session, item.film_id),
            "assets": [(a.id, a.asset_kind, a.normalized_locator_hash, a.content_fingerprint,
                        a.content_hash, a.file_size, a.file_mtime, a.availability_status) for a in assets]}


def seal_source_evidence(session: Session, review: IdentityReview) -> None:
    review.candidate_snapshot = {**(review.candidate_snapshot or {}),
        "source_hash": canonical_json_hash(_item_snapshot(session, review.library_item_id))}
    session.add(review)


def seal_review_evidence(session: Session, review: IdentityReview) -> None:
    """Seal a new review after this transaction finishes syncing identities/assets."""
    snapshot = dict(review.candidate_snapshot or {})
    candidates = []
    for entry in snapshot.get("candidates", []):
        state = (_item_snapshot(session, entry["library_item_id"]) if entry["library_item_id"]
                 else _film_snapshot(session, entry["film_id"]))
        candidates.append({**entry, "state_hash": canonical_json_hash(state)})
    snapshot["candidates"] = candidates
    review.candidate_snapshot = snapshot
    review.review_key = canonical_json_hash({"item": review.library_item_id, "reason": review.reason_code,
        "incoming": snapshot.get("incoming_identities", {}), "candidates": candidates})
    seal_source_evidence(session, review)


def capture_candidates(session: Session, *, item_id: str, incoming: dict[str, str],
                       file_observation: FileIdentityObservation | None,
                       candidate_item_ids: list[str] | None = None) -> dict[str, Any]:
    """Store bounded IDs and state hashes; never paths, source documents or notes."""
    incoming = safe_identities(incoming)
    film_ids: set[str] = set()
    for provider, external_id in incoming.items():
        film_ids.update(session.exec(select(ExternalIdentity.entity_id)
            .where(ExternalIdentity.provider == provider)
            .where(ExternalIdentity.external_id == external_id)
            .where(ExternalIdentity.identity_status == "active")).all())
    item_ids = {value for value in candidate_item_ids or [] if validate_resource_id(value, "lib")}
    file_matches_truncated = False
    if file_observation:
        matches = session.exec(select(MediaAsset.library_item_id)
            .where(MediaAsset.asset_kind == "video")
            .where(MediaAsset.library_item_id.is_not(None))
            .where(or_(MediaAsset.platform_file_id == file_observation.platform_file_id,
                       MediaAsset.content_fingerprint == file_observation.content_fingerprint))
            .distinct().order_by(MediaAsset.library_item_id).limit(MAX_CANDIDATES + 1)).all()
        item_ids.update(matches)
        file_matches_truncated = len(matches) > MAX_CANDIDATES
    item_ids.discard(item_id)
    entries = []
    for candidate_id in sorted(item_ids)[:MAX_CANDIDATES]:
        state = _item_snapshot(session, candidate_id)
        if state:
            entries.append({"library_item_id": candidate_id, "film_id": state["film_id"],
                            "state_hash": canonical_json_hash(state)})
    for film_id in sorted(film_ids - {entry["film_id"] for entry in entries}):
        if validate_resource_id(film_id, "film") and (state := _film_snapshot(session, film_id)):
            entries.append({"library_item_id": None, "film_id": film_id,
                            "state_hash": canonical_json_hash(state)})
    return {"version": 1, "incoming_identities": incoming, "candidates": entries[:MAX_CANDIDATES],
            "truncated": file_matches_truncated or len(item_ids) > MAX_CANDIDATES or len(entries) > MAX_CANDIDATES}


class IdentityReviewReader:
    def page(self, session: Session, *, status: str = "open", limit: int = 40,
             offset: int = 0) -> dict[str, Any]:
        statement = select(IdentityReview)
        count = select(func.count()).select_from(IdentityReview)
        if status != "all":
            statement = statement.where(IdentityReview.status == status)
            count = count.where(IdentityReview.status == status)
        total = session.exec(count).one()
        rows = session.exec(statement.order_by(IdentityReview.created_at, IdentityReview.id)
                            .offset(offset).limit(limit)).all()
        return {"items": [self._summary(session, row) for row in rows], "total": total,
                "limit": limit, "offset": offset}

    def detail(self, session: Session, review_id: str) -> dict[str, Any] | None:
        row = session.get(IdentityReview, review_id)
        if row is None:
            return None
        snapshot = row.candidate_snapshot or {}
        has_evidence = snapshot.get("version") == 1
        candidates = []
        for entry in (snapshot.get("candidates") or [])[:MAX_CANDIDATES] if has_evidence else []:
            item_id, film_id = entry.get("library_item_id"), entry.get("film_id")
            if not validate_resource_id(film_id, "film") or (item_id and not validate_resource_id(item_id, "lib")):
                continue
            current = _item_snapshot(session, item_id) if item_id else _film_snapshot(session, film_id)
            candidates.append({"film": self._film(session, film_id), "library_item": self._item(session, item_id),
                "film_id": film_id, "library_item_id": item_id,
                "evidence_status": "unavailable" if current is None else (
                    "current" if canonical_json_hash(current) == entry.get("state_hash") else "changed")})
        result = {**self._summary(session, row), "candidates": candidates,
                  "incoming_identities": safe_identities(snapshot.get("incoming_identities") or {}) if has_evidence else {},
                  "evidence_available": has_evidence,
                  "candidates_truncated": bool(snapshot.get("truncated")) if has_evidence else False,
                  "actions": []}
        current_source = _item_snapshot(session, row.library_item_id) if row.library_item_id else None
        result["source_evidence_current"] = bool(current_source and has_evidence
            and canonical_json_hash(current_source) == snapshot.get("source_hash"))
        blocked = None
        if row.status != "open":
            blocked = "already_decided"
        elif not has_evidence or not snapshot.get("source_hash"):
            blocked = "evidence_missing"
        elif result["candidates_truncated"]:
            blocked = "evidence_incomplete"
        elif not result["source_evidence_current"] or any(c["evidence_status"] != "current" for c in candidates):
            blocked = "stale_review"
        elif row.reason_code not in REASONS or row.reason_code in {"identity_conflict", "relink_identity_conflict"}:
            blocked = "identity_conflict_read_only"
        elif not result["film"] or result["film"]["lifecycle"] != "active" or not result["library_item"] or result["library_item"]["availability"] != "available":
            blocked = "source_unavailable"
        else:
            result["actions"] = ["keep_separate"]
            if any(c["library_item"] and c["film_id"] == row.film_id
                   and c["library_item"]["availability"] in {"available", "missing"} for c in candidates):
                result["actions"].append("reconnect")
        result["blocked_code"] = blocked
        result["revision"] = canonical_json_hash(result)
        return result

    def _summary(self, session: Session, row: IdentityReview) -> dict[str, Any]:
        return {"id": row.id, "reason_code": row.reason_code if row.reason_code in REASONS else "unknown",
                "status": row.status, "created_at": row.created_at, "resolved_at": row.resolved_at,
                "film": self._film(session, row.film_id), "library_item": self._item(session, row.library_item_id)}

    @staticmethod
    def _item(session: Session, item_id: str | None) -> dict[str, Any] | None:
        item = session.get(LibraryItem, item_id) if item_id else None
        if item is None:
            return None
        return {"id": item.id, "film_id": item.film_id, "display_name": item.display_name,
                "availability": item.availability_status, "resolution_status": item.resolution_status}

    @staticmethod
    def _film(session: Session, film_id: str | None) -> dict[str, Any] | None:
        film = session.get(Film, film_id) if film_id else None
        if film is None:
            return None
        states = session.exec(select(FilmProfileState).where(FilmProfileState.film_id == film.id)).all()
        viewing_count = session.exec(select(func.count()).select_from(Viewing)
            .where(Viewing.film_id == film.id).where(Viewing.deleted_at.is_(None))).one()
        identities = _film_snapshot(session, film.id)["identities"]
        return {"id": film.id, "title": film.canonical_title, "year": film.release_year,
                "lifecycle": film.lifecycle_status, "identities": safe_identities(dict(identities)),
                "personal_data": {"viewings": viewing_count, "has_rating": any(s.rating is not None for s in states),
                                  "has_notes": any(bool(s.notes) for s in states),
                                  "favorite": any(s.favorite for s in states)}}


identity_review_reader = IdentityReviewReader()
