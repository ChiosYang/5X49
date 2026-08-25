from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.contracts.structured_metadata import normalize_metadata_text


VOCABULARY_VERSION = "structured-metadata-vocab:v1"
GENRE_VOCABULARY_VERSION = "tmdb-movie-genres:v1"
COUNTRY_VOCABULARY_VERSION = "iso-3166-1:v1"
VOCABULARY_PATH = Path(__file__).with_name("structured_metadata_vocab_v1.json")
VOCABULARY_SHA256 = hashlib.sha256(VOCABULARY_PATH.read_bytes()).hexdigest()


@dataclass(frozen=True)
class GenreDefinition:
    tmdb_id: int
    canonical_key: str
    canonical_name: str
    aliases: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class StructuredMetadataVocabulary:
    version: str
    genres: tuple[GenreDefinition, ...]
    genre_by_id: dict[int, GenreDefinition]
    genre_aliases: dict[str, GenreDefinition]
    country_codes: frozenset[str]
    country_aliases: dict[str, str]

    def resolve_genre(self, value: str | int | None) -> GenreDefinition | None:
        if value is None:
            return None
        if isinstance(value, int) or (isinstance(value, str) and value.strip().isdigit()):
            return self.genre_by_id.get(int(value))
        return self.genre_aliases.get(normalize_metadata_text(str(value)))

    def resolve_country(self, value: str | None) -> str | None:
        if value is None:
            return None
        candidate = value.strip()
        if len(candidate) == 2 and candidate.upper() in self.country_codes:
            return candidate.upper()
        return self.country_aliases.get(normalize_metadata_text(candidate))


def load_structured_metadata_vocabulary() -> StructuredMetadataVocabulary:
    payload = json.loads(VOCABULARY_PATH.read_text(encoding="utf-8"))
    if payload.get("version") != VOCABULARY_VERSION:
        raise ValueError("structured metadata vocabulary version does not match")

    genres: list[GenreDefinition] = []
    genre_by_id: dict[int, GenreDefinition] = {}
    genre_aliases: dict[str, GenreDefinition] = {}
    for item in payload.get("genres", []):
        tmdb_id = int(item["tmdb_id"])
        definition = GenreDefinition(
            tmdb_id=tmdb_id,
            canonical_key=f"tmdb.movie.genre:{tmdb_id}",
            canonical_name=_required_text(item.get("canonical_name"), "genre canonical name"),
            aliases=tuple(
                (str(locale), _required_text(alias, "genre alias"))
                for locale, values in dict(item.get("aliases") or {}).items()
                for alias in values
            ),
        )
        if tmdb_id in genre_by_id:
            raise ValueError(f"duplicate genre id: {tmdb_id}")
        genre_by_id[tmdb_id] = definition
        genres.append(definition)
        for _locale, alias in definition.aliases:
            normalized = normalize_metadata_text(alias)
            existing = genre_aliases.get(normalized)
            if existing is not None and existing.tmdb_id != tmdb_id:
                raise ValueError("genre vocabulary contains an ambiguous alias")
            genre_aliases[normalized] = definition

    expected_ids = {
        12, 14, 16, 18, 27, 28, 35, 36, 37, 53,
        80, 99, 878, 9648, 10402, 10749, 10751, 10752, 10770,
    }
    if set(genre_by_id) != expected_ids:
        raise ValueError("genre vocabulary must contain the 19 TMDB movie genres")

    countries = dict(payload.get("countries") or {})
    country_codes = frozenset(str(code).upper() for code in countries)
    country_aliases: dict[str, str] = {}
    for code, names in countries.items():
        normalized_code = str(code).upper()
        if len(normalized_code) != 2 or not normalized_code.isalpha():
            raise ValueError("country vocabulary contains an invalid alpha-2 code")
        _add_country_alias(country_aliases, normalized_code, normalized_code)
        for name in dict(names or {}).values():
            _add_country_alias(country_aliases, str(name), normalized_code)
    for alias, code in dict(payload.get("country_aliases") or {}).items():
        normalized_code = str(code).upper()
        if normalized_code not in country_codes:
            raise ValueError("country alias targets an unknown alpha-2 code")
        _add_country_alias(country_aliases, str(alias), normalized_code)

    if len(country_codes) != 249:
        raise ValueError("country vocabulary must contain all 249 ISO alpha-2 assignments")
    return StructuredMetadataVocabulary(
        version=VOCABULARY_VERSION,
        genres=tuple(sorted(genres, key=lambda item: item.tmdb_id)),
        genre_by_id=genre_by_id,
        genre_aliases=genre_aliases,
        country_codes=country_codes,
        country_aliases=country_aliases,
    )


def _add_country_alias(target: dict[str, str], alias: str, code: str) -> None:
    normalized = normalize_metadata_text(alias)
    if not normalized:
        return
    existing = target.get(normalized)
    if existing is not None and existing != code:
        raise ValueError("country vocabulary contains an ambiguous alias")
    target[normalized] = code


def _required_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must not be empty")
    return value.strip()


STRUCTURED_METADATA_VOCABULARY = load_structured_metadata_vocabulary()


__all__ = [
    "COUNTRY_VOCABULARY_VERSION",
    "GENRE_VOCABULARY_VERSION",
    "GenreDefinition",
    "STRUCTURED_METADATA_VOCABULARY",
    "StructuredMetadataVocabulary",
    "VOCABULARY_VERSION",
    "VOCABULARY_SHA256",
    "load_structured_metadata_vocabulary",
]
