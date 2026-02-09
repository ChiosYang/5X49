from typing import Optional, List
from sqlmodel import Field, SQLModel, JSON, Column

class Movie(SQLModel, table=True):
    id: str = Field(primary_key=True)
    title: str = Field(index=True)
    title_cn: Optional[str] = None
    year: int = Field(index=True)
    
    # Image paths
    poster_local: Optional[str] = None
    backdrop_local: Optional[str] = None
    poster_path: Optional[str] = None
    backdrop_path: Optional[str] = None
    
    # Metadata
    tmdb_id: Optional[str] = None
    imdb_id: Optional[str] = None
    overview: Optional[str] = None
    plot: Optional[str] = None  # Sometimes used as overview
    director: Optional[str] = None
    runtime: Optional[int] = None
    imdb_rating: Optional[float] = None
    
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
