"""Generate deterministic, local-only data for 5X49 integration testing.

The generator deliberately writes files only below the requested output
directory.  It does not import the application database or call external
services, so it is safe to use without API keys.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import shutil
import sys
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw


GENERATOR_NAME = "5X49 local test data generator"
SCHEMA_VERSION = 1
DEFAULT_SEED = 549
DEFAULT_COUNT = 200
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parents[1] / "data" / "generated-test-data"
VIDEO_BYTES = b"5X49_TEST_VIDEO_PLACEHOLDER\n"
DATA_PROFILES = ("mixed", "normal")

TITLE_PAIRS = (
    ("The Quiet Signal", "静默信号"),
    ("海边的第七封信", "The Seventh Letter by the Sea"),
    ("Lumiere apres minuit", "午夜之后的光"),
    ("Kosmicheskiy sad", "太空花园"),
    ("Cafe com Chuva", "雨中的咖啡馆"),
    ("Tokyo no yohaku", "東京の余白"),
    ("The Quiet Signal", "静默信号"),
    ("A-B: Director's Cut", "A-B：导演剪辑版"),
    (
        "The Cartographer of Small and Very Distant Stars, or a Field Guide to\n"
        "Maps That Refuse to Stay Folded",
        "拒绝折叠的星图",
    ),
)
GENRES = (
    ("Drama", "Mystery"),
    ("Animation", "Family"),
    ("Sci-Fi", "Adventure"),
    ("Documentary",),
    ("Comedy", "Romance"),
    ("Thriller", "Crime"),
)
COUNTRIES = ("US", "CN", "FR", "JP", "BR", "DE", "GB")
EDGE_SCENARIOS = (
    "missing_nfo",
    "corrupt_xml",
    "multiple_videos",
    "special_path",
    "duplicate_version",
    "no_video",
    "temporary_video_only",
    "root_video",
)


def generate_dataset(
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    *,
    count: int = DEFAULT_COUNT,
    seed: int = DEFAULT_SEED,
    profile: str = "mixed",
    force: bool = False,
) -> dict[str, Any]:
    """Generate a model-compatible JSON fixture and a small media tree."""
    if count < 0:
        raise ValueError("count must be non-negative")
    if profile not in DATA_PROFILES:
        raise ValueError(f"profile must be one of: {', '.join(DATA_PROFILES)}")

    output = _safe_output_path(output_dir)
    if output.exists() and not output.is_dir():
        raise ValueError(f"Output path is not a directory: {output}")

    complete, incomplete, edge = (count, 0, 0) if profile == "normal" else _distribution(count)
    rng = random.Random(seed)
    base_time = datetime(2025, 1, 1, tzinfo=timezone.utc)
    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=str(output.parent)))
    try:
        media_root = staging / "media"
        media_root.mkdir()
        movies: list[dict[str, Any]] = []
        user_states: list[dict[str, Any]] = []
        media_scenarios: list[dict[str, Any]] = []

        for index in range(count):
            category = _category_for(index, complete, incomplete)
            edge_index = index - complete - incomplete
            scenario = EDGE_SCENARIOS[edge_index % len(EDGE_SCENARIOS)] if category == "edge" else "valid_nfo"
            title, title_cn = TITLE_PAIRS[index % len(TITLE_PAIRS)]
            year = 1950 + ((index * 37 + seed) % 76)
            movie_id = (
                f"{100000 + index}_{year}"
                if profile == "normal"
                else f"fixture_{index + 1:04d}"
            )
            folder_name = f"movie-{index + 1:04d}"
            if scenario == "special_path":
                folder_name = f"电影 & Cafe [{seed}] ({year})"
            if scenario == "duplicate_version":
                folder_name = f"movie-{index + 1:04d}-director-cut"

            movie = _movie_record(
                index=index,
                movie_id=movie_id,
                title=title,
                title_cn=title_cn,
                year=year,
                category=category,
                scenario=scenario,
                folder_name=folder_name,
                base_time=base_time,
                rng=rng,
                with_artwork=profile == "normal",
            )
            movies.append(movie)
            user_states.append(_user_state(movie_id, index, base_time))

            scenario_info = _write_media_case(
                media_root=media_root,
                index=index,
                title=title,
                title_cn=title_cn,
                year=year,
                scenario=scenario,
                folder_name=folder_name,
                seed=seed,
                with_artwork=profile == "normal",
            )
            media_scenarios.append(scenario_info)

        root_video_path = None
        if profile == "mixed":
            root_video = media_root / "Root Only (2024).mp4"
            if not root_video.exists():
                root_video.write_bytes(VIDEO_BYTES)
            root_video_path = "media/Root Only (2024).mp4"

        invalid_records = _invalid_records() if profile == "mixed" else []
        manifest = {
            "generator": GENERATOR_NAME,
            "schema_version": SCHEMA_VERSION,
            "profile": profile,
            "seed": seed,
            "count": count,
            "distribution": {
                "complete": complete,
                "incomplete": incomplete,
                "edge": edge,
            },
            "files": {
                "movies": "movies.json",
                "user_states": "user_states.json",
                "invalid_records": "invalid_records.json",
                "media_root": "media",
            },
            "media_scenarios": media_scenarios,
            "root_video": root_video_path,
            "invalid_record_names": [record["name"] for record in invalid_records],
            "cleanup": "uv run python scripts/generate_test_data.py --clean --output-dir <same-dir>",
        }
        _write_json(staging / "manifest.json", manifest)
        _write_json(staging / "movies.json", movies)
        _write_json(staging / "user_states.json", user_states)
        _write_json(staging / "invalid_records.json", invalid_records)

        if output.exists():
            if not force:
                raise ValueError(
                    f"Output directory already exists: {output}; use --force only for a generated directory"
                )
            clean_dataset(output)
        staging.replace(output)
        return manifest
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def clean_dataset(output_dir: str | Path) -> None:
    """Delete exactly one generator-owned output directory after verification."""
    output = _safe_output_path(output_dir)
    manifest_path = output / "manifest.json"
    if not output.is_dir() or not manifest_path.is_file():
        raise ValueError(f"Refusing to clean an unmarked generator directory: {output}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Refusing to clean an unreadable generator manifest: {output}") from exc
    if manifest.get("generator") != GENERATOR_NAME or manifest.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"Refusing to clean a directory not created by this generator: {output}")
    shutil.rmtree(output)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=DEFAULT_COUNT, help="number of movie records (default: 200)")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="random seed (default: 549)")
    parser.add_argument(
        "--profile",
        choices=DATA_PROFILES,
        default="mixed",
        help="mixed includes edge cases; normal creates only valid demo movies with local artwork",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--force", action="store_true", help="replace an existing generator-owned output directory")
    parser.add_argument("--clean", action="store_true", help="remove the exact generator-owned output directory")
    args = parser.parse_args(argv)

    try:
        if args.clean:
            clean_dataset(args.output_dir)
            print(f"Removed test data: {Path(args.output_dir).expanduser().resolve()}")
        else:
            manifest = generate_dataset(
                args.output_dir,
                count=args.count,
                seed=args.seed,
                profile=args.profile,
                force=args.force,
            )
            print(
                f"Generated {manifest['count']} movies with seed {manifest['seed']} "
                f"at {Path(args.output_dir).expanduser().resolve()}"
            )
        return 0
    except ValueError as exc:
        parser.error(str(exc))
        return 2


def _distribution(count: int) -> tuple[int, int, int]:
    complete = int(count * 0.7 + 0.5)
    incomplete = int(count * 0.2 + 0.5)
    return complete, incomplete, count - complete - incomplete


def _category_for(index: int, complete: int, incomplete: int) -> str:
    if index < complete:
        return "complete"
    if index < complete + incomplete:
        return "incomplete"
    return "edge"


def _movie_record(
    *,
    index: int,
    movie_id: str,
    title: str,
    title_cn: str,
    year: int,
    category: str,
    scenario: str,
    folder_name: str,
    base_time: datetime,
    rng: random.Random,
    with_artwork: bool,
) -> dict[str, Any]:
    stamp = (base_time + timedelta(days=index)).isoformat()
    complete = category == "complete"
    incomplete = category == "incomplete"
    has_external_ids = complete or (incomplete and index % 3 == 0)
    tmdb_id = str(100000 + index) if has_external_ids else None
    imdb_id = f"tt{5000000 + index:07d}" if has_external_ids and index % 2 == 0 else None
    genres = list(GENRES[index % len(GENRES)]) if complete else (["Drama"] if incomplete else [])
    countries = [COUNTRIES[index % len(COUNTRIES)]] if complete else None
    overview = f"A deterministic 5X49 fixture story about {title_cn}." if complete else None
    runtime = 80 + ((index * 11) % 96) if complete else None
    rating = round(1.5 + rng.random() * 3.4, 1) if complete else None
    scenario_path = f"/media/{folder_name}"
    video_file = "movie.mp4"
    if scenario == "missing_nfo":
        video_file = f"{_safe_filename(title)} ({year}).mp4"
    if scenario == "multiple_videos":
        video_file = "clip-a.mp4"
    if scenario in {"no_video", "temporary_video_only"}:
        video_file = None
    if scenario == "root_video":
        video_file = "Root Only (2024).mp4"

    return {
        "id": movie_id,
        "title": title,
        "title_cn": title_cn,
        "year": year,
        "poster_local": (
            f"{scenario_path}/movie-poster.jpg"
            if with_artwork
            else (f"{scenario_path}/poster.jpg" if complete and index % 4 == 0 else None)
        ),
        "backdrop_local": f"{scenario_path}/movie-fanart.jpg" if with_artwork else None,
        "poster_thumb_local": None,
        "backdrop_thumb_local": None,
        "poster_path": f"/fixture/poster-{index + 1:04d}.jpg" if complete else None,
        "backdrop_path": f"/fixture/backdrop-{index + 1:04d}.jpg" if complete and index % 2 == 0 else None,
        "tmdb_id": tmdb_id,
        "imdb_id": imdb_id,
        "overview": overview,
        "plot": overview,
        "director": f"Director {index % 11 + 1}" if complete else None,
        "runtime": runtime,
        "countries": countries,
        "audio_tracks": (
            [{"codec": "aac", "language": "中文" if index % 2 else "en", "channels": "2"}]
            if complete
            else None
        ),
        "imdb_rating": rating,
        "external_scores": [{"source": "fixture", "value": 50 + index % 51}] if complete else None,
        "external_scores_updated_at": stamp if complete else None,
        "external_scores_error": None,
        "genres": genres,
        "actors": ([{"name": f"Actor {index % 17 + 1}", "role": "Lead"}] if complete else None),
        "analysis_status": "pending",
        "micro_genre": None,
        "micro_genre_definition": None,
        "analysis_data": None,
        "folder_name": folder_name,
        "video_file": video_file,
        "nfo_source": (
            "filename"
            if scenario == "missing_nfo"
            else ("tmdb" if index % 2 == 0 else "tmm")
        ),
        "nfo_file": None if scenario == "missing_nfo" else "movie.nfo",
        "nfo_path": None,
        "nfo_size": None,
        "nfo_mtime": None,
        "nfo_fingerprint": None,
        "media_path": f"{scenario_path}/{video_file}" if video_file else None,
        "folder_path": scenario_path,
        "file_size": len(VIDEO_BYTES) if video_file else None,
        "file_mtime": 1735689600.0 + index if video_file else None,
        "video_width": (3840 if index % 5 == 0 else 1920) if complete else None,
        "video_height": (2160 if index % 5 == 0 else 1080) if complete else None,
        "video_codec": "hevc" if complete and index % 2 else "h264",
        "video_bitrate": 8000000 + index * 1000 if complete else None,
        "video_duration": float(runtime * 60) if runtime else None,
        "video_fps": 24.0 if complete else None,
        "video_dynamic_range": "HDR10" if complete and index % 6 == 0 else None,
        "video_bit_depth": 10 if complete and index % 6 == 0 else (8 if complete else None),
        "added_at": stamp,
        "last_seen_at": stamp if scenario not in {"root_video"} else None,
        "missing_since": stamp if scenario == "temporary_video_only" else None,
        "library_status": "missing" if scenario == "temporary_video_only" else "available",
        "metadata_updated_at": stamp,
        "metadata_source": "fixture",
        "scrape_status": (
            "pending"
            if scenario in {"missing_nfo", "corrupt_xml", "root_video"}
            else "matched"
        ),
        "scrape_error": None,
        "scraped_at": stamp if complete else None,
        "tmdb_confidence": 0.99 if complete else None,
    }


def _user_state(movie_id: str, index: int, base_time: datetime) -> dict[str, Any]:
    updated = (base_time + timedelta(days=index, hours=3)).isoformat()
    watched = index % 3 != 0
    return {
        "movie_id": movie_id,
        "watched": watched,
        "watched_at": (base_time + timedelta(days=index, hours=2)).isoformat() if watched else None,
        "rating": (index % 5) + 1 if watched else None,
        "favorite": index % 7 == 0,
        "notes": "含中文备注 / fixture note" if index % 11 == 0 else None,
        "updated_at": updated,
    }


def _write_media_case(
    *,
    media_root: Path,
    index: int,
    title: str,
    title_cn: str,
    year: int,
    scenario: str,
    folder_name: str,
    seed: int,
    with_artwork: bool,
) -> dict[str, Any]:
    if scenario == "root_video":
        root_video = media_root / "Root Only (2024).mp4"
        root_video.write_bytes(VIDEO_BYTES)
        return {
            "index": index,
            "scenario": scenario,
            "title": title,
            "path": "media/Root Only (2024).mp4",
            "expected": "root_only",
        }

    folder = media_root / folder_name
    folder.mkdir(parents=True)
    if scenario == "missing_nfo":
        video = folder / f"{_safe_filename(title)} ({year}).mp4"
        video.write_bytes(VIDEO_BYTES)
        expected = "filename_fallback"
    elif scenario == "corrupt_xml":
        (folder / "movie.nfo").write_text("<movie><title>broken", encoding="utf-8")
        (folder / "movie.mp4").write_bytes(VIDEO_BYTES)
        expected = "rejected"
    elif scenario == "multiple_videos":
        (folder / "clip-b.mkv").write_bytes(VIDEO_BYTES)
        (folder / "clip-a.mp4").write_bytes(VIDEO_BYTES)
        _write_nfo(folder / "movie.nfo", title, title_cn, year, seed, index)
        expected = "parsed_first_video"
    elif scenario == "duplicate_version":
        (folder / "movie.mp4").write_bytes(VIDEO_BYTES)
        _write_nfo(
            folder / "movie.nfo",
            title,
            title_cn,
            1967,
            seed,
            index,
            tmdb_id="100000",
        )
        expected = "parsed_duplicate_id"
    elif scenario == "no_video":
        _write_nfo(folder / "movie.nfo", title, title_cn, year, seed, index)
        expected = "parsed_without_video"
    elif scenario == "temporary_video_only":
        (folder / "movie.mp4.part").write_bytes(VIDEO_BYTES)
        _write_nfo(folder / "movie.nfo", title, title_cn, year, seed, index)
        expected = "parsed_without_usable_video"
    else:
        (folder / "movie.mp4").write_bytes(VIDEO_BYTES)
        _write_nfo(folder / "movie.nfo", title, title_cn, year, seed, index)
        expected = "parsed"

    if with_artwork:
        _write_demo_artwork(folder / "movie-poster.jpg", (600, 900), index, year, "PORTRAIT")
        _write_demo_artwork(folder / "movie-fanart.jpg", (1280, 720), index, year, "LANDSCAPE")

    return {
        "index": index,
        "scenario": scenario,
        "title": title,
        "path": f"media/{folder_name}",
        "expected": expected,
    }


def _write_nfo(
    path: Path,
    title: str,
    title_cn: str,
    year: int,
    seed: int,
    index: int,
    *,
    tmdb_id: str | None = None,
) -> None:
    root = ET.Element("movie")
    _xml_text(root, "generator", "5X49" if index % 2 == 0 else "tinyMediaManager")
    _xml_text(root, "title", title_cn)
    _xml_text(root, "originaltitle", title)
    _xml_text(root, "year", str(year))
    _xml_text(root, "tmdbid", tmdb_id or str(100000 + index))
    _xml_text(root, "id", f"tt{5000000 + index:07d}")
    _xml_text(root, "plot", f"A local-only NFO fixture for seed {seed}, item {index + 1}.")
    _xml_text(root, "runtime", str(90 + index % 100))
    _xml_text(root, "genre", GENRES[index % len(GENRES)][0])
    _xml_text(root, "country", COUNTRIES[index % len(COUNTRIES)])
    _xml_text(root, "director", f"Director {index % 11 + 1}")
    rating = ET.SubElement(root, "rating", {"name": "imdb"})
    _xml_text(rating, "value", f"{5.0 + (index % 46) / 10:.1f}")
    actor = ET.SubElement(root, "actor")
    _xml_text(actor, "name", f"Actor {index % 17 + 1}")
    _xml_text(actor, "role", "Lead")
    thumb = ET.SubElement(root, "thumb", {"aspect": "poster"})
    thumb.text = f"https://image.tmdb.org/t/p/original/fixture-poster-{index + 1:04d}.jpg"
    fanart = ET.SubElement(root, "fanart")
    fanart_thumb = ET.SubElement(fanart, "thumb")
    fanart_thumb.text = f"https://image.tmdb.org/t/p/original/fixture-backdrop-{index + 1:04d}.jpg"
    streamdetails = ET.SubElement(root, "streamdetails")
    audio = ET.SubElement(streamdetails, "audio")
    _xml_text(audio, "codec", "aac")
    _xml_text(audio, "language", "en")
    _xml_text(audio, "channels", "2")
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    tree.write(path, encoding="utf-8", xml_declaration=True)


def _write_demo_artwork(
    path: Path,
    size: tuple[int, int],
    index: int,
    year: int,
    layout: str,
) -> None:
    """Write deterministic local artwork for the normal demo profile."""
    width, height = size
    palette = (
        ((20, 24, 36), (170, 54, 62), (244, 178, 71)),
        ((13, 31, 34), (32, 117, 126), (180, 225, 151)),
        ((28, 19, 45), (116, 68, 153), (229, 164, 255)),
        ((38, 24, 13), (174, 91, 38), (255, 205, 126)),
        ((13, 24, 45), (42, 91, 168), (138, 198, 255)),
        ((35, 16, 25), (151, 48, 89), (255, 153, 188)),
    )[index % 6]
    start, middle, accent = palette
    image = Image.new("RGB", size, start)
    draw = ImageDraw.Draw(image, "RGBA")

    for y in range(height):
        ratio = y / max(height - 1, 1)
        color = tuple(round(start[channel] * (1 - ratio) + middle[channel] * ratio) for channel in range(3))
        draw.line((0, y, width, y), fill=(*color, 255))

    orbit_size = int(min(width, height) * 0.72)
    orbit_left = int(width * (0.55 if layout == "PORTRAIT" else 0.68)) - orbit_size // 2
    orbit_top = int(height * 0.32) - orbit_size // 2
    draw.ellipse(
        (orbit_left, orbit_top, orbit_left + orbit_size, orbit_top + orbit_size),
        outline=(*accent, 170),
        width=max(3, width // 120),
    )
    draw.rectangle((0, int(height * 0.72), width, height), fill=(0, 0, 0, 105))
    draw.text(
        (int(width * 0.07), int(height * 0.78)),
        f"5X49 TEST FILM {index + 1:02d}",
        fill=(255, 255, 255, 235),
    )
    draw.text(
        (int(width * 0.07), int(height * 0.84)),
        str(year),
        fill=(*accent, 255),
    )
    image.save(path, format="JPEG", quality=88, optimize=True)


def _invalid_records() -> list[dict[str, Any]]:
    return [
        {"name": "movie_missing_primary_key", "payload": {"title": "Missing ID", "year": 2024}},
        {
            "name": "movie_missing_required_title",
            "payload": {"id": "invalid_missing_title", "year": 2024},
        },
        {
            "name": "movie_id_rejected_by_api_validator",
            "payload": {"id": "contains/slash", "title": "Unsafe ID", "year": 2024},
        },
        {
            "name": "user_state_rating_out_of_range",
            "payload": {
                "movie_id": "fixture_0001",
                "watched": True,
                "rating": 6,
                "favorite": False,
            },
        },
    ]


def _safe_output_path(output_dir: str | Path) -> Path:
    raw = Path(output_dir).expanduser()
    if raw.is_symlink():
        raise ValueError(f"Refusing to follow a symlink as output: {raw}")
    output = raw.resolve()
    if output == Path(output.anchor):
        raise ValueError(f"Refusing to use a filesystem root as output: {output}")

    backend_root = Path(__file__).resolve().parents[1]
    repo_root = backend_root.parent
    current = Path.cwd().resolve()
    protected = (backend_root, repo_root, current)
    if any(output == path or path.is_relative_to(output) for path in protected):
        raise ValueError(f"Output directory is too broad or protected: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    return output


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _xml_text(parent: ET.Element, tag: str, value: Any) -> None:
    child = ET.SubElement(parent, tag)
    child.text = str(value)


def _safe_filename(value: str) -> str:
    cleaned = re.sub(r"[<>:\"/\\|?*]", "_", value)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return cleaned[:100] or "fixture"


if __name__ == "__main__":
    sys.exit(main())
