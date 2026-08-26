from datetime import datetime, timezone
from threading import Lock
from typing import Optional

from sqlmodel import Session, select

from app.canonical_models import ExternalScoreRefreshState, FilmExternalScore
from app.database import engine
from app.services.event_bus import library_event_bus
from app.services.event_store import event_store
from app.services.external_scores.tspdt import TSPDTDataset
from app.services.library import library_manager


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

    def refresh_film(self, film_id: str, force: bool = False) -> dict:
        film = library_manager.get_film_operation_context(film_id)
        if film is None:
            raise LookupError("Film not found")
        now = utc_now_iso()
        try:
            match = self.tspdt.match_movie(film)
        except Exception as exc:
            safe_message = type(exc).__name__
            with Session(engine) as session:
                state = self._refresh_state(session, film_id, self.tspdt.source)
                state.status = "failed"
                state.error_code = "source_refresh_failed"
                state.error_message = safe_message[:160]
                state.refreshed_at = now
                state.updated_at = now
                session.add(state)
                event_store.append_in_session(
                    session,
                    "ExternalScoresRefreshFailed",
                    "film",
                    film_id,
                    {"source": self.tspdt.source, "error_code": state.error_code},
                )
                session.commit()
            raise RuntimeError("External score refresh failed") from exc

        updated_sources: list[str] = []
        skipped_sources: list[str] = []
        with Session(engine) as session:
            state = self._refresh_state(session, film_id, self.tspdt.source)
            state.status = "succeeded"
            state.error_code = None
            state.error_message = None
            state.refreshed_at = now
            state.updated_at = now
            session.add(state)
            if match is None:
                skipped_sources.append(self.tspdt.source)
            else:
                score = session.exec(
                    select(FilmExternalScore)
                    .where(FilmExternalScore.film_id == film_id)
                    .where(FilmExternalScore.source == self.tspdt.source)
                    .where(FilmExternalScore.kind == "rank")
                    .where(FilmExternalScore.list_name == self.tspdt.list_name)
                    .where(FilmExternalScore.edition == self.tspdt.edition)
                ).first()
                if score is None:
                    score = FilmExternalScore(
                        film_id=film_id,
                        source=self.tspdt.source,
                        label=self.tspdt.label,
                        kind="rank",
                        rank=match.entry.rank,
                        previous_rank=match.entry.previous_rank,
                        list_name=self.tspdt.list_name,
                        edition=self.tspdt.edition,
                        matched_by=match.matched_by,
                        confidence=match.confidence,
                        fetched_at=now,
                    )
                else:
                    score.label = self.tspdt.label
                    score.rank = match.entry.rank
                    score.previous_rank = match.entry.previous_rank
                    score.matched_by = match.matched_by
                    score.confidence = match.confidence
                    score.fetched_at = now
                    score.updated_at = now
                session.add(score)
                updated_sources.append(self.tspdt.source)
            event_store.append_in_session(
                session,
                "ExternalScoresRefreshed",
                "film",
                film_id,
                {
                    "updated_sources": updated_sources,
                    "skipped_sources": skipped_sources,
                    "force": force,
                },
            )
            session.commit()

        result_film = library_manager.get_film(film_id)
        library_event_bus.publish_library_changed("external_scores_updated", film_id=film_id)
        return {
            "status": "success" if updated_sources else "skipped",
            "film_id": film_id,
            "film": result_film,
            "updated_sources": updated_sources,
            "skipped_sources": skipped_sources,
        }

    def refresh_library(self, force: bool = False) -> dict:
        started_at = utc_now_iso()
        self._set_status(state="running", last_started_at=started_at, last_error=None)
        result = {"processed": 0, "updated": 0, "skipped": 0, "failed": 0}
        try:
            for film in library_manager.list_films():
                result["processed"] += 1
                try:
                    refreshed = self.refresh_film(film["id"], force=force)
                    result["updated" if refreshed["updated_sources"] else "skipped"] += 1
                except Exception:
                    result["failed"] += 1
            self._set_status(state="idle", last_finished_at=utc_now_iso(), last_result=result)
            library_event_bus.publish_library_changed("external_scores_batch_updated", result=result)
            return result
        except Exception as exc:
            self._set_status(
                state="error",
                last_finished_at=utc_now_iso(),
                last_error=type(exc).__name__,
            )
            raise

    def _refresh_state(self, session: Session, film_id: str, source: str) -> ExternalScoreRefreshState:
        state = session.exec(
            select(ExternalScoreRefreshState)
            .where(ExternalScoreRefreshState.film_id == film_id)
            .where(ExternalScoreRefreshState.source == source)
        ).first()
        return state or ExternalScoreRefreshState(film_id=film_id, source=source)

    def _set_status(self, **updates):
        with self._lock:
            self._status.update(updates)


external_score_service = ExternalScoreService()
