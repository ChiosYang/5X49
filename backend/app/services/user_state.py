from typing import Optional

from sqlmodel import Session, select

from app.database import engine
from app.models import Movie, MovieUserState, utc_now_iso
from app.services.canonical_runtime import canonical_runtime_writer
from app.services.canonical_shadow import CanonicalShadowReader
from app.services.compatibility_reads import (
    library_read_source,
    log_orphan_fallback,
    log_shadow_report,
)


class MovieUserStateManager:
    def default_state(self, movie_id: str) -> dict:
        return {
            "movie_id": movie_id,
            "watched": False,
            "watched_at": None,
            "rating": None,
            "favorite": False,
            "notes": None,
            "updated_at": None,
        }

    def get(self, movie_id: str) -> dict:
        legacy = self._legacy_get(movie_id)
        source = library_read_source()
        if source == "legacy":
            return legacy
        reader = CanonicalShadowReader(engine)
        canonical = reader.get_user_state(movie_id)
        if source == "shadow":
            log_shadow_report(reader.compare_user_states())
            return legacy
        if canonical is None:
            log_orphan_fallback("user_state", record_id=movie_id)
        return canonical or legacy

    def _legacy_get(self, movie_id: str) -> dict:
        with Session(engine) as session:
            state = session.get(MovieUserState, movie_id)
            return state.model_dump() if state else self.default_state(movie_id)

    def list_all(self) -> list[dict]:
        legacy = self._legacy_list_all()
        source = library_read_source()
        if source == "legacy":
            return legacy
        reader = CanonicalShadowReader(engine)
        if source == "shadow":
            log_shadow_report(reader.compare_user_states())
            return legacy
        canonical = reader.list_user_states()
        canonical_ids = {state["movie_id"] for state in canonical}
        orphans = [
            state
            for state in legacy
            if state["movie_id"] not in canonical_ids
            and (
                state.get("watched")
                or state.get("favorite")
                or state.get("rating") is not None
                or bool(state.get("notes"))
                or state.get("watched_at") is not None
            )
        ]
        if orphans:
            log_orphan_fallback("user_state", count=len(orphans))
            canonical.extend(orphans)
        return sorted(canonical, key=lambda state: state.get("updated_at") or "", reverse=True)

    def _legacy_list_all(self) -> list[dict]:
        with Session(engine) as session:
            states = session.exec(select(MovieUserState).order_by(MovieUserState.updated_at.desc())).all()
            return [state.model_dump() for state in states]

    def upsert(
        self,
        movie_id: str,
        *,
        watched: Optional[bool] = None,
        watched_at: Optional[str] = None,
        rating: Optional[int] = None,
        favorite: Optional[bool] = None,
        notes: Optional[str] = None,
        fields_set: set[str] | None = None,
    ) -> dict:
        fields_set = fields_set or set()
        now = utc_now_iso()

        with Session(engine) as session:
            canonical = canonical_runtime_writer.sync_user_state(
                session,
                movie_id,
                watched=watched,
                watched_at=watched_at,
                rating=rating,
                favorite=favorite,
                notes=notes,
                fields_set=fields_set,
            )
            if canonical is not None:
                session.commit()
                return canonical
            state = session.get(MovieUserState, movie_id)
            if not state:
                state = MovieUserState(movie_id=movie_id)

            if "watched" in fields_set and watched is not None:
                state.watched = watched
            if "watched_at" in fields_set:
                state.watched_at = watched_at
            if "rating" in fields_set:
                state.rating = rating
            if "favorite" in fields_set and favorite is not None:
                state.favorite = favorite
            if "notes" in fields_set:
                state.notes = notes

            state.updated_at = now
            session.add(state)
            session.commit()
            session.refresh(state)
            return state.model_dump()

    def watch_history(self) -> list[dict]:
        source = library_read_source()
        if source == "canonical":
            reader = CanonicalShadowReader(engine)
            canonical = reader.watch_history()
            legacy_orphans = [
                entry
                for entry in self._legacy_watch_history()
                if reader.get_movie(entry["movie"]["id"]) is None
            ]
            if legacy_orphans:
                log_orphan_fallback("watch_history", count=len(legacy_orphans))
                canonical.extend(legacy_orphans)
                canonical.sort(
                    key=lambda entry: (
                        entry["user_state"].get("watched_at") or "",
                        entry["user_state"].get("updated_at") or "",
                    ),
                    reverse=True,
                )
            return canonical
        legacy = self._legacy_watch_history()
        if source == "shadow":
            canonical = CanonicalShadowReader(engine).watch_history()
            # The detailed field comparison is covered by movie and state shadow reports.
            if len(legacy) != len(canonical):
                import logging

                logging.getLogger("compatibility_reads").info(
                    "Canonical shadow comparison scope=watch_history legacy_count=%s canonical_count=%s",
                    len(legacy),
                    len(canonical),
                )
        return legacy

    def _legacy_watch_history(self) -> list[dict]:
        with Session(engine) as session:
            statement = (
                select(MovieUserState, Movie)
                .join(Movie, Movie.id == MovieUserState.movie_id)
                .where(MovieUserState.watched == True)  # noqa: E712
            )
            rows = session.exec(statement).all()

        entries = [
            {
                "movie": movie.model_dump(),
                "user_state": state.model_dump(),
            }
            for state, movie in rows
        ]
        return sorted(
            entries,
            key=lambda entry: (
                entry["user_state"].get("watched_at") or "",
                entry["user_state"].get("updated_at") or "",
            ),
            reverse=True,
        )


movie_user_state_manager = MovieUserStateManager()
