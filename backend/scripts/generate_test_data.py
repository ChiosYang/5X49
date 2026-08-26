"""Generate deterministic local media fixtures for the fresh Canonical scanner."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw


GENERATOR_NAME = "5X49 fresh Canonical media generator"
SCHEMA_VERSION = 2
DEFAULT_SEED = 549
DEFAULT_COUNT = 200
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parents[1] / "data" / "generated-test-data"
VIDEO_BYTES = b"5X49_TEST_VIDEO_PLACEHOLDER\n"
DATA_PROFILES = ("mixed", "normal")
TITLE_PAIRS = (
    ("The Quiet Signal", "静默信号"),
    ("The Seventh Letter by the Sea", "海边的第七封信"),
    ("Light After Midnight", "午夜之后的光"),
    ("Cosmic Garden", "太空花园"),
    ("Cafe in the Rain", "雨中的咖啡馆"),
    ("Tokyo Negative Space", "東京の余白"),
    ("The Cartographer of Distant Stars", "遥远星图的制作者"),
    ("A-B: Director's Cut", "A-B：导演剪辑版"),
)
GENRES = ("Drama", "Mystery", "Animation", "Family", "Science Fiction", "Adventure", "Documentary", "Romance")
COUNTRIES = ("US", "CN", "FR", "JP", "BR", "DE", "GB")
EDGE_SCENARIOS = ("missing_nfo", "corrupt_xml", "multiple_videos", "no_video", "temporary_video_only", "root_video")


def generate_dataset(
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    *,
    count: int = DEFAULT_COUNT,
    seed: int = DEFAULT_SEED,
    profile: str = "mixed",
    force: bool = False,
) -> dict[str, Any]:
    if count < 0:
        raise ValueError("count must be non-negative")
    if profile not in DATA_PROFILES:
        raise ValueError(f"profile must be one of: {', '.join(DATA_PROFILES)}")
    output = _safe_output_path(output_dir)
    if output.exists() and not output.is_dir():
        raise ValueError(f"Output path is not a directory: {output}")

    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=str(output.parent)))
    try:
        media_root = staging / "media"
        media_root.mkdir()
        scenarios: list[dict[str, Any]] = []
        for index in range(count):
            title, localized = TITLE_PAIRS[index % len(TITLE_PAIRS)]
            year = 1950 + ((index * 37 + seed) % 76)
            scenario = "valid_nfo" if profile == "normal" else (
                EDGE_SCENARIOS[index % len(EDGE_SCENARIOS)] if index >= max(1, int(count * 0.8)) else "valid_nfo"
            )
            scenarios.append(
                _write_media_case(media_root, index, title, localized, year, scenario, seed, profile == "normal")
            )

        manifest = {
            "generator": GENERATOR_NAME,
            "schema_version": SCHEMA_VERSION,
            "profile": profile,
            "seed": seed,
            "count": count,
            "media_root": "media",
            "media_scenarios": scenarios,
            "cleanup": "uv run python scripts/generate_test_data.py --clean --output-dir <same-dir>",
        }
        _write_json(staging / "manifest.json", manifest)
        if output.exists():
            if not force:
                raise ValueError(f"Output directory already exists: {output}; use --force only for generated data")
            clean_dataset(output)
        staging.replace(output)
        return manifest
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def clean_dataset(output_dir: str | Path) -> None:
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
    parser.add_argument("--count", type=int, default=DEFAULT_COUNT)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--profile", choices=DATA_PROFILES, default="mixed")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--clean", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.clean:
            clean_dataset(args.output_dir)
            print(f"Removed test data: {args.output_dir.resolve()}")
        else:
            result = generate_dataset(args.output_dir, count=args.count, seed=args.seed, profile=args.profile, force=args.force)
            print(f"Generated {result['count']} Film media fixtures at {args.output_dir.resolve()}")
        return 0
    except ValueError as exc:
        parser.error(str(exc))
        return 2


def _write_media_case(
    media_root: Path,
    index: int,
    title: str,
    localized: str,
    year: int,
    scenario: str,
    seed: int,
    with_artwork: bool,
) -> dict[str, Any]:
    if scenario == "root_video":
        path = media_root / f"Root Film {index + 1} ({year}).mp4"
        path.write_bytes(VIDEO_BYTES)
        return {"index": index, "scenario": scenario, "path": path.relative_to(media_root.parent).as_posix()}

    folder = media_root / f"film-{index + 1:04d}"
    folder.mkdir()
    video = folder / "film.mp4"
    if scenario == "multiple_videos":
        (folder / "clip-b.mkv").write_bytes(VIDEO_BYTES)
        video = folder / "clip-a.mp4"
    if scenario not in {"no_video", "temporary_video_only"}:
        video.write_bytes(VIDEO_BYTES)
    elif scenario == "temporary_video_only":
        (folder / "film.mp4.part").write_bytes(VIDEO_BYTES)

    nfo = folder / "film.nfo"
    if scenario == "corrupt_xml":
        nfo.write_text("<movie><title>broken", encoding="utf-8")
    elif scenario != "missing_nfo":
        _write_nfo(nfo, title, localized, year, seed, index)

    if with_artwork:
        _write_artwork(folder / "film-poster.jpg", (600, 900), index, year, "POSTER")
        _write_artwork(folder / "film-fanart.jpg", (1280, 720), index, year, "BACKDROP")
    return {
        "index": index,
        "scenario": scenario,
        "path": folder.relative_to(media_root.parent).as_posix(),
        "expected": "parsed" if scenario == "valid_nfo" else scenario,
    }


def _write_nfo(path: Path, title: str, localized: str, year: int, seed: int, index: int) -> None:
    root = ET.Element("movie")
    values = {
        "title": localized,
        "originaltitle": title,
        "year": year,
        "tmdbid": 100000 + index,
        "id": f"tt{5000000 + index:07d}",
        "plot": f"A local-only fixture for seed {seed}, item {index + 1}.",
        "runtime": 90 + index % 100,
        "genre": GENRES[index % len(GENRES)],
        "country": COUNTRIES[index % len(COUNTRIES)],
        "director": f"Director {index % 11 + 1}",
    }
    for tag, value in values.items():
        ET.SubElement(root, tag).text = str(value)
    actor = ET.SubElement(root, "actor")
    ET.SubElement(actor, "name").text = f"Actor {index % 17 + 1}"
    ET.SubElement(actor, "role").text = "Lead"
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    tree.write(path, encoding="utf-8", xml_declaration=True)


def _write_artwork(path: Path, size: tuple[int, int], index: int, year: int, label: str) -> None:
    palette = ((18, 25, 38), (119, 45, 66), (224, 168, 77))
    image = Image.new("RGB", size, palette[index % len(palette)])
    draw = ImageDraw.Draw(image)
    draw.rectangle((size[0] * 0.08, size[1] * 0.08, size[0] * 0.92, size[1] * 0.92), outline=(235, 235, 230), width=max(2, size[0] // 120))
    draw.text((size[0] * 0.12, size[1] * 0.13), f"5X49 {label}\n{index + 1:02d} / {year}", fill=(245, 245, 240))
    image.save(path, format="JPEG", quality=88, optimize=True)


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
    if any(output == path or path.is_relative_to(output) for path in (backend_root, repo_root, current)):
        raise ValueError(f"Output directory is too broad or protected: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    return output


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
