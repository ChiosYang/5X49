from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from sqlalchemy import Connection, inspect, text


BACKFILL_RUN_KEY = "legacy_movie_to_canonical.v1"
SOURCE_INSTANCE_ID = "legacy.local"


@dataclass(frozen=True)
class BackfillIssue:
    legacy_movie_id: str
    code: str


@dataclass(frozen=True)
class CanonicalBackfillReport:
    dry_run: bool
    counts: dict[str, int]
    issues: tuple[BackfillIssue, ...]

    @property
    def warning_count(self) -> int:
        return sum(issue.code != "identity_conflict" for issue in self.issues)

    @property
    def conflict_count(self) -> int:
        return sum(issue.code == "identity_conflict" for issue in self.issues)


def backfill_legacy_movies(
    connection: Connection,
    *,
    dry_run: bool = False,
) -> CanonicalBackfillReport:
    counts = {
        "movies_scanned": 0,
        "movies_skipped": 0,
        "films_created": 0,
        "films_reused": 0,
        "external_identities_created": 0,
        "library_items_created": 0,
        "media_assets_created": 0,
        "aliases_created": 0,
        "identity_reviews_created": 0,
    }
    issues: list[BackfillIssue] = []
    if "movie" not in inspect(connection).get_table_names():
        report = CanonicalBackfillReport(dry_run=dry_run, counts=counts, issues=())
        if not dry_run:
            _store_report(connection, report)
        return report

    profile_id = connection.execute(
        text("SELECT id FROM local_profile WHERE profile_key = 'local'")
    ).scalar_one()
    now = str(connection.execute(text("SELECT strftime('%Y-%m-%dT%H:%M:%fZ', 'now')")).scalar_one())
    movies = connection.execute(text("SELECT * FROM movie ORDER BY id")).mappings().all()
    aliases = {
        str(value)
        for value in connection.execute(text("SELECT legacy_movie_id FROM legacy_movie_alias")).scalars()
    }
    identity_rows = connection.execute(
        text(
            "SELECT i.provider, i.external_id, i.entity_id, g.entity_type "
            "FROM external_identity i JOIN graph_entity g ON g.id = i.entity_id "
            "WHERE i.identity_status = 'active'"
        )
    ).mappings()
    identity_map: dict[tuple[str, str], tuple[str, str]] = {
        (str(row["provider"]), str(row["external_id"])): (
            str(row["entity_id"]),
            str(row["entity_type"]),
        )
        for row in identity_rows
    }
    source_keys = {
        (str(row[0]), str(row[1]))
        for row in connection.execute(
            text(
                "SELECT source_instance_id, source_item_key FROM library_item "
                "WHERE availability_status <> 'retired'"
            )
        )
    }
    asset_keys = {
        (
            "library" if row[0] is not None else "film",
            str(row[0] if row[0] is not None else row[1]),
            str(row[2]),
            str(row[3]),
        )
        for row in connection.execute(
            text(
                "SELECT library_item_id, film_id, asset_kind, normalized_locator_hash "
                "FROM media_asset"
            )
        )
    }

    for index, movie in enumerate(movies):
        legacy_id = str(movie["id"])
        counts["movies_scanned"] += 1
        if legacy_id in aliases:
            counts["movies_skipped"] += 1
            continue

        identities = _movie_identities(movie)
        candidate_ids = {
            identity_map[key][0]
            for key in identities
            if key in identity_map and identity_map[key][1] == "film"
        }
        occupied_by_other_type = any(
            key in identity_map and identity_map[key][1] != "film" for key in identities
        )
        conflict = occupied_by_other_type or len(candidate_ids) > 1
        if conflict:
            film_id = _new_id("film", dry_run, legacy_id, index)
            _create_film(connection, movie, film_id, now, dry_run)
            counts["films_created"] += 1
            counts["identity_reviews_created"] += 1
            issues.append(BackfillIssue(legacy_id, "identity_conflict"))
            if not dry_run:
                _create_identity_review(connection, movie, identity_map, now)
        elif candidate_ids:
            film_id = next(iter(candidate_ids))
            counts["films_reused"] += 1
        else:
            film_id = _new_id("film", dry_run, legacy_id, index)
            _create_film(connection, movie, film_id, now, dry_run)
            counts["films_created"] += 1

        if not conflict:
            for provider_key in identities:
                if provider_key in identity_map:
                    continue
                identity_map[provider_key] = (film_id, "film")
                counts["external_identities_created"] += 1
                if not dry_run:
                    _create_external_identity(
                        connection,
                        film_id,
                        provider_key,
                        legacy_id,
                        now,
                    )

        source_item_key = _source_item_key(movie, legacy_id)
        source_key = (SOURCE_INSTANCE_ID, source_item_key)
        if source_key in source_keys:
            source_item_key = f"{source_item_key}#legacy:{legacy_id}"
            source_key = (SOURCE_INSTANCE_ID, source_item_key)
            issues.append(BackfillIssue(legacy_id, "duplicate_source_item_key"))
        source_keys.add(source_key)

        library_item_id = _new_id("lib", dry_run, legacy_id, index)
        availability = _availability_status(movie.get("library_status"))
        resolution = "review_required" if conflict else ("matched" if identities else "unresolved")
        counts["library_items_created"] += 1
        counts["aliases_created"] += 1
        if not dry_run:
            _create_library_item(
                connection,
                movie,
                profile_id,
                film_id,
                library_item_id,
                source_item_key,
                availability,
                resolution,
                now,
            )
            _create_alias(connection, movie, film_id, library_item_id, now)

        for asset in _assets_for_movie(movie, library_item_id, film_id, availability):
            owner_kind = "library" if asset["library_item_id"] else "film"
            owner_id = asset["library_item_id"] or asset["film_id"]
            key = (owner_kind, str(owner_id), asset["asset_kind"], asset["normalized_locator_hash"])
            if key in asset_keys:
                continue
            asset_keys.add(key)
            counts["media_assets_created"] += 1
            if not dry_run:
                _create_asset(connection, asset, now)

    report = CanonicalBackfillReport(
        dry_run=dry_run,
        counts=counts,
        issues=tuple(issues),
    )
    if not dry_run:
        _store_report(connection, report)
    return report


