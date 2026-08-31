import hashlib
import json
import re
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Optional
from uuid import uuid4

from app.services.event_bus import library_event_bus
from app.services.library import library_manager
from app.services.metadata.matcher import parse_title_year
from app.services.metadata.models import MetadataSearchResult, RootOrganizeOptions, ScrapeOptions
from app.services.metadata.scraper import metadata_scraper
from app.services.operation_manifests import operation_manifest_store
from app.services.settings import (
    get_media_dir,
    get_media_file_stable_seconds,
    get_organize_min_confidence,
    get_organize_rename_style,
    get_scrape_require_confirmation,
)


class RootVideoOrganizer:
    video_extensions = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".m4v", ".ts", ".iso"}
    sidecar_extensions = {".srt", ".ass", ".ssa", ".vtt", ".sub", ".idx"}
    ignored_suffixes = (".part", ".tmp", ".download", ".crdownload")

    def __init__(self):
        self._lock = Lock()
        self._status = {
            "state": "idle",
            "last_started_at": None,
            "last_finished_at": None,
            "last_error": None,
            "last_result": None,
        }

    def get_status(self) -> dict:
        with self._lock:
            return dict(self._status)

    def list_root_videos(self, media_dir: Optional[str] = None) -> list[dict]:
        root = Path(media_dir or get_media_dir()).resolve()
        if not root.exists() or not root.is_dir():
            raise FileNotFoundError(f"Directory not found: {root}")

        videos = []
        for path in self._root_videos(root):
            video = self._video_view(path, root, source_location="root", include_absolute_path=True)
            if video:
                videos.append(video)
        return videos

    def list_organization_candidates(self, media_dir: Optional[str] = None) -> list[dict]:
        root = Path(media_dir or get_media_dir()).resolve()
        if not root.exists() or not root.is_dir():
            raise FileNotFoundError(f"Directory not found: {root}")

        candidates = []
        for path in self._root_videos(root):
            video = self._video_view(path, root, source_location="root")
            if video:
                candidates.append(video)

        inbox = (root / "inbox").resolve()
        if inbox.is_dir():
            for path in self._videos_in_directory(inbox):
                video = self._video_view(path, root, source_location="legacy_inbox")
                if video:
                    candidates.append(video)

        return sorted(
            candidates,
            key=lambda item: (
                0 if item["source_location"] == "root" else 1,
                item["filename"].lower(),
            ),
        )

    def preview_organization(
        self,
        media_dir: str | Path,
        source_path: str,
        tmdb_id: int,
        rename_style: str = "preserve_stem",
    ) -> dict:
        root = Path(media_dir).resolve()
        source = self._resolve_candidate_source(root, source_path)
        if not self._is_usable_pending_video(source, root):
            raise ValueError("Source video is not stable or cannot be organized")
        if rename_style not in {"preserve_stem", "title_year"}:
            raise ValueError("Unsupported organization rename style")

        candidate = metadata_scraper.get_candidate(tmdb_id)
        parsed_title, parsed_year = parse_title_year(source.name)
        target_year = candidate.year or parsed_year
        target_dir = self._target_dir(root, candidate.title, target_year)
        target_video_name = self._target_video_name(
            source,
            candidate.title,
            target_year,
            rename_style,
        )
        target_video = target_dir / target_video_name
        sidecars = self._sidecar_plan(source, target_dir, target_video_name, rename_style)
        conflicts = []
        if target_video.exists():
            conflicts.append({"kind": "video", "name": target_video.name})
        conflicts.extend(
            {"kind": "sidecar", "name": item["target_name"]}
            for item in sidecars
            if item["conflict"]
        )

        stat = source.stat()
        source_relative = source.relative_to(root).as_posix()
        token_payload = {
            "source_path": source_relative,
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
            "tmdb_id": candidate.tmdb_id,
            "title": candidate.title,
            "year": target_year,
            "rename_style": rename_style,
            "target_folder": target_dir.name,
            "target_file": target_video.name,
            "sidecars": [
                {
                    "source_name": item["source_name"],
                    "target_name": item["target_name"],
                    "conflict": item["conflict"],
                }
                for item in sidecars
            ],
            "conflicts": conflicts,
        }
        confirmation_token = hashlib.sha256(
            json.dumps(
                token_payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        return {
            "source": {
                "source_path": source_relative,
                "filename": source.name,
                "size": stat.st_size,
                "source_location": "legacy_inbox" if source.parent == (root / "inbox").resolve() else "root",
            },
            "match": candidate.model_dump(),
            "target": {
                "folder_name": target_dir.name,
                "video_name": target_video.name,
            },
            "rename_style": rename_style,
            "sidecars": [
                {
                    "source_name": item["source_name"],
                    "target_name": item["target_name"],
                    "conflict": item["conflict"],
                }
                for item in sidecars
            ],
            "post_actions": {
                "write_nfo": True,
                "download_artwork": True,
            },
            "conflicts": conflicts,
            "can_confirm": not conflicts,
            "confirmation_token": confirmation_token,
        }

    def validate_organization_confirmation(
        self,
        media_dir: str | Path,
        source_path: str,
        tmdb_id: int,
        rename_style: str,
        confirmation_token: str,
    ) -> dict:
        preview = self.preview_organization(media_dir, source_path, tmdb_id, rename_style)
        if preview["confirmation_token"] != confirmation_token:
            raise RuntimeError("Organization preview is stale")
        if not preview["can_confirm"]:
            raise RuntimeError("Organization target has conflicts")
        return preview

    def organize_root(self, media_dir: Optional[str] = None, options: Optional[RootOrganizeOptions] = None) -> dict:
        options = options or RootOrganizeOptions(rename_style=get_organize_rename_style())
        root = Path(media_dir or get_media_dir()).resolve()
        started_at = datetime.now(timezone.utc).isoformat()
        self._set_status(state="running", last_started_at=started_at, last_error=None)
        result = {
            "processed": 0,
            "organized": 0,
            "scraped": 0,
            "needs_review": 0,
            "failed": 0,
            "skipped": 0,
            "items": [],
        }

        try:
            if not root.exists() or not root.is_dir():
                raise FileNotFoundError(f"Directory not found: {root}")

            for video_path in self._root_videos(root):
                item = self.organize_file(video_path, root, options)
                result["processed"] += 1
                result["items"].append(item)
                status = item.get("status")
                if status == "success":
                    result["organized"] += 1
                    result["scraped"] += 1 if item.get("scrape_status") == "success" else 0
                elif status == "needs_review":
                    result["needs_review"] += 1
                elif status == "skipped":
                    result["skipped"] += 1
                else:
                    result["failed"] += 1

            self._set_status(
                state="idle",
                last_finished_at=datetime.now(timezone.utc).isoformat(),
                last_result=result,
            )
            if result["processed"]:
                library_event_bus.publish_library_changed("root_videos_organized", result=result)
            return result
        except Exception as exc:
            self._set_status(
                state="error",
                last_finished_at=datetime.now(timezone.utc).isoformat(),
                last_error=str(exc),
            )
            raise

    def organize_file(
        self,
        video_path: Path,
        root: Path,
        options: RootOrganizeOptions,
        *,
        manifest_ref: str | None = None,
    ) -> dict:
        command_id = self._new_command_id("root_organize")
        video_path = video_path.resolve()
        if not self._is_usable_root_video(video_path, root):
            return {"status": "skipped", "source_name": video_path.name, "message": "Not a stable root video"}

        query, year = parse_title_year(video_path.name)
        candidates = metadata_scraper.search(query, year=year, language=options.language)
        if not candidates:
            return {"status": "failed", "source_name": video_path.name, "message": "No TMDB matches found"}

        best = candidates[0]
        min_confidence = options.min_confidence
        if min_confidence is None:
            min_confidence = get_organize_min_confidence()
        if best.score < min_confidence:
            return {
                "status": "needs_review",
                "source_name": video_path.name,
                "message": "Low confidence TMDB match",
                "candidate": best.model_dump(),
            }
        if get_scrape_require_confirmation():
            return {
                "status": "needs_review",
                "source_name": video_path.name,
                "message": "Manual confirmation required",
                "candidate": best.model_dump(),
            }

        return self._organize_matched_file(
            video_path,
            root,
            best,
            year,
            options,
            command_id=command_id,
            manifest_ref=manifest_ref,
        )

    def organize_file_confirmed(
        self,
        video_path: Path,
        root: Path,
        tmdb_id: int,
        options: RootOrganizeOptions,
        *,
        candidate: MetadataSearchResult | None = None,
        manifest_ref: str | None = None,
    ) -> dict:
        command_id = self._new_command_id("root_organize")
        video_path = video_path.resolve()
        if not self._is_usable_pending_video(video_path, root):
            return {"status": "skipped", "source_name": video_path.name, "message": "Not a stable root video"}

        _, year = parse_title_year(video_path.name)
        candidate = candidate or metadata_scraper.get_candidate(tmdb_id, options.language)
        return self._organize_matched_file(
            video_path,
            root,
            candidate,
            year,
            options,
            command_id=command_id,
            block_sidecar_conflicts=True,
            manifest_ref=manifest_ref,
        )

    def _organize_matched_file(
        self,
        video_path: Path,
        root: Path,
        candidate: MetadataSearchResult,
        parsed_year: int,
        options: RootOrganizeOptions,
        *,
        command_id: str,
        block_sidecar_conflicts: bool = False,
        manifest_ref: str | None = None,
    ) -> dict:
        target_dir = self._target_dir(root, candidate.title, candidate.year or parsed_year)
        target_video = target_dir / self._target_video_name(
            video_path,
            candidate.title,
            candidate.year or parsed_year,
            options.rename_style,
        )
        if target_video.exists() and not options.overwrite:
            return {
                "status": "failed",
                "source_name": video_path.name,
                "message": "Target video already exists",
            }
        if block_sidecar_conflicts and not options.overwrite:
            sidecar_conflicts = [
                item["target_name"]
                for item in self._sidecar_plan(
                    video_path,
                    target_dir,
                    target_video.name,
                    options.rename_style,
                )
                if item["conflict"]
            ]
            if sidecar_conflicts:
                return {
                    "status": "failed",
                    "source_name": video_path.name,
                    "message": "Target sidecar already exists",
                }

        manifest_ref = manifest_ref or operation_manifest_store.create(root, video_path)
        target_dir.mkdir(parents=True, exist_ok=True)
        moved_sidecars, sidecar_moves = self._move_sidecars(
            video_path,
            target_dir,
            target_video.name,
            options.rename_style,
            options.overwrite,
        )
        shutil.move(str(video_path), str(target_video))
        operation_manifest_store.finalize(
            manifest_ref,
            target=target_video,
            sidecars=sidecar_moves,
        )

        from app.services.library_sync import library_sync_service

        film = library_sync_service.scan_folder(
            target_dir,
            command_id=command_id,
            correlation_id=command_id,
        )
        if not film:
            operation_manifest_store.restore(manifest_ref)
            return {
                "status": "failed",
                "source_name": video_path.name,
                "message": "Moved video but scan failed",
                "sidecar_count": len(moved_sidecars),
            }

        scrape_result = metadata_scraper.scrape_film(
            film["id"],
            ScrapeOptions(
                mode="manual",
                tmdb_id=candidate.tmdb_id,
                language=options.language,
                artwork_language=options.artwork_language,
                overwrite=options.overwrite,
                write_nfo=options.write_nfo,
                download_artwork=options.download_artwork,
            ),
            command_id=command_id,
            correlation_id=command_id,
        )

        snapshot_id = library_manager.record_file_organization(
            film["id"],
            film["primary_item"]["id"],
            manifest_ref,
            command_id=command_id,
            tmdb_id=candidate.tmdb_id,
            sidecar_count=len(moved_sidecars),
            scrape_status=scrape_result.status,
        )
        return {
            "status": "success",
            "source_name": video_path.name,
            "target_name": target_video.name,
            "film_id": film["id"],
            "library_item_id": film["primary_item"]["id"],
            "tmdb_id": candidate.tmdb_id,
            "score": candidate.score,
            "scrape_status": scrape_result.status,
            "sidecar_count": len(moved_sidecars),
            "manifest_ref": manifest_ref,
            "snapshot_id": snapshot_id,
        }

    def _root_videos(self, root: Path) -> list[Path]:
        return self._videos_in_directory(root)

    def _videos_in_directory(self, directory: Path) -> list[Path]:
        videos = []
        try:
            entries = directory.iterdir()
            for path in entries:
                try:
                    is_video_file = path.is_file() and path.suffix.lower() in self.video_extensions
                except OSError:
                    continue
                if is_video_file:
                    videos.append(path)
        except OSError as exc:
            reason = exc.strerror or str(exc)
            raise PermissionError(f"Cannot read media directory: {directory}: {reason}") from exc
        return sorted(videos, key=lambda path: path.name.lower())

    def _is_usable_root_video(self, path: Path, root: Path) -> bool:
        if path.parent.resolve() != root:
            return False
        return self._is_stable_video(path)

    def _is_usable_pending_video(self, path: Path, root: Path) -> bool:
        allowed_parents = {root.resolve(), (root / "inbox").resolve()}
        if path.parent.resolve() not in allowed_parents:
            return False
        return self._is_stable_video(path)

    def _is_stable_video(self, path: Path) -> bool:
        if path.suffix.lower() not in self.video_extensions:
            return False
        lower_name = path.name.lower()
        if lower_name.endswith(self.ignored_suffixes):
            return False
        try:
            stat = path.stat()
        except OSError:
            return False
        if stat.st_size <= 0:
            return False
        stable_seconds = get_media_file_stable_seconds()
        return stable_seconds <= 0 or stat.st_mtime <= time.time() - stable_seconds

    def _video_view(
        self,
        path: Path,
        root: Path,
        *,
        source_location: str,
        include_absolute_path: bool = False,
    ) -> dict | None:
        lower_name = path.name.lower()
        if lower_name.endswith(self.ignored_suffixes):
            return None
        try:
            stat = path.stat()
        except OSError:
            return None
        if stat.st_size <= 0:
            return None
        parsed_title, parsed_year = parse_title_year(path.name)
        stable = self._is_usable_pending_video(path, root)
        try:
            source_path = path.resolve().relative_to(root).as_posix()
        except ValueError:
            return None
        view = {
            "source_path": source_path,
            "source_location": source_location,
            "filename": path.name,
            "size": stat.st_size,
            "mtime": stat.st_mtime,
            "stable": stable,
            "parsed_title": parsed_title,
            "parsed_year": parsed_year,
            "status": "needs_organize" if stable else "waiting_for_stability",
        }
        if include_absolute_path:
            view["path"] = str(path.resolve())
        return view

    def _resolve_candidate_source(self, root: Path, source_path: str) -> Path:
        if not source_path or Path(source_path).is_absolute():
            raise ValueError("Organization source path must be relative")
        source = (root / source_path).resolve()
        allowed_parents = {root.resolve(), (root / "inbox").resolve()}
        if source.parent not in allowed_parents:
            raise ValueError("Organization source path is outside the pending-file locations")
        try:
            source.relative_to(root)
        except ValueError as exc:
            raise ValueError("Organization source path escapes the media root") from exc
        if not source.exists() or not source.is_file():
            raise FileNotFoundError("Organization source video was not found")
        if source.suffix.lower() not in self.video_extensions:
            raise ValueError("Organization source is not a supported video")
        return source

    def _target_dir(self, root: Path, title: str, year: int) -> Path:
        base = self._safe_name(f"{title} ({year})" if year else title)
        return root / (base or "Unknown Movie")

    def _target_video_name(self, source: Path, title: str, year: int, style: str) -> str:
        if style == "title_year":
            base = self._safe_name(f"{title} ({year})" if year else title)
            return f"{base or source.stem}{source.suffix}"
        return source.name

    def _sidecar_plan(
        self,
        source: Path,
        target_dir: Path,
        target_video_name: str,
        rename_style: str,
    ) -> list[dict]:
        plans = []
        target_stem = Path(target_video_name).stem
        for sidecar in sorted(source.parent.glob(f"{source.stem}.*"), key=lambda path: path.name.lower()):
            if sidecar == source or sidecar.suffix.lower() not in self.sidecar_extensions:
                continue
            suffix = sidecar.name[len(source.stem):]
            target_name = f"{target_stem}{suffix}" if rename_style == "title_year" else sidecar.name
            target = target_dir / target_name
            plans.append({
                "source": sidecar,
                "target": target,
                "source_name": sidecar.name,
                "target_name": target.name,
                "conflict": target.exists(),
            })
        return plans

    def _move_sidecars(
        self,
        source: Path,
        target_dir: Path,
        target_video_name: str,
        rename_style: str,
        overwrite: bool,
    ) -> tuple[list[str], list[dict]]:
        moved = []
        sidecar_moves = []
        for item in self._sidecar_plan(source, target_dir, target_video_name, rename_style):
            sidecar = item["source"]
            target = item["target"]
            if target.exists() and not overwrite:
                continue
            shutil.move(str(sidecar), str(target))
            moved.append(target.name)
            sidecar_moves.append({
                "source": str(sidecar),
                "target": str(target),
            })
        return moved, sidecar_moves

    def _new_command_id(self, operation: str) -> str:
        return f"{operation}_{uuid4().hex}"

    def _safe_name(self, value: str) -> str:
        cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', " ", value)
        cleaned = re.sub(r"\s+", " ", cleaned).strip().rstrip(".")
        return cleaned[:180]

    def _release_year(self, release_date: Optional[str]) -> int:
        if not release_date:
            return 0
        try:
            return int(str(release_date).split("-", 1)[0])
        except ValueError:
            return 0

    def _set_status(self, **updates):
        with self._lock:
            self._status.update(updates)


root_video_organizer = RootVideoOrganizer()
