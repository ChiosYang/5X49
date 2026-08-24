"""Generate a curated, local-only media library for Gate A rehearsal.

The generated MP4 files contain FFmpeg test patterns and synthetic tones.  No
copyrighted film footage, NFO metadata, artwork, or application database rows
are included.  The missing metadata is intentional: the library is meant to
exercise the normal scan and manual scrape workflow through the application.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


GENERATOR_NAME = "5X49 Gate A curated acceptance media generator"
SCHEMA_VERSION = 1
DEFAULT_OUTPUT_DIR = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "gate-a"
    / "acceptance-library"
)
LARGE_FILE_MIN_BYTES = 12 * 1024 * 1024


@dataclass(frozen=True)
class MovieSpec:
    title: str
    year: int
    frequency: int
    edition: str | None = None
    large_file: bool = False

    @property
    def display_name(self) -> str:
        suffix = f" [{self.edition}]" if self.edition else ""
        return f"{self.title} ({self.year}){suffix}"


MOVIES = (
    MovieSpec("The Godfather", 1972, 220),
    MovieSpec("Farewell My Concubine", 1993, 247),
    MovieSpec("Chungking Express", 1994, 262),
    MovieSpec("The Matrix", 1999, 294),
    MovieSpec("The Matrix", 1999, 330, edition="UHD Edition"),
    MovieSpec("In the Mood for Love", 2000, 349),
    MovieSpec("Yi Yi", 2000, 392),
    MovieSpec("Spirited Away", 2001, 440),
    MovieSpec("The Grand Budapest Hotel", 2014, 494),
    MovieSpec("Interstellar", 2014, 523),
    MovieSpec("Mad Max Fury Road", 2015, 587),
    MovieSpec("Dune Part Two", 2024, 659, large_file=True),
    MovieSpec("A Long Day's Journey Into Night", 2018, 698),
    MovieSpec("Parasite", 2019, 784),
    MovieSpec("Portrait of a Lady on Fire", 2019, 880),
    MovieSpec("Everything Everywhere All at Once", 2022, 988),
)


def generate_library(
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    *,
    force: bool = False,
    ffmpeg: str | None = None,
    ffprobe: str | None = None,
) -> dict[str, Any]:
    output = Path(output_dir).expanduser().resolve()
    _validate_output_path(output)
    ffmpeg_path = ffmpeg or shutil.which("ffmpeg")
    ffprobe_path = ffprobe or shutil.which("ffprobe")
    if not ffmpeg_path or not ffprobe_path:
        raise ValueError("ffmpeg and ffprobe must both be available on PATH")

    if output.exists():
        if not force:
            raise ValueError(f"Output already exists: {output}")
        _verify_generator_output(output)

    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=output.parent))
    try:
        media_root = staging / "media"
        media_root.mkdir()
        (staging / "source").mkdir()
        (staging / "runtime" / "data").mkdir(parents=True)
        (staging / "runtime" / "logs").mkdir()

        items = []
        for index, movie in enumerate(MOVIES, start=1):
            movie_dir = media_root / movie.display_name
            movie_dir.mkdir()
            video_path = movie_dir / f"{movie.display_name}.mp4"
            _generate_video(ffmpeg_path, video_path, movie, index)
            probe = _probe_video(ffprobe_path, video_path)
            size = video_path.stat().st_size
            if movie.large_file and size <= LARGE_FILE_MIN_BYTES:
                raise ValueError(
                    f"Large-file fixture is only {size} bytes; expected more than "
                    f"{LARGE_FILE_MIN_BYTES}"
                )
            items.append(
                {
                    **asdict(movie),
                    "folder": movie.display_name,
                    "video": f"media/{movie.display_name}/{movie.display_name}.mp4",
                    "size_bytes": size,
                    "sha256": _sha256(video_path),
                    "probe": probe,
                }
            )

        manifest = {
            "generator": GENERATOR_NAME,
            "schema_version": SCHEMA_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "kind": "curated_acceptance_library",
            "evidence_scope": (
                "Normal scan, manual scrape, user-state, viewing, relink, and "
                "restore rehearsal; not a substitute for a naturally aged user library."
            ),
            "movie_count": len(items),
            "media_root": "media",
            "database": "source/library.db",
            "large_file_threshold_bytes": LARGE_FILE_MIN_BYTES,
            "items": items,
        }
        _write_json(staging / "manifest.json", manifest)
        (staging / "media-root.txt").write_text(
            str((output / "media").resolve()) + "\n",
            encoding="utf-8",
        )
        (staging / "README.txt").write_text(_readme(output), encoding="utf-8")

        if output.exists():
            shutil.rmtree(output)
        staging.replace(output)
        return manifest
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def clean_library(output_dir: str | Path) -> None:
    output = Path(output_dir).expanduser().resolve()
    _validate_output_path(output)
    _verify_generator_output(output)
    shutil.rmtree(output)


def _generate_video(
    ffmpeg: str,
    destination: Path,
    movie: MovieSpec,
    index: int,
) -> None:
    size = "1280x720" if movie.large_file else "960x540"
    duration = "9" if movie.large_file else "4"
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        f"testsrc2=size={size}:rate=24",
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency={movie.frequency}:sample_rate=48000",
        "-t",
        duration,
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast" if movie.large_file else "veryfast",
    ]
    if movie.large_file:
        command.extend(
            [
                "-b:v",
                "14M",
                "-minrate",
                "14M",
                "-maxrate",
                "14M",
                "-bufsize",
                "28M",
                "-x264-params",
                "nal-hrd=cbr:filler=1",
            ]
        )
    else:
        command.extend(["-crf", str(23 + index % 5)])
    command.extend(
        [
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "96k",
            "-movflags",
            "+faststart",
            "-metadata",
            f"title=5X49 synthetic fixture {index:02d}",
            "-y",
            str(destination),
        ]
    )
    _run(command, f"ffmpeg failed for {movie.display_name}")


def _probe_video(ffprobe: str, video_path: Path) -> dict[str, Any]:
    command = [
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        "format=duration:stream=codec_name,codec_type,width,height,sample_rate,channels",
        "-of",
        "json",
        str(video_path),
    ]
    result = _run(command, f"ffprobe failed for {video_path.name}")
    data = json.loads(result.stdout)
    streams = data.get("streams") or []
    if not any(stream.get("codec_type") == "video" for stream in streams):
        raise ValueError(f"No video stream found in {video_path}")
    if not any(stream.get("codec_type") == "audio" for stream in streams):
        raise ValueError(f"No audio stream found in {video_path}")
    duration = float((data.get("format") or {}).get("duration") or 0)
    if duration <= 0:
        raise ValueError(f"Invalid duration for {video_path}")
    return {"duration_seconds": duration, "streams": streams}


def _run(command: list[str], error_message: str) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown error"
        raise ValueError(f"{error_message}: {detail}")
    return result


def _verify_generator_output(output: Path) -> None:
    manifest_path = output / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Refusing to replace unmarked directory: {output}") from exc
    if (
        manifest.get("generator") != GENERATOR_NAME
        or manifest.get("schema_version") != SCHEMA_VERSION
    ):
        raise ValueError(f"Refusing to replace non-generator directory: {output}")


def _validate_output_path(output: Path) -> None:
    gate_root = (
        Path(__file__).resolve().parents[1] / "data" / "gate-a"
    ).resolve()
    if output == gate_root or gate_root not in output.parents:
        raise ValueError(f"Output must be a child of {gate_root}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _readme(output: Path) -> str:
    return f"""5X49 curated acceptance library

This directory is generated and Git-ignored. The videos contain only synthetic
test patterns and tones. They intentionally have no NFO files or artwork.

Media root:
{output / 'media'}

Isolated database:
{output / 'source' / 'library.db'}

Start the backend from the runtime directory so settings and artwork caches stay
isolated from backend/data. Set SQLITE_DB_PATH to the database above, MEDIA_DIR
to the media root, and LIBRARY_READ_SOURCE to canonical. Then start the normal
frontend on port 5549 and use the UI to scan, scrape, and add personal state.

Evidence label: curated acceptance library. This exercises normal product
workflows but does not replace a naturally aged real-user library for strict
Gate A evidence.
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--clean", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.clean:
            clean_library(args.output_dir)
            print(f"Removed curated acceptance library: {args.output_dir.resolve()}")
        else:
            manifest = generate_library(args.output_dir, force=args.force)
            print(
                f"Generated {manifest['movie_count']} synthetic movies at "
                f"{args.output_dir.resolve()}"
            )
        return 0
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