def _movie_identities(movie: Any) -> tuple[tuple[str, str], ...]:
    identities: list[tuple[str, str]] = []
    tmdb_id = _clean_value(movie.get("tmdb_id"))
    imdb_id = _clean_value(movie.get("imdb_id"))
    if tmdb_id:
        identities.append(("tmdb.movie", tmdb_id))
    if imdb_id:
        identities.append(("imdb.title", imdb_id.casefold()))
    return tuple(identities)


def _new_id(prefix: str, dry_run: bool, legacy_id: str, index: int) -> str:
    if dry_run:
        digest = hashlib.sha256(f"{prefix}:{legacy_id}:{index}".encode("utf-8")).hexdigest()[:32]
        return f"{prefix}_{digest}"
    return f"{prefix}_{uuid4().hex}"


def _create_film(
    connection: Connection,
    movie: Any,
    film_id: str,
    now: str,
    dry_run: bool,
) -> None:
    if dry_run:
        return
    connection.execute(
        text(
            "INSERT INTO graph_entity "
            "(id, entity_type, lifecycle_status, created_at, updated_at) "
            "VALUES (:id, 'film', 'active', :now, :now)"
        ),
        {"id": film_id, "now": now},
    )
    release_year = movie.get("year")
    connection.execute(
        text(
            "INSERT INTO film "
            "(id, canonical_title, original_title, release_year, runtime_minutes, overview, "
            "lifecycle_status, created_at, updated_at) VALUES "
            "(:id, :canonical_title, :original_title, :release_year, :runtime, :overview, "
            "'active', :now, :now)"
        ),
        {
            "id": film_id,
            "canonical_title": _clean_value(movie.get("title_cn")) or str(movie["title"]),
            "original_title": str(movie["title"]),
            "release_year": int(release_year) if release_year and int(release_year) > 0 else None,
            "runtime": movie.get("runtime"),
            "overview": movie.get("overview") or movie.get("plot"),
            "now": now,
        },
    )


def _create_external_identity(
    connection: Connection,
    film_id: str,
    identity: tuple[str, str],
    legacy_id: str,
    now: str,
) -> None:
    connection.execute(
        text(
            "INSERT INTO external_identity "
            "(id, entity_id, provider, external_id, identity_status, provenance_kind, "
            "provenance_ref, created_at, updated_at) VALUES "
            "(:id, :film_id, :provider, :external_id, 'active', 'migration', "
            ":legacy_id, :now, :now)"
        ),
        {
            "id": f"identity_{uuid4().hex}",
            "film_id": film_id,
            "provider": identity[0],
            "external_id": identity[1],
            "legacy_id": legacy_id,
            "now": now,
        },
    )


