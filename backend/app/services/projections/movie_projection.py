from typing import Optional

from sqlmodel import Session

from app.models import EventRecord, Movie
from app.services.projections.movie_fields import (
    ARTWORK_SELECTION_FIELDS,
    EXTERNAL_SCORE_FIELDS,
    FILE_OBSERVED_FIELDS,
    METADATA_MATCH_FIELDS,
    MOVIE_DISCOVERED_FIELDS,
    NFO_METADATA_FIELDS,
    NFO_SIGNATURE_FIELDS,
    apply_values_to_movie,
    event_movie_id,
    values_from_payload,
)


class MovieProjector:
    """Synchronous Movie projection for low-risk event-sourced changes."""

    def apply(self, event: EventRecord, session: Session) -> Optional[dict]:
        if event.aggregate_type != "movie":
            return None

        handlers = {
            "MovieDiscovered": self._apply_discovered,
            "MovieFileObserved": self._apply_file_observed,
            "MovieMetadataParsedFromNfo": self._apply_nfo_metadata,
            "MovieIgnored": self._apply_ignored,
            "MovieMarkedMissing": self._apply_marked_missing,
            "MovieRestored": self._apply_restored,
            "MovieStateBackfilled": self._apply_state_backfilled,
            "MetadataMatched": self._apply_metadata_matched,
            "ArtworkSelected": self._apply_artwork_selected,
            "MovieStateRestored": self._apply_restored_fields,
            "MetadataRestored": self._apply_restored_fields,
            "ArtworkSelectionRestored": self._apply_restored_fields,
            "RootVideoOrganizationReverted": self._apply_root_video_organization_reverted,
            "AnalysisStarted": self._apply_analysis_started,
            "AnalysisCompleted": self._apply_analysis_completed,
            "AnalysisFailed": self._apply_analysis_failed,
            "ExternalScoresRefreshed": self._apply_external_scores_refreshed,
        }
        handler = handlers.get(event.type)
        if not handler:
            return None

        payload = event.payload or {}
        movie_id = event_movie_id(payload, event.aggregate_id)
        if not movie_id:
            return None

        movie = session.get(Movie, movie_id)
        if not movie:
            if event.type != "MovieDiscovered":
                return None
            movie = self._movie_from_discovered(movie_id, payload)
            if not movie:
                return None

        handler(movie, payload)
        session.add(movie)
        session.flush()
        return movie.model_dump()

    def _movie_from_discovered(self, movie_id: str, payload: dict) -> Optional[Movie]:
        if not payload.get("title") or payload.get("year") is None:
            return None
        movie = Movie(id=movie_id, title=payload["title"], year=payload["year"])
        apply_values_to_movie(movie, values_from_payload(payload, MOVIE_DISCOVERED_FIELDS))
        return movie

    def _apply_discovered(self, movie: Movie, payload: dict):
        apply_values_to_movie(movie, values_from_payload(payload, MOVIE_DISCOVERED_FIELDS))

    def _apply_file_observed(self, movie: Movie, payload: dict):
        apply_values_to_movie(movie, values_from_payload(payload, FILE_OBSERVED_FIELDS))

    def _apply_nfo_metadata(self, movie: Movie, payload: dict):
        fields = (*NFO_METADATA_FIELDS, *NFO_SIGNATURE_FIELDS)
        apply_values_to_movie(movie, values_from_payload(payload, fields))

    def _apply_state_backfilled(self, movie: Movie, payload: dict):
        apply_values_to_movie(movie, values_from_payload(payload, tuple(Movie.model_fields)))

    def _apply_metadata_matched(self, movie: Movie, payload: dict):
        apply_values_to_movie(movie, values_from_payload(payload, METADATA_MATCH_FIELDS))

    def _apply_artwork_selected(self, movie: Movie, payload: dict):
        apply_values_to_movie(movie, values_from_payload(payload, ARTWORK_SELECTION_FIELDS))

    def _apply_external_scores_refreshed(self, movie: Movie, payload: dict):
        apply_values_to_movie(movie, values_from_payload(payload, EXTERNAL_SCORE_FIELDS))

    def _apply_ignored(self, movie: Movie, payload: dict):
        movie.library_status = "ignored"
        movie.missing_since = None

    def _apply_marked_missing(self, movie: Movie, payload: dict):
        if movie.library_status in {"ignored", "reverted"}:
            return
        movie.library_status = "missing"
        movie.missing_since = payload.get("missing_since")

    def _apply_restored(self, movie: Movie, payload: dict):
        if movie.library_status == "ignored":
            return
        movie.library_status = "available"
        movie.missing_since = None

    def _apply_root_video_organization_reverted(self, movie: Movie, payload: dict):
        movie.library_status = "reverted"
        movie.missing_since = None

    def _apply_restored_fields(self, movie: Movie, payload: dict):
        restored_fields = payload.get("restored_fields")
        if not isinstance(restored_fields, list):
            return
        for item in restored_fields:
            if not isinstance(item, dict):
                continue
            field = item.get("field")
            if isinstance(field, str) and field in Movie.model_fields:
                setattr(movie, field, item.get("restored"))

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
