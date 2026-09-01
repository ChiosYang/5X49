from typing import Optional

from sqlmodel import Session, select

from app.canonical_models import Film, FilmProfileState, Viewing
from app.database import engine
from app.models import utc_now_iso
from app.services.canonical_runtime import canonical_runtime_writer
from app.services.event_store import event_store


class FilmProfileStateManager:
    def default_state(self, film_id: str) -> dict:
        return {
            "film_id": film_id,
            "watched": False,
            "manual_watched": False,
            "watched_at": None,
            "rating": None,
            "favorite": False,
            "notes": None,
            "updated_at": None,
        }

    def get(self, film_id: str) -> dict | None:
        with Session(engine) as session:
            if session.get(Film, film_id) is None:
                return None
            return self._view(session, film_id)

    def upsert(
        self,
        film_id: str,
        *,
        watched: Optional[bool] = None,
        watched_at: Optional[str] = None,
        rating: Optional[int] = None,
        favorite: Optional[bool] = None,
        notes: Optional[str] = None,
        fields_set: set[str] | None = None,
    ) -> dict | None:
        fields_set = fields_set or set()
        with Session(engine) as session:
            if session.get(Film, film_id) is None:
                return None
            before = self._view(session, film_id)
            canonical_runtime_writer.sync_user_state(
                session,
                film_id,
                watched=watched,
                watched_at=watched_at,
                rating=rating,
                favorite=favorite,
                notes=notes,
                fields_set=fields_set,
            )
            after = self._view(session, film_id)
            event_store.append_in_session(
                session,
                "FilmProfileStateUpdated",
                "film",
                film_id,
                {
                    "changed_fields": sorted(fields_set),
                    "before": before,
                    "after": after,
                },
                actor_type="user",
            )
            session.commit()
            return after

    def _view(self, session: Session, film_id: str) -> dict:
        profile_id = canonical_runtime_writer.local_profile_id(session)
        state = session.get(FilmProfileState, (profile_id, film_id))
        viewing = session.exec(
            select(Viewing)
            .where(Viewing.profile_id == profile_id)
            .where(Viewing.film_id == film_id)
            .where(Viewing.review_status == "confirmed")
            .where(Viewing.deleted_at.is_(None))
            .order_by(Viewing.watched_at.desc(), Viewing.updated_at.desc(), Viewing.id.desc())
        ).first()
        manual = session.exec(
            select(Viewing)
            .where(Viewing.profile_id == profile_id)
            .where(Viewing.film_id == film_id)
            .where(Viewing.source == "manual")
            .where(Viewing.source_record_id == film_id)
            .where(Viewing.review_status == "confirmed")
            .where(Viewing.deleted_at.is_(None))
        ).first()
        updated_values = [
            value
            for value in (state.updated_at if state else None, viewing.updated_at if viewing else None)
            if value
        ]
        return {
            "film_id": film_id,
            "watched": viewing is not None,
            "manual_watched": manual is not None,
            "watched_at": viewing.watched_at if viewing else None,
            "rating": state.rating if state else None,
            "favorite": bool(state.favorite) if state else False,
            "notes": state.notes if state else None,
            "updated_at": max(updated_values, default=None),
        }


film_profile_state_manager = FilmProfileStateManager()


__all__ = ["FilmProfileStateManager", "film_profile_state_manager"]