def _create_identity_review(
    connection: Connection,
    movie: Any,
    identity_map: dict[tuple[str, str], tuple[str, str]],
    now: str,
) -> None:
    tmdb_value = _clean_value(movie.get("tmdb_id"))
    imdb_value = _clean_value(movie.get("imdb_id"))
    tmdb = identity_map.get(("tmdb.movie", tmdb_value)) if tmdb_value else None
    imdb = identity_map.get(("imdb.title", imdb_value.casefold())) if imdb_value else None
    connection.execute(
        text(
            "INSERT INTO identity_review "
            "(id, legacy_movie_id, tmdb_film_id, imdb_film_id, reason, status, "
            "created_at, updated_at) VALUES "
            "(:id, :legacy_id, :tmdb_film, :imdb_film, 'identity_conflict', 'open', :now, :now)"
        ),
        {
            "id": f"review_{uuid4().hex}",
            "legacy_id": str(movie["id"]),
            "tmdb_film": tmdb[0] if tmdb and tmdb[1] == "film" else None,
            "imdb_film": imdb[0] if imdb and imdb[1] == "film" else None,
            "now": now,
        },
    )


def _source_item_key(movie: Any, legacy_id: str) -> str:
    raw = (
        _clean_value(movie.get("folder_path"))
        or _clean_value(movie.get("media_path"))
        or _clean_value(movie.get("folder_name"))
        or legacy_id
    )
    normalized = raw.replace("\\", "/").rstrip("/").strip()
    return normalized or legacy_id


def _availability_status(value: Any) -> str:
    normalized = _clean_value(value) or "available"
    if normalized == "reverted":
        return "retired"
    return normalized if normalized in {"available", "missing", "ignored", "retired"} else "available"


def _create_library_item(
    connection: Connection,
    movie: Any,
    profile_id: str,
    film_id: str,
    library_item_id: str,
    source_item_key: str,
    availability: str,
    resolution: str,
    now: str,
) -> None:
    source_type = "local_nfo" if any(
        _clean_value(movie.get(field)) for field in ("nfo_file", "nfo_path", "nfo_source")
    ) else "local_folder"
    connection.execute(
        text(
            "INSERT INTO library_item "
            "(id, profile_id, film_id, source_type, source_instance_id, source_item_key, "
            "display_name, availability_status, resolution_status, added_at, last_seen_at, "
            "missing_since, retired_at, metadata_source, metadata_updated_at, scrape_status, "
            "scrape_error, scraped_at, match_confidence, created_at, updated_at) VALUES "
            "(:id, :profile_id, :film_id, :source_type, :source_instance_id, :source_item_key, "
            ":display_name, :availability, :resolution, :added_at, :last_seen_at, "
            ":missing_since, :retired_at, :metadata_source, :metadata_updated_at, :scrape_status, "
            ":scrape_error, :scraped_at, :match_confidence, :now, :now)"
        ),
        {
            "id": library_item_id,
            "profile_id": profile_id,
            "film_id": film_id,
            "source_type": source_type,
            "source_instance_id": SOURCE_INSTANCE_ID,
            "source_item_key": source_item_key,
            "display_name": movie.get("folder_name") or movie.get("title"),
            "availability": availability,
            "resolution": resolution,
            "added_at": movie.get("added_at"),
            "last_seen_at": movie.get("last_seen_at"),
            "missing_since": movie.get("missing_since"),
            "retired_at": now if availability == "retired" else None,
            "metadata_source": movie.get("metadata_source"),
            "metadata_updated_at": movie.get("metadata_updated_at"),
            "scrape_status": movie.get("scrape_status") or "pending",
            "scrape_error": movie.get("scrape_error"),
            "scraped_at": movie.get("scraped_at"),
            "match_confidence": movie.get("tmdb_confidence"),
            "now": now,
        },
    )
    connection.execute(
        text(
            "INSERT INTO library_item_locator_history "
            "(id, library_item_id, source_instance_id, source_item_key, observed_from, reason) "
            "VALUES (:id, :item_id, :source_instance_id, :source_item_key, :now, 'legacy_backfill')"
        ),
        {
            "id": f"locator_{uuid4().hex}",
            "item_id": library_item_id,
            "source_instance_id": SOURCE_INSTANCE_ID,
            "source_item_key": source_item_key,
            "now": now,
        },
    )


def _create_alias(
    connection: Connection,
    movie: Any,
    film_id: str,
    library_item_id: str,
    now: str,
) -> None:
    connection.execute(
        text(
            "INSERT INTO legacy_movie_alias "
            "(legacy_movie_id, film_id, library_item_id, legacy_library_status, created_at, updated_at) "
            "VALUES (:legacy_id, :film_id, :item_id, :status, :now, :now)"
        ),
        {
            "legacy_id": str(movie["id"]),
            "film_id": film_id,
            "item_id": library_item_id,
            "status": movie.get("library_status"),
            "now": now,
        },
    )


