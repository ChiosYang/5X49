from datetime import datetime, timezone
from typing import Optional, List
from sqlmodel import Field, SQLModel, JSON, Column


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Movie(SQLModel, table=True):
    id: str = Field(primary_key=True)
    title: str = Field(index=True)
    title_cn: Optional[str] = None
    year: int = Field(index=True)
    
    # Image paths
    poster_local: Optional[str] = None
    backdrop_local: Optional[str] = None
    poster_thumb_local: Optional[str] = None
    backdrop_thumb_local: Optional[str] = None
    poster_path: Optional[str] = None
    backdrop_path: Optional[str] = None
    
    # Metadata
    tmdb_id: Optional[str] = None
    imdb_id: Optional[str] = None
    overview: Optional[str] = None
    plot: Optional[str] = None  # Sometimes used as overview
    director: Optional[str] = None
    runtime: Optional[int] = None
    countries: Optional[List[str]] = Field(default=None, sa_column=Column(JSON))
    audio_tracks: Optional[List[dict]] = Field(default=None, sa_column=Column(JSON))
    imdb_rating: Optional[float] = None
    external_scores: Optional[List[dict]] = Field(default=None, sa_column=Column(JSON))
    external_scores_updated_at: Optional[str] = None
    external_scores_error: Optional[str] = None
    
    # Complex fields stored as JSON
    # Note: In SQLite, JSON type is stored as Text but can be parsed.
    # We use sa_column=Column(JSON) to hint SQLAlchemy/SQLModel to handle serialization.
    # This requires `json` module import isn't sufficient, it relies on dialect support.
    # For SQLite, it usually works fine with standard Python JSON dicts/lists.
    genres: Optional[List[str]] = Field(default=None, sa_column=Column(JSON))
    actors: Optional[List[dict]] = Field(default=None, sa_column=Column(JSON))
    
    # Analysis Status
    analysis_status: str = Field(default="pending")
    micro_genre: Optional[str] = None
    micro_genre_definition: Optional[str] = None
    analysis_data: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    
    # File info
    folder_name: Optional[str] = None
    video_file: Optional[str] = None
    nfo_source: Optional[str] = None
    media_path: Optional[str] = Field(default=None, index=True)
    folder_path: Optional[str] = None
    file_size: Optional[int] = None
    file_mtime: Optional[float] = None
    video_width: Optional[int] = None
    video_height: Optional[int] = None
    video_codec: Optional[str] = None
    video_bitrate: Optional[int] = None
    video_duration: Optional[float] = None
    video_fps: Optional[float] = None
    video_dynamic_range: Optional[str] = None
    video_bit_depth: Optional[int] = None
    added_at: Optional[str] = Field(default_factory=utc_now_iso)
    last_seen_at: Optional[str] = None
    missing_since: Optional[str] = None
    library_status: str = Field(default="available", index=True)
    metadata_updated_at: Optional[str] = None
    metadata_source: Optional[str] = None
    scrape_status: str = Field(default="pending", index=True)
    scrape_error: Optional[str] = None
    scraped_at: Optional[str] = None
    tmdb_confidence: Optional[float] = None
