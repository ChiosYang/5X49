from __future__ import annotations

import re
from datetime import date, datetime
from uuid import uuid4

from sqlalchemy import case, func
from sqlmodel import Session, select

from app.canonical_models import Film, LibraryItem, Viewing
from app.database import engine
from app.models import utc_now_iso
from app.services.canonical_runtime import canonical_runtime_writer
from app.services.event_store import event_store


_YEAR_PATTERN = re.compile(r"^[0-9]{4}$")
_DATE_PATTERN = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
_TIMESTAMP_PATTERN = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]+)?(?:Z|[+-][0-9]{2}:[0-9]{2})$"
)
_EDITABLE_SOURCES = {"manual", "diary"}


class ViewingNotFound(LookupError):
    pass


class ViewingReadOnly(RuntimeError):
    code = "viewing_read_only"


class ViewingDateError(ValueError):
    pass


def normalize_watched_at(value: str | None) -> tuple[str | None, str]:
    """Normalize the public Viewing date contract without assuming a user timezone."""
    if value is None:
        return None, "unknown"
    if not isinstance(value, str) or not value or value != value.strip():
        raise ViewingDateError("watched_at must be a year, date, or RFC 3339 timestamp")
    if _YEAR_PATTERN.fullmatch(value):
        year = int(value)
        if year < 1:
            raise ViewingDateError("watched_at year is invalid")
        return value, "year"
    if _DATE_PATTERN.fullmatch(value):
        try:
            date.fromisoformat(value)
        except ValueError as exc:
            raise ViewingDateError("watched_at date is invalid") from exc
        return value, "date"

    if not _TIMESTAMP_PATTERN.fullmatch(value):
        raise ViewingDateError("watched_at timestamp must be RFC 3339")
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise ViewingDateError("watched_at timestamp must be RFC 3339") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ViewingDateError("watched_at timestamp must include a timezone")
    return parsed.isoformat(), "timestamp"


