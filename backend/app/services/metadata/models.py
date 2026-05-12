from typing import Literal, Optional

from pydantic import BaseModel


class MetadataSearchResult(BaseModel):
    tmdb_id: int
    title: str
    original_title: Optional[str] = None
    year: int = 0
    overview: str = ""
    poster_path: Optional[str] = None
    backdrop_path: Optional[str] = None
    popularity: float = 0
    score: float = 0


class ScrapeOptions(BaseModel):
    mode: Literal["auto", "manual"] = "auto"
    language: Optional[str] = None
    overwrite: bool = False
    write_nfo: bool = True
    download_artwork: bool = True
    tmdb_id: Optional[int] = None


class BatchScrapeOptions(BaseModel):
    scope: Literal["unscraped", "missing_artwork", "all", "selected"] = "unscraped"
    movie_ids: Optional[list[str]] = None
    language: Optional[str] = None
    overwrite: bool = False
    write_nfo: bool = True
    download_artwork: bool = True


class ScrapeResult(BaseModel):
    status: Literal["success", "needs_review", "failed", "skipped"]
    movie_id: str
    message: str
    movie: Optional[dict] = None
    candidates: list[MetadataSearchResult] = []
