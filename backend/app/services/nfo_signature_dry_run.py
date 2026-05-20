from collections import Counter
from pathlib import Path
from typing import Optional
import os
import xml.etree.ElementTree as ET

from sqlmodel import Session, select

from app.database import engine
from app.models import Movie
from app.services.scanner import NFOScanner
from app.services.settings import get_media_dir


NFO_SIGNATURE_FIELDS = (
    "nfo_file",
    "nfo_path",
    "nfo_size",
    "nfo_mtime",
    "nfo_fingerprint",
)


class NFOSignatureDryRun:
    """Read-only check for NFO signature changes discovered by a scan."""

    def run(
        self,
        *,
        media_dir: Optional[str] = None,
        folder_path: Optional[str] = None,
        limit: int = 200,
        include_unchanged: bool = False,
    ) -> dict:
        limit = max(1, min(limit, 1000))
        scanner_root = self._scanner_root(media_dir, folder_path)
        scanner = NFOScanner(str(scanner_root))
        folders = self._target_folders(media_dir, folder_path)

        with Session(engine) as session:
            movies = list(session.exec(select(Movie)).all())

        by_id = {movie.id: movie.model_dump() for movie in movies}
        by_folder_path = {
            movie.folder_path: movie.model_dump()
            for movie in movies
            if movie.folder_path
        }
        by_media_path = {
            movie.media_path: movie.model_dump()
            for movie in movies
            if movie.media_path
        }

        results = []
        counts: Counter[str] = Counter()
        nfo_files_found = 0
        results_available = 0

        for folder in folders:
            video_file = scanner._find_video_file(folder)
            nfo_file = scanner._find_nfo_file(folder, video_file)
            if not nfo_file:
                counts["no_nfo"] += 1
                continue

            nfo_files_found += 1
            signature = scanner.nfo_signature(nfo_file)
            candidate_id, parse_error = self._candidate_movie_id(scanner, nfo_file, folder, video_file)
            movie = (
                by_folder_path.get(str(folder.resolve()))
                or (by_media_path.get(str(video_file.resolve())) if video_file else None)
                or (by_id.get(candidate_id) if candidate_id else None)
            )

            if not movie:
                status = "unmatched_movie"
                counts[status] += 1
                results_available += 1
                self._append_result(
                    results,
                    limit,
                    {
                        "status": status,
                        "movie_id": candidate_id,
                        "folder_path": str(folder.resolve()),
                        "nfo_path": signature["nfo_path"],
                        "observed": signature,
                        "current": None,
                        "changed_fields": list(NFO_SIGNATURE_FIELDS),
                        "parse_error": parse_error,
                    },
                )
                continue

            current = {field: movie.get(field) for field in NFO_SIGNATURE_FIELDS}
            changed_fields = [
                field
                for field in NFO_SIGNATURE_FIELDS
                if current.get(field) != signature.get(field)
            ]
            if not changed_fields:
                status = "unchanged"
            elif not any(current.values()):
                status = "new_signature"
            else:
                status = "changed"
            counts[status] += 1

            if status != "unchanged" or include_unchanged:
                results_available += 1
                self._append_result(
                    results,
                    limit,
                    {
                        "status": status,
                        "movie_id": movie["id"],
                        "title": movie.get("title"),
                        "year": movie.get("year"),
                        "folder_path": str(folder.resolve()),
                        "nfo_path": signature["nfo_path"],
                        "observed": signature,
                        "current": current,
                        "changed_fields": changed_fields,
                        "parse_error": parse_error,
                    },
                )

        return {
            "dry_run": True,
            "media_dir": str(Path(media_dir).resolve()) if media_dir else None,
            "folder_path": str(Path(folder_path).resolve()) if folder_path else None,
            "folders_scanned": len(folders),
            "nfo_files_found": nfo_files_found,
            "matched_movies": counts["unchanged"] + counts["new_signature"] + counts["changed"],
            "unchanged": counts["unchanged"],
            "new_signatures": counts["new_signature"],
            "changed_signatures": counts["changed"],
            "unmatched_movies": counts["unmatched_movie"],
            "folders_without_nfo": counts["no_nfo"],
            "results_returned": len(results),
            "results_truncated": results_available > len(results),
            "results": results,
        }

    def _target_folders(self, media_dir: Optional[str], folder_path: Optional[str]) -> list[Path]:
        if folder_path:
            folder = Path(folder_path).resolve()
            if not folder.exists() or not folder.is_dir():
                raise FileNotFoundError(f"Movie folder not found: {folder}")
            return [folder]

        root = Path(media_dir or get_media_dir() or os.getenv("MEDIA_DIR", "/media")).resolve()
        if not root.exists() or not root.is_dir():
            raise FileNotFoundError(f"Media directory not found: {root}")
        return [
            folder
            for folder in sorted(root.iterdir(), key=lambda path: path.name.lower())
            if folder.is_dir() and not folder.name.startswith(".")
        ]

    def _scanner_root(self, media_dir: Optional[str], folder_path: Optional[str]) -> Path:
        if folder_path:
            return Path(folder_path).resolve().parent
        return Path(media_dir or get_media_dir() or os.getenv("MEDIA_DIR", "/media")).resolve()

    def _candidate_movie_id(
        self,
        scanner: NFOScanner,
        nfo_file: Path,
        folder: Path,
        video_file: Optional[Path],
    ) -> tuple[Optional[str], Optional[str]]:
        try:
            root = ET.parse(nfo_file).getroot()
            year = int(root.findtext("year") or 0)
            return scanner._build_movie_id(
                root.findtext("tmdbid"),
                root.findtext("id"),
                year,
                folder,
                video_file,
            ), None
        except Exception as exc:
            return None, str(exc)

    def _append_result(self, results: list[dict], limit: int, result: dict):
        if len(results) < limit:
            results.append(result)


nfo_signature_dry_run = NFOSignatureDryRun()
