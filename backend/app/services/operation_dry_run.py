from collections import Counter
import os
from pathlib import Path
from typing import Optional

from sqlmodel import Session, select

from app.database import engine
from app.models import EventRecord
from app.services.settings import get_media_dir


SIDE_EFFECT_EVENT_TYPES = {
    "ArtworkDownloaded",
    "ArtworkSelected",
    "MetadataMatched",
    "MovieFileObserved",
    "MovieMetadataParsedFromNfo",
    "NfoWritten",
    "RootVideoMoved",
    "RootVideoOrganized",
}

FIELD_RECOVERY_EVENT_TYPES = {
    "ArtworkSelected",
    "MetadataMatched",
}


class OperationDryRun:
    """Read-only consistency check for one correlated operation."""

    def run(
        self,
        *,
        correlation_id: Optional[str] = None,
        command_id: Optional[str] = None,
        limit: int = 500,
    ) -> dict:
        if not correlation_id and not command_id:
            raise ValueError("correlation_id or command_id is required")

        limit = max(1, min(limit, 500))
        events = self._events(correlation_id=correlation_id, command_id=command_id, limit=limit)
        payload_issues = self._payload_issues(events)
        field_recovery = self._field_recovery(events)
        checks = {
            "poster_restore": self._poster_restore_check(events),
            "nfo_writer_trace": self._nfo_writer_trace_check(events),
            "root_move_reverse": self._root_move_reverse_check(events),
            "scrape_side_effects": self._scrape_side_effects_check(events),
        }
        unsafe_actions = self._unsafe_actions(checks)
        missing_payload = self._missing_payload(payload_issues, checks)

        return {
            "dry_run": True,
            "operation_id": correlation_id or command_id,
            "correlation_id": correlation_id,
            "command_id": command_id,
            "status": self._overall_status(checks, missing_payload, unsafe_actions),
            "events_analyzed": len(events),
            "event_types": dict(Counter(event.type for event in events)),
            "can_restore_poster": checks["poster_restore"]["can"],
            "can_trace_nfo_writer": checks["nfo_writer_trace"]["can"],
            "can_reverse_root_move": checks["root_move_reverse"]["can"],
            "can_list_scrape_side_effects": checks["scrape_side_effects"]["can"],
            "checks": checks,
            "side_effects": self._side_effects(events),
            "recoverable_fields": field_recovery,
            "missing_payload": missing_payload,
            "unsafe_actions": unsafe_actions,
            "events": [self._event_summary(event) for event in events],
        }

    def _events(
        self,
        *,
        correlation_id: Optional[str],
        command_id: Optional[str],
        limit: int,
    ) -> list[EventRecord]:
        statement = select(EventRecord)
        if correlation_id:
            statement = statement.where(EventRecord.correlation_id == correlation_id)
        else:
            statement = statement.where(EventRecord.command_id == command_id)
        statement = statement.order_by(EventRecord.occurred_at, EventRecord.id).limit(limit)
        with Session(engine) as session:
            return list(session.exec(statement).all())

    def _payload_issues(self, events: list[EventRecord]) -> list[dict]:
        issues = []
        required_fields = {
            "ArtworkDownloaded": ("asset_type", "destination", "before", "after"),
            "ArtworkSelected": ("changed_fields", "previous", "current"),
            "MetadataMatched": ("changed_fields", "previous", "current"),
            "NfoWritten": ("action", "path", "before", "after"),
            "RootVideoMoved": ("source_path", "target_path", "source", "target"),
        }
        for event in events:
            payload = event.payload or {}
            for field in required_fields.get(event.type, ()):
                if field not in payload:
                    issues.append({
                        "event_id": event.id,
                        "type": event.type,
                        "field": field,
                        "reason": "Required payload field is missing",
                    })
        return issues

    def _field_recovery(self, events: list[EventRecord]) -> list[dict]:
        fields = []
        for event in events:
            if event.type not in FIELD_RECOVERY_EVENT_TYPES:
                continue
            payload = event.payload or {}
            previous = payload.get("previous")
            current = payload.get("current")
            changed_fields = payload.get("changed_fields")
            if not isinstance(previous, dict) or not isinstance(current, dict) or not isinstance(changed_fields, list):
                continue
            for field in changed_fields:
                fields.append({
                    "event_id": event.id,
                    "type": event.type,
                    "field": field,
                    "previous": previous.get(field),
                    "current": current.get(field),
                    "can_restore_value": field in previous,
                })
        return fields

    def _poster_restore_check(self, events: list[EventRecord]) -> dict:
        candidates = []
        for event in events:
            if event.type not in FIELD_RECOVERY_EVENT_TYPES:
                continue
            payload = event.payload or {}
            previous = payload.get("previous")
            current = payload.get("current")
            if not isinstance(previous, dict) or not isinstance(current, dict):
                continue
            if any(field in previous or field in current for field in ("poster_path", "poster_local")):
                candidates.append((event, previous, current))

        if not candidates:
            return self._check("not_applicable", False, "No poster-changing event was found")

        event, previous, current = candidates[-1]
        previous_path = previous.get("poster_path")
        previous_local = previous.get("poster_local")
        current_local = current.get("poster_local")
        if not previous_path and not previous_local:
            return self._check(
                "unsafe",
                False,
                "Previous poster selection is not present in the event payload",
                event_id=event.id,
                missing_payload=["previous.poster_path", "previous.poster_local"],
            )

        previous_file = self._resolve_media_path(previous_local) if isinstance(previous_local, str) else None
        previous_file_exists = bool(previous_file and previous_file.exists())
        same_local_file = bool(previous_local and current_local and previous_local == current_local)
        if previous_file_exists and not same_local_file:
            return self._check(
                "safe",
                True,
                "Previous poster file still exists at a distinct local path",
                event_id=event.id,
                details={"previous_file": str(previous_file)},
            )

        return self._check(
            "partial",
            False,
            "Previous poster selection is known, but the old image file is not safely restorable from local state",
            event_id=event.id,
            details={
                "previous_poster_path": previous_path,
                "previous_poster_local": previous_local,
                "current_poster_local": current_local,
                "previous_file_exists": previous_file_exists,
                "same_local_file": same_local_file,
            },
            unsafe_actions=["Old poster file content may have been overwritten and no backup path is recorded"],
        )

    def _nfo_writer_trace_check(self, events: list[EventRecord]) -> dict:
        nfo_events = [event for event in events if event.type == "NfoWritten"]
        if not nfo_events:
            return self._check("not_applicable", False, "No NFO write event was found")

        missing_operation = [
            event.id
            for event in nfo_events
            if not (event.context or {}).get("operation")
        ]
        missing_actor = [event.id for event in nfo_events if not event.actor_id]
        status = "partial" if missing_actor else "safe"
        message = "NFO writes can be traced to a system operation"
        unsafe_actions = []
        if missing_operation:
            status = "partial"
            message = "Some NFO writes are missing operation context"
        if missing_actor:
            unsafe_actions.append("NFO writes do not identify a concrete user actor")
        return self._check(
            status,
            not missing_operation,
            message,
            details={
                "nfo_events": [event.id for event in nfo_events],
                "operations": sorted({(event.context or {}).get("operation") for event in nfo_events if (event.context or {}).get("operation")}),
                "actor_type": sorted({event.actor_type for event in nfo_events if event.actor_type}),
                "missing_actor_ids": missing_actor,
            },
            unsafe_actions=unsafe_actions,
        )

    def _root_move_reverse_check(self, events: list[EventRecord]) -> dict:
        move_events = [event for event in events if event.type == "RootVideoMoved"]
        if not move_events:
            return self._check("not_applicable", False, "No root video move event was found")

        event = move_events[-1]
        payload = event.payload or {}
        source_path = payload.get("source_path")
        target_path = payload.get("target_path")
        if not isinstance(source_path, str) or not isinstance(target_path, str):
            return self._check(
                "unsafe",
                False,
                "Root move event is missing source or target path",
                event_id=event.id,
                missing_payload=["source_path", "target_path"],
            )

        source = Path(source_path)
        target = Path(target_path)
        target_exists = target.exists()
        source_available = not source.exists()
        sidecar_checks = self._sidecar_reverse_checks(payload.get("sidecars"))
        sidecars_reversible = all(item["target_exists"] and item["source_available"] for item in sidecar_checks)
        can_reverse = target_exists and source_available and sidecars_reversible
        return self._check(
            "safe" if can_reverse else "unsafe",
            can_reverse,
            "Root video move can be reversed" if can_reverse else "Root video move cannot be safely reversed from current filesystem state",
            event_id=event.id,
            details={
                "source_path": source_path,
                "target_path": target_path,
                "target_exists": target_exists,
                "source_available": source_available,
                "sidecars": sidecar_checks,
            },
            unsafe_actions=[] if can_reverse else ["Reverse move would require filesystem conflict handling or a missing target file"],
        )

    def _scrape_side_effects_check(self, events: list[EventRecord]) -> dict:
        side_effects = self._side_effects(events)
        if not side_effects:
            return self._check("unknown", False, "No supported side-effect events were found")
        return self._check(
            "safe",
            True,
            "Side effects can be listed from the operation event chain",
            details={"side_effect_count": len(side_effects)},
        )

    def _side_effects(self, events: list[EventRecord]) -> list[dict]:
        side_effects = []
        for event in events:
            if event.type not in SIDE_EFFECT_EVENT_TYPES:
                continue
            payload = event.payload or {}
            side_effects.append({
                "event_id": event.id,
                "type": event.type,
                "aggregate_type": event.aggregate_type,
                "aggregate_id": event.aggregate_id,
                "occurred_at": event.occurred_at,
                "operation": (event.context or {}).get("operation"),
                "path": payload.get("path") or payload.get("destination") or payload.get("target_path") or payload.get("media_path"),
                "asset_type": payload.get("asset_type"),
                "action": payload.get("action"),
            })
        return side_effects

    def _sidecar_reverse_checks(self, sidecars: object) -> list[dict]:
        if not isinstance(sidecars, list):
            return []
        checks = []
        for sidecar in sidecars:
            if not isinstance(sidecar, dict):
                continue
            source_path = sidecar.get("source_path")
            target_path = sidecar.get("target_path")
            if not isinstance(source_path, str) or not isinstance(target_path, str):
                continue
            checks.append({
                "source_path": source_path,
                "target_path": target_path,
                "target_exists": Path(target_path).exists(),
                "source_available": not Path(source_path).exists(),
            })
        return checks

    def _missing_payload(self, payload_issues: list[dict], checks: dict) -> list[dict]:
        missing = list(payload_issues)
        for check in checks.values():
            for field in check.get("missing_payload", []):
                missing.append({
                    "event_id": check.get("event_id"),
                    "field": field,
                    "reason": check.get("message"),
                })
        return missing

    def _unsafe_actions(self, checks: dict) -> list[dict]:
        actions = []
        for name, check in checks.items():
            for action in check.get("unsafe_actions", []):
                actions.append({
                    "check": name,
                    "reason": action,
                    "event_id": check.get("event_id"),
                })
        return actions

    def _overall_status(self, checks: dict, missing_payload: list[dict], unsafe_actions: list[dict]) -> str:
        relevant_checks = [
            check
            for check in checks.values()
            if check["status"] != "not_applicable"
        ]
        if any(check["status"] == "unsafe" for check in relevant_checks):
            return "unsafe"
        if missing_payload or unsafe_actions or any(check["status"] in {"partial", "unknown"} for check in relevant_checks):
            return "partial"
        return "safe" if relevant_checks else "unknown"

    def _check(
        self,
        status: str,
        can: bool,
        message: str,
        *,
        event_id: Optional[str] = None,
        details: Optional[dict] = None,
        missing_payload: Optional[list[str]] = None,
        unsafe_actions: Optional[list[str]] = None,
    ) -> dict:
        return {
            "status": status,
            "can": can,
            "message": message,
            "event_id": event_id,
            "details": details or {},
            "missing_payload": missing_payload or [],
            "unsafe_actions": unsafe_actions or [],
        }

    def _event_summary(self, event: EventRecord) -> dict:
        return {
            "id": event.id,
            "type": event.type,
            "aggregate_type": event.aggregate_type,
            "aggregate_id": event.aggregate_id,
            "command_id": event.command_id,
            "correlation_id": event.correlation_id,
            "occurred_at": event.occurred_at,
            "operation": (event.context or {}).get("operation"),
        }

    def _resolve_media_path(self, value: str) -> Optional[Path]:
        if value.startswith("/media/"):
            media_dir = get_media_dir() or os.getenv("MEDIA_DIR")
            if not media_dir:
                return None
            return Path(media_dir) / value.removeprefix("/media/")
        path = Path(value)
        return path if path.is_absolute() else None


operation_dry_run = OperationDryRun()