def _assets_for_movie(
    movie: Any,
    library_item_id: str,
    film_id: str,
    item_availability: str,
) -> list[dict[str, Any]]:
    local_availability = "missing" if item_availability == "missing" else (
        "retired" if item_availability == "retired" else "present"
    )
    definitions = [
        ("library", "video", "local_path", movie.get("media_path") or movie.get("video_file")),
        ("library", "nfo", "local_path", movie.get("nfo_path") or movie.get("nfo_file")),
        ("library", "poster", "local_path", movie.get("poster_local")),
        ("library", "backdrop", "local_path", movie.get("backdrop_local")),
        ("library", "thumbnail", "cache_path", movie.get("poster_thumb_local")),
        ("library", "thumbnail", "cache_path", movie.get("backdrop_thumb_local")),
        ("film", "poster", "provider_path", movie.get("poster_path")),
        ("film", "backdrop", "provider_path", movie.get("backdrop_path")),
    ]
    assets: list[dict[str, Any]] = []
    for owner, kind, locator_kind, raw_locator in definitions:
        locator = _clean_value(raw_locator)
        if not locator:
            continue
        normalized_hash = hashlib.sha256(_normalize_locator(locator).encode("utf-8")).hexdigest()
        assets.append({
            "id": f"asset_{uuid4().hex}",
            "library_item_id": library_item_id if owner == "library" else None,
            "film_id": film_id if owner == "film" else None,
            "asset_kind": kind,
            "locator_kind": locator_kind,
            "locator": locator,
            "normalized_locator_hash": normalized_hash,
            "availability_status": local_availability if owner == "library" else "unknown",
            "file_size": movie.get("file_size") if kind == "video" else (
                movie.get("nfo_size") if kind == "nfo" else None
            ),
            "file_mtime": movie.get("file_mtime") if kind == "video" else (
                movie.get("nfo_mtime") if kind == "nfo" else None
            ),
            "content_fingerprint": movie.get("nfo_fingerprint") if kind == "nfo" else None,
            "width": movie.get("video_width") if kind == "video" else None,
            "height": movie.get("video_height") if kind == "video" else None,
            "codec": movie.get("video_codec") if kind == "video" else None,
            "bitrate": movie.get("video_bitrate") if kind == "video" else None,
            "duration_seconds": movie.get("video_duration") if kind == "video" else None,
            "fps": movie.get("video_fps") if kind == "video" else None,
            "dynamic_range": movie.get("video_dynamic_range") if kind == "video" else None,
            "bit_depth": movie.get("video_bit_depth") if kind == "video" else None,
            "stream_metadata": movie.get("audio_tracks") if kind == "video" else None,
            "source": "legacy_movie",
            "last_observed_at": movie.get("last_seen_at"),
            "missing_since": movie.get("missing_since") if owner == "library" else None,
        })
    return assets


def _create_asset(connection: Connection, asset: dict[str, Any], now: str) -> None:
    connection.execute(
        text(
            "INSERT INTO media_asset "
            "(id, library_item_id, film_id, asset_kind, locator_kind, locator, "
            "normalized_locator_hash, availability_status, file_size, file_mtime, "
            "content_fingerprint, width, height, codec, bitrate, duration_seconds, fps, "
            "dynamic_range, bit_depth, stream_metadata, source, last_observed_at, "
            "missing_since, created_at, updated_at) VALUES "
            "(:id, :library_item_id, :film_id, :asset_kind, :locator_kind, :locator, "
            ":normalized_locator_hash, :availability_status, :file_size, :file_mtime, "
            ":content_fingerprint, :width, :height, :codec, :bitrate, :duration_seconds, :fps, "
            ":dynamic_range, :bit_depth, :stream_metadata, :source, :last_observed_at, "
            ":missing_since, :now, :now)"
        ),
        {
            **asset,
            "stream_metadata": json.dumps(asset["stream_metadata"], ensure_ascii=False)
            if asset["stream_metadata"] is not None
            else None,
            "now": now,
        },
    )


def _store_report(connection: Connection, report: CanonicalBackfillReport) -> None:
    now = str(connection.execute(text("SELECT strftime('%Y-%m-%dT%H:%M:%fZ', 'now')")).scalar_one())
    connection.execute(
        text(
            "INSERT INTO canonical_backfill_run "
            "(run_key, status, counts, warning_count, conflict_count, started_at, finished_at) "
            "VALUES (:run_key, 'succeeded', :counts, :warnings, :conflicts, :now, :now) "
            "ON CONFLICT(run_key) DO NOTHING"
        ),
        {
            "run_key": BACKFILL_RUN_KEY,
            "counts": json.dumps(report.counts, sort_keys=True),
            "warnings": report.warning_count,
            "conflicts": report.conflict_count,
            "now": now,
        },
    )


def _normalize_locator(value: str) -> str:
    return value.replace("\\", "/").strip().rstrip("/").casefold()


def _clean_value(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None
