from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path
from uuid import uuid4


MANIFEST_SCHEMA_VERSION = "file-operation-manifest.v1"
_REF_PATTERN = re.compile(r"^manifest_[0-9a-f]{32}$")


class OperationManifestError(RuntimeError):
    pass


class OperationManifestStore:
    def __init__(self, root: Path | None = None):
        configured = Path(os.getenv("OPERATION_MANIFEST_DIR", "data/operation-manifests"))
        self.root = (root or configured).resolve()

    def create(self, media_root: Path, source: Path) -> str:
        media_root = media_root.resolve()
        source = source.resolve()
        self._require_within(source, media_root)
        if not source.is_file():
            raise OperationManifestError("Source file is unavailable")
        return self._create_entry(media_root, source, "file_operation")

    def create_path_reference(
        self,
        media_root: Path,
        source: Path,
        *,
        allow_missing: bool = False,
    ) -> str:
        media_root = media_root.resolve()
        source = source.resolve()
        self._require_within(source, media_root)
        if not allow_missing and not source.exists():
            raise OperationManifestError("Referenced path is unavailable")
        return self._create_entry(media_root, source, "path_reference")

    def resolve_path(self, reference: str) -> tuple[Path, Path]:
        manifest = self.load(reference)
        if manifest.get("entry_kind") not in {"path_reference", "file_operation"}:
            raise OperationManifestError("Operation manifest does not reference a path")
        return Path(manifest["media_root"]), Path(manifest["source"])

    def _create_entry(self, media_root: Path, source: Path, entry_kind: str) -> str:
        reference = f"manifest_{uuid4().hex}"
        self._write(
            reference,
            {
                "schema_version": MANIFEST_SCHEMA_VERSION,
                "reference": reference,
                "entry_kind": entry_kind,
                "media_root": str(media_root),
                "source": str(source),
                "target": None,
                "sidecars": [],
            },
        )
        return reference

    def finalize(
        self,
        reference: str,
        *,
        target: Path,
        sidecars: list[dict[str, str]],
    ) -> None:
        manifest = self.load(reference)
        if manifest.get("entry_kind") != "file_operation":
            raise OperationManifestError("Operation manifest is not a file operation")
        root = Path(manifest["media_root"]).resolve()
        target = target.resolve()
        self._require_within(target, root)
        sanitized_sidecars = []
        for item in sidecars:
            source = Path(item["source"]).resolve()
            sidecar_target = Path(item["target"]).resolve()
            self._require_within(source, root)
            self._require_within(sidecar_target, root)
            sanitized_sidecars.append({"source": str(source), "target": str(sidecar_target)})
        manifest["target"] = str(target)
        manifest["sidecars"] = sanitized_sidecars
        self._write(reference, manifest)

    def load(self, reference: str) -> dict:
        path = self._path(reference)
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise OperationManifestError("Operation manifest is unavailable") from exc
        if value.get("schema_version") != MANIFEST_SCHEMA_VERSION or value.get("reference") != reference:
            raise OperationManifestError("Operation manifest contract is invalid")
        root = Path(value.get("media_root") or "").resolve()
        source = Path(value.get("source") or "").resolve()
        self._require_within(source, root)
        target_value = value.get("target")
        if target_value:
            self._require_within(Path(target_value).resolve(), root)
        return value

    def state(self, reference: str) -> str:
        manifest = self.load(reference)
        source = Path(manifest["source"])
        target_value = manifest.get("target")
        if not target_value:
            return "source" if source.is_file() else "invalid"
        target = Path(target_value)
        if source.is_file() and not target.exists():
            return "source"
        if target.is_file() and not source.exists():
            return "target"
        return "invalid"

    def restore(self, reference: str) -> None:
        manifest = self.load(reference)
        source = Path(manifest["source"])
        target = Path(manifest.get("target") or "")
        if self.state(reference) != "target":
            raise OperationManifestError("Organized files no longer match the manifest")
        moves = [
            (Path(item["target"]), Path(item["source"]))
            for item in manifest.get("sidecars", [])
        ]
        moves.append((target, source))
        for current, destination in moves:
            if destination.exists() or not current.is_file():
                raise OperationManifestError("A file restore destination is no longer safe")
        for current, destination in moves:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(current), str(destination))

    def _write(self, reference: str, value: dict) -> None:
        path = self._path(reference)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        temporary.replace(path)

    def _path(self, reference: str) -> Path:
        if not _REF_PATTERN.fullmatch(reference or ""):
            raise OperationManifestError("Operation manifest reference is invalid")
        return self.root / f"{reference}.json"

    @staticmethod
    def _require_within(path: Path, root: Path) -> None:
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise OperationManifestError("Operation path escapes the media root") from exc


operation_manifest_store = OperationManifestStore()


__all__ = [
    "MANIFEST_SCHEMA_VERSION",
    "OperationManifestError",
    "OperationManifestStore",
    "operation_manifest_store",
]
