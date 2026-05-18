import csv
import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional


TSPDT_DATASET_PATH = (
    Path(__file__).resolve().parents[4]
    / "dataset"
    / "TSPDT - 1,000 Greatest Films (Table).csv"
)


@dataclass(frozen=True)
class TSPDTEntry:
    rank: int
    previous_rank: Optional[int]
    title: str
    normalized_title: str
    director: str
    normalized_director: str
    year: int
    country: str
    runtime: Optional[int]


@dataclass(frozen=True)
class TSPDTMatch:
    entry: TSPDTEntry
    confidence: float
    matched_by: str


class TSPDTDataset:
    source = "tspdt"
    label = "TSPDT"
    list_name = "1,000 Greatest Films"
    edition = "2026"

    def __init__(self, dataset_path: Path = TSPDT_DATASET_PATH):
        self.dataset_path = dataset_path
        self._entries: Optional[list[TSPDTEntry]] = None

    def entries(self) -> list[TSPDTEntry]:
        if self._entries is None:
            self._entries = self._load_entries()
        return self._entries

    def match_movie(self, movie: dict, min_confidence: float = 0.9) -> Optional[TSPDTMatch]:
        best: Optional[TSPDTMatch] = None
        titles = self._movie_titles(movie)
        if not titles:
            return None

        movie_year = self._safe_int(movie.get("year"))
        movie_director = normalize_text(normalize_director(movie.get("director") or ""))

        for entry in self.entries():
            match = self._score_entry(entry, titles, movie_year, movie_director)
            if not match:
                continue
            if not best or match.confidence > best.confidence:
                best = match

        if best and best.confidence >= min_confidence:
            return best
        return None

    def _load_entries(self) -> list[TSPDTEntry]:
        if not self.dataset_path.exists():
            raise FileNotFoundError(f"TSPDT dataset not found: {self.dataset_path}")

        entries: list[TSPDTEntry] = []
        with self.dataset_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                title = (row.get("Title") or "").strip()
                rank = self._safe_int(row.get("Pos"))
                year = self._safe_int(row.get("Year"))
                if not title or not rank or not year:
                    continue

                director = normalize_director(row.get("Director") or "")
                entries.append(
                    TSPDTEntry(
                        rank=rank,
                        previous_rank=self._safe_int(row.get("2025")),
                        title=restore_trailing_article(title),
                        normalized_title=normalize_title(title),
                        director=director,
                        normalized_director=normalize_text(director),
                        year=year,
                        country=(row.get("Country") or "").strip(),
                        runtime=self._safe_int(row.get("Mins")),
                    )
                )
        return entries

    def _movie_titles(self, movie: dict) -> set[str]:
        values = [movie.get("title"), movie.get("title_cn")]
        return {normalize_title(value) for value in values if value and normalize_title(value)}

    def _score_entry(
        self,
        entry: TSPDTEntry,
        movie_titles: set[str],
        movie_year: Optional[int],
        movie_director: str,
    ) -> Optional[TSPDTMatch]:
        title_exact = entry.normalized_title in movie_titles
        title_ratio = max(
            (SequenceMatcher(None, entry.normalized_title, title).ratio() for title in movie_titles),
            default=0,
        )
        year_delta = abs(entry.year - movie_year) if movie_year else None
        director_matches = bool(
            movie_director
            and entry.normalized_director
            and (
                entry.normalized_director == movie_director
                or entry.normalized_director in movie_director
                or movie_director in entry.normalized_director
            )
        )

        confidence = 0.0
        matched_by = ""
        if title_exact and year_delta == 0:
            confidence = 0.95
            matched_by = "title_year"
        elif title_exact and year_delta == 1:
            confidence = 0.88
            matched_by = "title_near_year"
        elif title_ratio >= 0.94 and year_delta == 0:
            confidence = 0.86
            matched_by = "fuzzy_title_year"
        elif title_exact and year_delta is None:
            confidence = 0.82
            matched_by = "title"

        if not confidence:
            return None
        if director_matches:
            confidence = min(confidence + 0.04, 0.99)
            matched_by = f"{matched_by}_director"

        return TSPDTMatch(entry=entry, confidence=round(confidence, 3), matched_by=matched_by)

    def _safe_int(self, value) -> Optional[int]:
        try:
            return int(str(value).strip())
        except (TypeError, ValueError):
            return None


def restore_trailing_article(title: str) -> str:
    match = re.match(r"^(?P<title>.+), (?P<article>The|A|An)$", title.strip(), re.IGNORECASE)
    if not match:
        return title.strip()
    return f"{match.group('article')} {match.group('title')}"


def normalize_title(value: str) -> str:
    return normalize_text(restore_trailing_article(value))


def normalize_director(value: str) -> str:
    value = value.strip()
    if "," not in value:
        return re.sub(r"\s+", " ", value)

    directors = []
    for part in re.split(r"\s*&\s*", value):
        if "," not in part:
            directors.append(part.strip())
            continue
        last, first = [segment.strip() for segment in part.split(",", 1)]
        directors.append(f"{first} {last}".strip())
    return " & ".join(directors)


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "").casefold()
    value = value.replace("&", " and ")
    value = re.sub(r"[^\w\s]", " ", value, flags=re.UNICODE)
    value = re.sub(r"\s+", " ", value).strip()
    return value
