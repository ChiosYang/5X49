from typing import Optional

from sqlmodel import Session, select

from app.database import engine
from app.models import Movie, MovieUserState, utc_now_iso


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
        with Session(engine) as session:
            state = session.get(MovieUserState, movie_id)
            return state.model_dump() if state else self.default_state(movie_id)

    def list_all(self) -> list[dict]:
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
