from datetime import datetime, timezone
from threading import Lock
from typing import Optional

from app.services.event_bus import library_event_bus
from app.services.event_store import event_store
from app.services.external_scores.tspdt import TSPDTDataset
from app.services.library import library_manager


EXTERNAL_SCORE_EVENT_FIELDS = (
    "external_scores",
    "external_scores_updated_at",
    "external_scores_error",
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ExternalScoreService:
    def __init__(self, tspdt: Optional[TSPDTDataset] = None):
        self.tspdt = tspdt or TSPDTDataset()
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

    def refresh_movie(self, movie_id: str, force: bool = False) -> dict:
        movie = library_manager.get_movie(movie_id)
        if not movie:
            raise LookupError("Movie not found")

        target_movie, updated_sources, skipped_sources = self._refresh_tspdt(movie)
        if target_movie and updated_sources:
            score_changes = self._field_changes(movie, target_movie, EXTERNAL_SCORE_EVENT_FIELDS)
            _, projected = event_store.append_and_project(
                "ExternalScoresRefreshed",
                "movie",
                movie_id,
                {
                    "movie_id": movie_id,
                    "updated_sources": updated_sources,
                    "skipped_sources": skipped_sources,
                    "force": force,
                    **score_changes,
                },
            )
            if not projected:
                raise RuntimeError("External scores event could not be projected")
            library_event_bus.publish_library_changed("external_scores_updated", movie_id=movie_id)
            return {
                "status": "success",
                "movie_id": movie_id,
                "movie": projected,
                "updated_sources": updated_sources,
                "skipped_sources": skipped_sources,
            }

        return {
            "status": "skipped",
            "movie_id": movie_id,
            "movie": target_movie or movie,
            "updated_sources": [],
            "skipped_sources": skipped_sources,
        }

    def refresh_library(self, force: bool = False) -> dict:
        started_at = utc_now_iso()
        self._set_status(state="running", last_started_at=started_at, last_error=None)
        result = {"processed": 0, "updated": 0, "skipped": 0, "failed": 0}

        try:
            for movie in library_manager.get_movies():
                if movie.get("library_status") in {"missing", "ignored", "reverted"}:
                    continue
                result["processed"] += 1
                try:
                    refresh_result = self.refresh_movie(movie["id"], force=force)
                    if refresh_result["updated_sources"]:
                        result["updated"] += 1
                    else:
                        result["skipped"] += 1
                except Exception:
                    result["failed"] += 1

            self._set_status(
                state="idle",
                last_finished_at=utc_now_iso(),
                last_result=result,
            )
            library_event_bus.publish_library_changed("external_scores_batch_updated", result=result)
            return result
        except Exception as exc:
            self._set_status(
                state="error",
                last_finished_at=utc_now_iso(),
                last_error=str(exc),
            )
            raise

    def _refresh_tspdt(self, movie: dict) -> tuple[Optional[dict], list[str], list[str]]:
        try:
            match = self.tspdt.match_movie(movie)
        except Exception as exc:
            stored = library_manager.upsert_movie(
                {
                    **movie,
                    "external_scores_error": str(exc),
                    "external_scores_updated_at": utc_now_iso(),
                },
                preserve_id=movie["id"],
            )
            event_store.safe_append(
                "ExternalScoresRefreshFailed",
                "movie",
                movie["id"],
                {"movie_id": movie["id"], "source": "tspdt", "message": str(exc)},
            )
            return stored, [], ["tspdt"]

        if not match:
            return None, [], ["tspdt"]

        score = {
            "source": self.tspdt.source,
            "label": self.tspdt.label,
            "kind": "rank",
            "rank": match.entry.rank,
            "previous_rank": match.entry.previous_rank,
            "list_name": self.tspdt.list_name,
            "edition": self.tspdt.edition,
            "title": match.entry.title,
            "year": match.entry.year,
            "director": match.entry.director,
            "matched_by": match.matched_by,
            "confidence": match.confidence,
            "fetched_at": utc_now_iso(),
        }
        scores = self._replace_source(movie.get("external_scores") or [], score)
        return {
            **movie,
            "external_scores": scores,
            "external_scores_updated_at": utc_now_iso(),
            "external_scores_error": None,
        }, ["tspdt"], []

    def _replace_source(self, scores: list[dict], score: dict) -> list[dict]:
        return [
            *[item for item in scores if item.get("source") != score["source"]],
            score,
        ]

    def _field_changes(self, previous: dict, current: dict, fields: tuple[str, ...]) -> dict:
        changed_fields = []
        previous_values = {}
        current_values = {}
        for field in fields:
            previous_value = previous.get(field)
            current_value = current.get(field)
            previous_values[field] = previous_value
            current_values[field] = current_value
            if previous_value != current_value:
                changed_fields.append(field)
        return {
            "changed_fields": changed_fields,
            "previous": previous_values,
            "current": current_values,
        }

    def _set_status(self, **updates):
        with self._lock:
            self._status.update(updates)


external_score_service = ExternalScoreService()
