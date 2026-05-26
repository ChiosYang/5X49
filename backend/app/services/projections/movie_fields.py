from app.models import Movie


MOVIE_DISCOVERED_FIELDS = (
    "title",
    "title_cn",
    "year",
    "media_path",
    "folder_path",
    "folder_name",
    "video_file",
    "file_size",
    "file_mtime",
    "last_seen_at",
    "library_status",
    "metadata_source",
    "scrape_status",
    "tmdb_id",
    "imdb_id",
    "video_width",
    "video_height",
    "video_codec",
    "video_bitrate",
    "video_duration",
    "video_fps",
    "video_dynamic_range",
    "video_bit_depth",
    "nfo_source",
    "nfo_file",
    "nfo_path",
    "nfo_size",
    "nfo_mtime",
    "nfo_fingerprint",
)

FILE_OBSERVED_FIELDS = (
    "media_path",
    "folder_path",
    "folder_name",
    "video_file",
    "file_size",
    "file_mtime",
    "last_seen_at",
    "video_width",
    "video_height",
    "video_codec",
    "video_bitrate",
    "video_duration",
    "video_fps",
    "video_dynamic_range",
    "video_bit_depth",
    "nfo_source",
    "nfo_file",
    "nfo_path",
    "nfo_size",
    "nfo_mtime",
    "nfo_fingerprint",
)

NFO_METADATA_FIELDS = (
    "title",
    "title_cn",
    "year",
    "tmdb_id",
    "imdb_id",
    "plot",
    "runtime",
    "countries",
    "audio_tracks",
    "genres",
    "director",
    "imdb_rating",
    "actors",
    "poster_local",
    "backdrop_local",
    "poster_thumb_local",
    "backdrop_thumb_local",
    "poster_path",
    "backdrop_path",
    "nfo_source",
    "metadata_source",
    "scrape_status",
)

NFO_SIGNATURE_FIELDS = (
    "nfo_file",
    "nfo_path",
    "nfo_size",
    "nfo_mtime",
    "nfo_fingerprint",
)

METADATA_MATCH_FIELDS = (
    "title",
    "title_cn",
    "year",
    "tmdb_id",
    "imdb_id",
    "overview",
    "plot",
    "runtime",
    "countries",
    "audio_tracks",
    "genres",
    "director",
    "imdb_rating",
    "actors",
    "poster_local",
    "backdrop_local",
    "poster_thumb_local",
    "backdrop_thumb_local",
    "poster_path",
    "backdrop_path",
    "nfo_source",
    "metadata_source",
    "scrape_status",
    "scrape_error",
    "scraped_at",
    "tmdb_confidence",
)

ARTWORK_SELECTION_FIELDS = (
    "poster_local",
    "backdrop_local",
    "poster_thumb_local",
    "backdrop_thumb_local",
    "poster_path",
    "backdrop_path",
    "metadata_updated_at",
)

EXTERNAL_SCORE_FIELDS = (
    "external_scores",
    "external_scores_updated_at",
    "external_scores_error",
)

ANALYSIS_FIELDS = (
    "analysis_status",
    "analysis_data",
    "micro_genre",
    "micro_genre_definition",
)

STATUS_FIELDS = (
    "library_status",
    "missing_since",
)

CORE_COMPARE_FIELDS = tuple(dict.fromkeys((
    "id",
    *MOVIE_DISCOVERED_FIELDS,
    *NFO_METADATA_FIELDS,
    *NFO_SIGNATURE_FIELDS,
    *METADATA_MATCH_FIELDS,
    *ARTWORK_SELECTION_FIELDS,
    *EXTERNAL_SCORE_FIELDS,
    *ANALYSIS_FIELDS,
    *STATUS_FIELDS,
)))

PROJECTABLE_EVENT_TYPES = {
    "MovieDiscovered",
    "MovieFileObserved",
    "MovieMetadataParsedFromNfo",
    "MovieIgnored",
    "MovieMarkedMissing",
    "MovieRestored",
    "MovieStateBackfilled",
    "MetadataMatched",
    "ArtworkSelected",
    "MovieStateRestored",
    "MetadataRestored",
    "ArtworkSelectionRestored",
    "RootVideoOrganizationReverted",
    "AnalysisStarted",
    "AnalysisCompleted",
    "AnalysisFailed",
    "ExternalScoresRefreshed",
}


def event_movie_id(payload: dict, aggregate_id: str | None) -> str | None:
    return payload.get("movie_id") or payload.get("id") or aggregate_id


def values_from_payload(payload: dict, fields: tuple[str, ...]) -> dict:
    values = {}
    current = payload.get("current")
    if isinstance(current, dict):
        values.update({field: current[field] for field in fields if field in current})
    values.update({field: payload[field] for field in fields if field not in values and field in payload})
    return {
        field: value
        for field, value in values.items()
        if field in Movie.model_fields
    }


def apply_values_to_movie(movie: Movie, values: dict):
    for field, value in values.items():
        if field != "id" and field in Movie.model_fields:
            setattr(movie, field, value)
