import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

from app.services.metadata.models import MetadataSearchResult


def parse_title_year(value: str) -> tuple[str, int]:
    stem = Path(value).stem
    match = re.search(r"(19\d{2}|20\d{2})", stem)
    year = int(match.group(1)) if match else 0
    title_part = stem[:match.start()] if match else stem
    title = re.sub(r"[\._\-\[\]\(\){}]+", " ", title_part).strip()
    title = re.sub(r"\s+", " ", title) or stem
    return title, year


def score_candidates(query_title: str, query_year: int, results: list[dict]) -> list[MetadataSearchResult]:
    scored = []
    for result in results:
        release_date = result.get("release_date") or ""
        result_year = int(release_date[:4]) if release_date[:4].isdigit() else 0
        title = result.get("title") or result.get("name") or ""
        original_title = result.get("original_title") or ""
        score = _score_match(query_title, query_year, title, original_title, result_year)
        scored.append(
            MetadataSearchResult(
                tmdb_id=result["id"],
                title=title,
                original_title=original_title,
                year=result_year,
                overview=result.get("overview") or "",
                poster_path=result.get("poster_path"),
                backdrop_path=result.get("backdrop_path"),
                popularity=float(result.get("popularity") or 0),
                score=score,
            )
        )

    scored.sort(key=lambda candidate: (candidate.score, candidate.popularity), reverse=True)
    return scored


def _score_match(
    query_title: str,
    query_year: int,
    title: str,
    original_title: Optional[str],
    result_year: int,
) -> float:
    query_norm = _normalize_title(query_title)
    title_score = max(
        _ratio(query_norm, _normalize_title(title)),
        _ratio(query_norm, _normalize_title(original_title or "")),
    ) * 60

    year_score = 0
    if query_year and result_year:
        diff = abs(query_year - result_year)
        if diff == 0:
            year_score = 25
        elif diff == 1:
            year_score = 15
        elif diff <= 2:
            year_score = 8

    exact_score = 25 if query_norm and query_norm in {
        _normalize_title(title),
        _normalize_title(original_title or ""),
    } else 0

    return round(min(100, title_score + year_score + exact_score), 2)


def _ratio(left: str, right: str) -> float:
    if not left or not right:
        return 0
    return SequenceMatcher(None, left, right).ratio()


def _normalize_title(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()