class ViewingManager:
    def list_profile(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        film_id: str | None = None,
    ) -> dict:
        with Session(engine) as session:
            profile_id = canonical_runtime_writer.local_profile_id(session)
            statement = self._active_statement(profile_id, film_id).order_by(
                case((Viewing.watched_at.is_(None), 1), else_=0),
                Viewing.watched_at.desc(),
                Viewing.updated_at.desc(),
                Viewing.id.desc(),
            )
            count_statement = (
                select(func.count()).select_from(Viewing)
                .where(Viewing.profile_id == profile_id)
                .where(Viewing.review_status == "confirmed")
                .where(Viewing.deleted_at.is_(None))
            )
            if film_id:
                count_statement = count_statement.where(Viewing.film_id == film_id)
            total = session.exec(count_statement).one()
            rows = session.exec(statement.offset(offset).limit(limit)).all()
            items = [self._timeline_entry(session, profile_id, row) for row in rows]
            next_offset = offset + len(items) if offset + len(items) < total else None
            return {
                "items": items,
                "total": total,
                "limit": limit,
                "offset": offset,
                "next_offset": next_offset,
            }

    def list_film(self, film_id: str) -> list[dict] | None:
        with Session(engine) as session:
            if session.get(Film, film_id) is None:
                return None
            profile_id = canonical_runtime_writer.local_profile_id(session)
            rows = session.exec(
                self._active_statement(profile_id, film_id).order_by(
                    case((Viewing.watched_at.is_(None), 1), else_=0),
                    Viewing.watched_at.desc(),
                    Viewing.updated_at.desc(),
                    Viewing.id.desc(),
                )
            ).all()
            return [self._view(row) for row in rows]

    def create(self, film_id: str, watched_at: str | None) -> dict | None:
        normalized, precision = normalize_watched_at(watched_at)
        with Session(engine) as session:
            if session.get(Film, film_id) is None:
                return None
            profile_id = canonical_runtime_writer.local_profile_id(session)
            now = utc_now_iso()
            viewing_id = f"view_{uuid4().hex}"
            viewing = Viewing(
                id=viewing_id,
                profile_id=profile_id,
                film_id=film_id,
                watched_at=normalized,
                watched_at_precision=precision,
                source="diary",
                source_record_id=viewing_id,
                review_status="confirmed",
                created_at=now,
                updated_at=now,
            )
            session.add(viewing)
            event_store.append_in_session(
                session,
                "ViewingCreated",
                "viewing",
                viewing.id,
                {
                    "film_id": film_id,
                    "source": "diary",
                    "watched_at": normalized,
                    "watched_at_precision": precision,
                },
                actor_type="user",
            )
            session.commit()
            session.refresh(viewing)
            return self._view(viewing)

    def update(self, viewing_id: str, watched_at: str | None) -> dict:
        normalized, precision = normalize_watched_at(watched_at)
        with Session(engine) as session:
            profile_id = canonical_runtime_writer.local_profile_id(session)
            viewing = session.get(Viewing, viewing_id)
            if viewing is None or viewing.profile_id != profile_id or viewing.deleted_at is not None:
                raise ViewingNotFound("Viewing not found")
            self._ensure_editable(viewing)
            before = {
                "watched_at": viewing.watched_at,
                "watched_at_precision": viewing.watched_at_precision,
            }
            after = {"watched_at": normalized, "watched_at_precision": precision}
            if before == after:
                return self._view(viewing)
            viewing.watched_at = normalized
            viewing.watched_at_precision = precision
            viewing.updated_at = utc_now_iso()
            session.add(viewing)
            event_store.append_in_session(
                session,
                "ViewingUpdated",
                "viewing",
                viewing.id,
                {"changed_fields": ["watched_at"], "before": before, "after": after},
                actor_type="user",
            )
            session.commit()
            session.refresh(viewing)
            return self._view(viewing)

    def delete(self, viewing_id: str) -> dict:
        with Session(engine) as session:
            profile_id = canonical_runtime_writer.local_profile_id(session)
            viewing = session.get(Viewing, viewing_id)
            if viewing is None or viewing.profile_id != profile_id:
                raise ViewingNotFound("Viewing not found")
            self._ensure_editable(viewing)
            if viewing.deleted_at is not None:
                return {
                    "status": "deleted",
                    "viewing_id": viewing.id,
                    "film_id": viewing.film_id,
                    "changed": False,
                }
            viewing.deleted_at = utc_now_iso()
            viewing.updated_at = viewing.deleted_at
            session.add(viewing)
            event_store.append_in_session(
                session,
                "ViewingDeleted",
                "viewing",
                viewing.id,
                {
                    "film_id": viewing.film_id,
                    "source": viewing.source,
                    "watched_at": viewing.watched_at,
                    "watched_at_precision": viewing.watched_at_precision,
                },
                actor_type="user",
            )
            session.commit()
            return {
                "status": "deleted",
                "viewing_id": viewing.id,
                "film_id": viewing.film_id,
                "changed": True,
            }

    @staticmethod
    def _active_statement(profile_id: str, film_id: str | None = None):
        statement = (
            select(Viewing)
            .where(Viewing.profile_id == profile_id)
            .where(Viewing.review_status == "confirmed")
            .where(Viewing.deleted_at.is_(None))
        )
        return statement.where(Viewing.film_id == film_id) if film_id else statement

    def _timeline_entry(self, session: Session, profile_id: str, viewing: Viewing) -> dict:
        film = session.get(Film, viewing.film_id)
        in_library = session.exec(
            select(LibraryItem.id)
            .where(LibraryItem.film_id == viewing.film_id)
            .where(LibraryItem.availability_status.notin_(("retired", "ignored")))
        ).first() is not None
        return {
            "viewing": self._view(viewing),
            "film": {
                "id": viewing.film_id,
                "title": film.canonical_title if film else "",
                "year": film.release_year if film else None,
                "in_library": in_library,
            },
            "profile_state": canonical_runtime_writer.derived_profile_state(
                session,
                profile_id,
                viewing.film_id,
            ),
        }

    @staticmethod
    def _view(viewing: Viewing) -> dict:
        return {
            "id": viewing.id,
            "film_id": viewing.film_id,
            "watched_at": viewing.watched_at,
            "watched_at_precision": viewing.watched_at_precision,
            "source": viewing.source,
            "editable": viewing.source in _EDITABLE_SOURCES,
            "created_at": viewing.created_at,
            "updated_at": viewing.updated_at,
        }

    @staticmethod
    def _ensure_editable(viewing: Viewing) -> None:
        if viewing.source not in _EDITABLE_SOURCES:
            raise ViewingReadOnly("Viewing source is read-only")


viewing_manager = ViewingManager()


__all__ = [
    "ViewingDateError",
    "ViewingManager",
    "ViewingNotFound",
    "ViewingReadOnly",
    "normalize_watched_at",
    "viewing_manager",
]
