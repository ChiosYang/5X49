from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.contracts.structured_metadata import (
    CountryObservation,
    CreditObservation,
    GenreObservation,
    ObservationIssue,
    StructuredMetadataObservation,
    TitleObservation,
)


def tmdb_structured_metadata_observation(
    details: dict[str, Any],
    tmdb_id: int,
    *,
    language: str,
    observed_at: str | None = None,
) -> StructuredMetadataObservation:
    titles: list[TitleObservation] = []
    title = _text(details.get("title")) or _text(details.get("original_title"))
    original_title = _text(details.get("original_title")) or title
    locale = _locale(language)
    original_locale = _locale(details.get("original_language"))
    if title:
        titles.append(TitleObservation(title, "canonical", locale))
        if title != original_title:
            titles.append(TitleObservation(title, "localized", locale))
    if original_title:
        titles.append(TitleObservation(original_title, "original", original_locale))

    countries = tuple(
        CountryObservation(value)
        for item in details.get("production_countries", [])
        if isinstance(item, dict)
        for value in [_text(item.get("iso_3166_1")) or _text(item.get("name"))]
        if value
    )

    credits: list[CreditObservation] = []
    issues: list[ObservationIssue] = []
    for index, item in enumerate(details.get("credits", {}).get("crew", [])):
        if not isinstance(item, dict) or item.get("job") != "Director":
            continue
        credit = _tmdb_credit(item, "Directing", "Director", index)
        if credit is None:
            issues.append(ObservationIssue("credit", "credit_invalid", {"kind": "director", "index": index}))
        else:
            credits.append(credit)
    for index, item in enumerate(details.get("credits", {}).get("cast", [])[:10]):
        if not isinstance(item, dict):
            issues.append(ObservationIssue("credit", "credit_invalid", {"kind": "actor", "index": index}))
            continue
        credit = _tmdb_credit(
            item,
            "Acting",
            "Actor",
            _nonnegative_int(item.get("order"), index),
            character=_text(item.get("character")) or "",
        )
        if credit is None:
            issues.append(ObservationIssue("credit", "credit_invalid", {"kind": "actor", "index": index}))
        else:
            credits.append(credit)

    genres: list[GenreObservation] = []
    for index, item in enumerate(details.get("genres", [])):
        if not isinstance(item, dict):
            issues.append(ObservationIssue("concept", "genre_invalid", {"index": index}))
            continue
        name = _text(item.get("name"))
        provider_id = _positive_int(item.get("id"))
        if not name:
            issues.append(ObservationIssue("concept", "genre_invalid", {"index": index}))
            continue
        genres.append(GenreObservation(value=name, tmdb_id=provider_id, locale=locale))

    return StructuredMetadataObservation(
        origin_kind="tmdb",
        origin_ref=f"tmdb.movie:{int(tmdb_id)}",
        source_instance_id="tmdb.api",
        observed_at=observed_at or datetime.now(timezone.utc).isoformat(),
        titles=tuple(titles),
        countries=countries,
        credits=tuple(credits),
        genres=tuple(genres),
        issues=tuple(issues),
    )


def _tmdb_credit(
    item: dict[str, Any],
    department: str,
    job: str,
    billing_order: int,
    *,
    character: str = "",
) -> CreditObservation | None:
    name = _text(item.get("original_name")) or _text(item.get("name"))
    if not name:
        return None
    provider_id = _positive_int(item.get("id"))
    return CreditObservation(
        name=name,
        department=department,
        job=job,
        character=character,
        billing_order=billing_order,
        provider="tmdb.person" if provider_id is not None else None,
        external_id=str(provider_id) if provider_id is not None else None,
    )


def _locale(value: Any) -> str:
    text = _text(value)
    if not text:
        return "und"
    normalized = text.replace("_", "-")
    if normalized.casefold() in {"zh", "zh-cn", "zh-hans"}:
        return "zh-CN"
    return normalized


def _text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _nonnegative_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= 0 else default


__all__ = ["tmdb_structured_metadata_observation"]
