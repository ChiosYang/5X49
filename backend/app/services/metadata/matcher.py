import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

from app.services.metadata.models import MetadataSearchResult

RELEASE_TERMS = {
    "aac",
    "ac3",
    "atmos",
    "av1",
    "avc",
    "bdrip",
    "bluray",
    "dts",
    "dvdrip",
    "hdr",
    "hdr10",
    "hevc",
    "hdtv",
    "proper",
    "remaster",
    "remastered",
    "remux",
    "repack",
    "truehd",
    "uhd",
    "web",
    "webdl",
    "webrip",
    "x264",
    "x265",
}

EDITION_PHRASES = (
    "director s cut",
    "directors cut",
    "extended cut",
    "extended edition",
    "final cut",
    "theatrical cut",
    "unrated cut",
)

EDITION_TERMS = {
    "cut",
    "director",
    "directors",
    "edition",
    "extended",
    "final",
    "theatrical",
    "unrated",
}

QUALITY_PATTERN = re.compile(r"^(?:[0-9]{3,4}p|[248]k|h\.?26[45]|10bit|8bit)$", re.IGNORECASE)
YEAR_PATTERN = re.compile(r"(18[7-9]\d|19\d{2}|20\d{2})")


def parse_title_year(value: str) -> tuple[str, int]:
    stem = _strip_release_group(Path(value).stem)
    match = YEAR_PATTERN.search(stem)
    year = int(match.group(1)) if match else 0
    title_part = stem[:match.start()] if match else stem
    title = _clean_title_text(title_part) or _clean_title_text(stem) or stem
    return title, year


def generate_search_queries(title: str) -> list[str]:
    cleaned = _clean_title_text(title)
    queries = [cleaned] if cleaned else []

    without_subtitle = _remove_subtitle(cleaned)
    if without_subtitle and without_subtitle != cleaned:
        queries.append(without_subtitle)

    latin_title = _latin_title(cleaned)
    if latin_title and latin_title != cleaned:
        queries.append(latin_title)

    cjk_title = _cjk_title(cleaned)
    if cjk_title and cjk_title != cleaned:
        queries.append(cjk_title)

    return _unique_nonempty(queries)


def score_candidates(query_title: str, query_year: int, results: list[dict]) -> list[MetadataSearchResult]:
    scored = []
    cleaned_query = _clean_title_text(query_title)
    for result in results:
        release_date = result.get("release_date") or ""
        result_year = int(release_date[:4]) if release_date[:4].isdigit() else 0
        title = result.get("title") or result.get("name") or ""
        original_title = result.get("original_title") or ""
        score = _score_match(cleaned_query, query_year, title, original_title, result_year)
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
    title_norm = _normalize_title(title)
    original_norm = _normalize_title(original_title or "")
    title_ratio = max(_ratio(query_norm, title_norm), _ratio(query_norm, original_norm))
    title_score = title_ratio * 50

    year_score = 0
    if query_year and result_year:
        diff = abs(query_year - result_year)
        if diff == 0:
            year_score = 30
        elif diff == 1:
            year_score = 18
        elif diff <= 2:
            year_score = 8

    exact_score = 15 if query_norm and query_norm in {title_norm, original_norm} else 0
    contains_score = 0
    if query_norm and query_norm not in {title_norm, original_norm}:
        if query_norm in {title_norm[:len(query_norm)], original_norm[:len(query_norm)]}:
            contains_score = 5

    return round(min(100, title_score + year_score + exact_score + contains_score), 2)


def _ratio(left: str, right: str) -> float:
    if not left or not right:
        return 0
    return SequenceMatcher(None, left, right).ratio()


def _normalize_title(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _clean_title_text(value: str) -> str:
    value = _strip_release_group(value)
    value = re.sub(r"['’]", " ", value)
    value = re.sub(r"[\._\-\[\]\(\){}:;,+]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    value = _remove_edition_phrases(value)
    tokens = [
        token
        for token in value.split()
        if not _is_release_token(token)
    ]
    return re.sub(r"\s+", " ", " ".join(tokens)).strip()


def _strip_release_group(value: str) -> str:
    if "-" not in value:
        return value.strip()

    left, group = value.rsplit("-", 1)
    group = group.strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{1,24}", group):
        return value.strip()
    if not _has_release_clue(left):
        return value.strip()
    return left.strip()


def _has_release_clue(value: str) -> bool:
    if YEAR_PATTERN.search(value):
        return True

    tokens = re.split(r"[\s._\-\[\]\(\){}:;,+]+", value)
    for token in tokens:
        normalized = _normalize_title(token)
        if normalized in RELEASE_TERMS or bool(QUALITY_PATTERN.match(normalized)):
            return True
    return False


def _remove_edition_phrases(value: str) -> str:
    for phrase in EDITION_PHRASES:
        pattern = re.compile(rf"\b{re.escape(phrase)}\b", re.IGNORECASE)
        value = pattern.sub(" ", value)
    return re.sub(r"\s+", " ", value).strip()


def _is_release_token(token: str) -> bool:
    normalized = _normalize_title(token)
    return (
        not normalized
        or normalized in RELEASE_TERMS
        or normalized in EDITION_TERMS
        or bool(QUALITY_PATTERN.match(normalized))
    )


def _remove_subtitle(title: str) -> str:
    parts = re.split(r"\s+(?:part|chapter|volume|vol)\s+\d+\b", title, maxsplit=1, flags=re.IGNORECASE)
    if parts and parts[0] != title:
        return parts[0].strip()
    if len(title.split()) > 2:
        return re.split(r"\s+-\s+|\s+:\s+", title, maxsplit=1)[0].strip()
    return title


def _latin_title(title: str) -> str:
    value = re.sub(r"[^A-Za-z0-9\s]+", " ", title)
    return re.sub(r"\s+", " ", value).strip()


def _cjk_title(title: str) -> str:
    value = re.sub(r"[^\u4e00-\u9fff\s]+", " ", title)
    return re.sub(r"\s+", " ", value).strip()


def _unique_nonempty(values: list[str]) -> list[str]:
    unique = []
    seen = set()
    for value in values:
        normalized = _normalize_title(value)
        if normalized and normalized not in seen:
            seen.add(normalized)
            unique.append(value)
    return unique
