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


class ArtworkImage(BaseModel):
    file_path: str
    url: str
    thumbnail_url: str
    width: int = 0
    height: int = 0
    aspect_ratio: float = 0
    language: Optional[str] = None
    vote_average: float = 0
    vote_count: int = 0


class MovieArtworkOptions(BaseModel):
    movie_id: str
    tmdb_id: int
    posters: list[ArtworkImage] = []
    backdrops: list[ArtworkImage] = []
    current_poster_path: Optional[str] = None
    current_backdrop_path: Optional[str] = None


class ArtworkSelection(BaseModel):
    poster_path: Optional[str] = None
    backdrop_path: Optional[str] = None


class ScrapeOptions(BaseModel):
    mode: Literal["auto", "manual"] = "auto"
    language: Optional[str] = None
    artwork_language: Optional[Literal["metadata", "zh", "en", "none"]] = None
    overwrite: bool = False
    write_nfo: bool = True
    download_artwork: bool = True
    tmdb_id: Optional[int] = None


class BatchScrapeOptions(BaseModel):
    scope: Literal["unscraped", "missing_artwork", "all", "selected"] = "unscraped"
    movie_ids: Optional[list[str]] = None
    language: Optional[str] = None
    artwork_language: Optional[Literal["metadata", "zh", "en", "none"]] = None
    overwrite: bool = False
    write_nfo: bool = True
    download_artwork: bool = True


class RootOrganizeOptions(BaseModel):
    min_confidence: Optional[float] = None
    rename_style: Literal["preserve_stem", "title_year"] = "preserve_stem"
    overwrite: bool = False
    write_nfo: bool = True
    download_artwork: bool = True
    language: Optional[str] = None
    artwork_language: Optional[Literal["metadata", "zh", "en", "none"]] = None


class RootOrganizeConfirmRequest(BaseModel):
    path: str
    tmdb_id: int
    options: Optional[RootOrganizeOptions] = None


class ScrapeResult(BaseModel):
    status: Literal["success", "needs_review", "failed", "skipped"]
    movie_id: str
    message: str
    movie: Optional[dict] = None
    candidates: list[MetadataSearchResult] = []
