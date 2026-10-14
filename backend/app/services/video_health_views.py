"""Public inspection views: DB-only summary reads; bounded on-demand file detail."""
from pathlib import Path
from datetime import datetime, timezone
from sqlmodel import Session, select
from app import database
from app.models import Film, LibraryItem, MediaAsset
from app.health_models import VideoHealth
from app.services.settings import get_media_dirs
from app.services.video_health import video_health, asset_snapshot


def records():
    roots = [Path(root) for root in get_media_dirs()]
    with Session(database.engine) as session:
        assets = session.exec(select(MediaAsset, LibraryItem, Film)
            .join(LibraryItem, MediaAsset.library_item_id == LibraryItem.id)
            .join(Film, LibraryItem.film_id == Film.id)
            .where(MediaAsset.asset_kind.in_(["video", "video_part"]))
            .where(MediaAsset.availability_status == "present")
            .where(LibraryItem.availability_status == "available")).all()
        # Query only the latest receipt per asset; lifetime history is not loaded
        # into every navigation badge or summary poll.
        from sqlalchemy.orm import aliased
        newer = aliased(VideoHealth)
        latest_id = select(newer.id).where(newer.asset_id == VideoHealth.asset_id).order_by(
            newer.observed_at.desc(), newer.id.desc()).limit(1).scalar_subquery()
        history = session.exec(select(VideoHealth).where(VideoHealth.id == latest_id)).all()
        latest = {row.asset_id: row for row in history}
        result = []
        for asset, item, film in assets:
            # Do not stat every HDD on polling reads. Live evidence is sampled
            # only by the idle worker or an explicitly opened detail.
            if not any(Path(asset.locator).is_relative_to(root) for root in roots):
                continue
            row = latest.get(asset.id)
            current = bool(row and row.asset_snapshot == asset_snapshot(asset))
            result.append({"id": row.id if row else None, "asset_id": asset.id,
                "film_id": film.id, "library_item_id": item.id, "title": film.canonical_title,
                "filename": Path(asset.locator).name, "part": asset.asset_kind == "video_part",
                "status": row.status if current else "unchecked", "current": current,
                "container_status": row.container_status if current else "unchecked",
                "decode_status": row.status if current and row.container_status == "passed" else "unchecked",
                "version_key": row.version_key if row else None, "version": row.version if row else None,
                "checked_at": row.checked_at if row else None,
                "passed_at": row.passed_at if row else None,
                "decoded_seconds": row.decoded_seconds if current else 0,
                "duration_seconds": row.duration_seconds if current else None,
                "error_code": row.error_code if current else None,
                "error_summary": row.error_summary if current else None,
                "error_position_seconds": None, "position_kind": "unknown",
                "unread": bool(current and row.status == "abnormal" and row.notified and not row.acknowledged)})
        return sorted(result, key=lambda entry: (entry["status"] != "abnormal", entry["title"] or "", entry["asset_id"]))


def status():
    items = records()
    counts = {state: sum(item["status"] == state for item in items)
              for state in ["unchecked", "queued", "checking", "passed", "abnormal", "incomplete", "unsupported"]}
    with Session(database.engine) as session:
        runtime = video_health.runtime(session)
        active = session.get(VideoHealth, video_health.active_id) if video_health.active_id else None
    today = datetime.fromtimestamp(video_health.clock(), timezone.utc).date().isoformat()
    return {"config": video_health.config(), "schedule_timezone": "UTC", "reason": video_health.reason,
            "counts": counts, "total": len(items), "unread": sum(item["unread"] for item in items),
            "load": video_health.load, "active_id": video_health.active_id,
            "budget_day": today, "used_seconds": runtime["used_seconds"] if runtime["day"] == today else 0,
            "active_progress": {"decoded_seconds": active.decoded_seconds, "duration_seconds": active.duration_seconds} if active else None,
            "queue_sweep_pending": runtime["sweep"], "manual_active": runtime["manual"]}


def detail(identifier):
    with Session(database.engine) as session:
        row = session.get(VideoHealth, identifier)
        if not row:
            raise LookupError("Inspection not found")
        asset = session.get(MediaAsset, row.asset_id)
        item = session.get(LibraryItem, asset.library_item_id) if asset else None
        film = session.get(Film, item.film_id) if item else None
        try:
            video_health._context(session, row)
            current, unavailable = True, None
        except (OSError, ValueError, RuntimeError) as exc:
            current, unavailable = False, video_health._access_code(exc)
        return {"id": row.id, "asset_id": row.asset_id, "film_id": film.id if film else None,
                "library_item_id": item.id if item else None, "title": film.canonical_title if film else None,
                "filename": Path(asset.locator).name if asset else None, "status": row.status,
                "container_status": row.container_status, "current": current,
                "decode_status": row.status if row.container_status == "passed" else "unchecked",
                "unavailable_reason": unavailable, "version_key": row.version_key, "version": row.version,
                "checked_at": row.checked_at, "decoded_seconds": row.decoded_seconds,
                "passed_at": row.passed_at,
                "duration_seconds": row.duration_seconds, "error_code": row.error_code,
                "error_summary": row.error_summary, "error_position_seconds": None,
                "position_kind": "unknown", "attempts": row.attempts}
