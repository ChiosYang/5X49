from typing import Optional

from sqlmodel import Session

from app.models import EventRecord, Movie


class MovieProjector:
    """Synchronous Movie projection for low-risk event-sourced changes."""

    def apply(self, event: EventRecord, session: Session) -> Optional[dict]:
        if event.aggregate_type != "movie" or not event.aggregate_id:
            return None

        movie = session.get(Movie, event.aggregate_id)
        if not movie:
            return None

        handlers = {
            "MovieIgnored": self._apply_ignored,
            "MovieMarkedMissing": self._apply_marked_missing,
            "MovieRestored": self._apply_restored,
            "AnalysisStarted": self._apply_analysis_started,
            "AnalysisCompleted": self._apply_analysis_completed,
            "AnalysisFailed": self._apply_analysis_failed,
        }
        handler = handlers.get(event.type)
        if not handler:
            return None

        handler(movie, event.payload or {})
        session.add(movie)
        session.flush()
        return movie.model_dump()

    def _apply_ignored(self, movie: Movie, payload: dict):
        movie.library_status = "ignored"
        movie.missing_since = None

    def _apply_marked_missing(self, movie: Movie, payload: dict):
        if movie.library_status == "ignored":
            return
        movie.library_status = "missing"
        movie.missing_since = payload.get("missing_since")

    def _apply_restored(self, movie: Movie, payload: dict):
        if movie.library_status == "ignored":
            return
        movie.library_status = "available"
        movie.missing_since = None

    def _apply_analysis_started(self, movie: Movie, payload: dict):
        movie.analysis_status = "processing"

    def _apply_analysis_completed(self, movie: Movie, payload: dict):
        movie.analysis_data = payload.get("analysis_data")
        movie.micro_genre = payload.get("micro_genre")
        movie.micro_genre_definition = payload.get("micro_genre_definition")
        movie.analysis_status = "completed"

    def _apply_analysis_failed(self, movie: Movie, payload: dict):
        movie.analysis_status = "failed"


movie_projector = MovieProjector()
