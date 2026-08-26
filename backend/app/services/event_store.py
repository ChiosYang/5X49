import logging
from typing import Optional

from sqlmodel import Session, select

from app.database import engine
from app.canonical_models import AnalysisRun, Assertion, Film, LibraryItem, OperationSnapshot, Viewing
from app.models import EventRecord


logger = logging.getLogger("event_store")


class EventStore:
    """Persistent Canonical audit event store."""

    def append_in_session(
        self,
        session: Session,
        event_type: str,
        aggregate_type: str,
        aggregate_id: Optional[str] = None,
        payload: Optional[dict] = None,
        *,
        actor_type: str = "system",
        actor_id: Optional[str] = None,
        command_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        causation_id: Optional[str] = None,
        context: Optional[dict] = None,
    ) -> EventRecord:
        event = EventRecord(
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            type=event_type,
            actor_type=actor_type,
            actor_id=actor_id,
            command_id=command_id,
            correlation_id=correlation_id,
            causation_id=causation_id,
            payload=payload or {},
            context=context or {},
        )
        session.add(event)
        session.flush()
        return event

    def append(
        self,
        event_type: str,
        aggregate_type: str,
        aggregate_id: Optional[str] = None,
        payload: Optional[dict] = None,
        *,
        actor_type: str = "system",
        actor_id: Optional[str] = None,
        command_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        causation_id: Optional[str] = None,
        context: Optional[dict] = None,
    ) -> dict:
        with Session(engine) as session:
            event = self.append_in_session(
                session,
                event_type,
                aggregate_type,
                aggregate_id,
                payload,
                actor_type=actor_type,
                actor_id=actor_id,
                command_id=command_id,
                correlation_id=correlation_id,
                causation_id=causation_id,
                context=context,
            )
            session.commit()
            session.refresh(event)
            return event.model_dump()

    def safe_append(self, *args, **kwargs) -> Optional[dict]:
        try:
            return self.append(*args, **kwargs)
        except Exception:
            logger.exception("Failed to append audit event")
            return None

    def list(
        self,
        *,
        aggregate_type: Optional[str] = None,
        aggregate_id: Optional[str] = None,
        event_type: Optional[str] = None,
        command_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict]:
        limit = max(1, min(limit, 500))
        statement = select(EventRecord)
        if aggregate_type:
            statement = statement.where(EventRecord.aggregate_type == aggregate_type)
        if aggregate_id:
            statement = statement.where(EventRecord.aggregate_id == aggregate_id)
        if event_type:
            statement = statement.where(EventRecord.type == event_type)
        if command_id:
            statement = statement.where(EventRecord.command_id == command_id)
        if correlation_id:
            statement = statement.where(EventRecord.correlation_id == correlation_id)
        statement = statement.order_by(EventRecord.occurred_at.desc(), EventRecord.id.desc()).limit(limit)

        with Session(engine) as session:
            events = session.exec(statement).all()
            snapshots = {
                snapshot.event_id: snapshot.id
                for snapshot in session.exec(
                    select(OperationSnapshot).where(
                        OperationSnapshot.event_id.in_([event.id for event in events])
                    )
                ).all()
            } if events else {}
            return [
                {
                    **event.model_dump(),
                    **self._display_context(session, event),
                    "operation_snapshot_id": snapshots.get(event.id),
                }
                for event in events
            ]

    @staticmethod
    def _display_context(session: Session, event: EventRecord) -> dict:
        film_id: str | None = None
        if event.aggregate_type == "film":
            film_id = event.aggregate_id
        elif event.aggregate_type == "library_item" and event.aggregate_id:
            item = session.get(LibraryItem, event.aggregate_id)
            film_id = item.film_id if item else None
        elif event.aggregate_type == "analysis_run" and event.aggregate_id:
            run = session.get(AnalysisRun, event.aggregate_id)
            film_id = run.film_id if run else None
        elif event.aggregate_type == "viewing" and event.aggregate_id:
            viewing = session.get(Viewing, event.aggregate_id)
            film_id = viewing.film_id if viewing else None
        elif event.aggregate_type == "assertion" and event.aggregate_id:
            assertion = session.get(Assertion, event.aggregate_id)
            if assertion and session.get(Film, assertion.subject_entity_id):
                film_id = assertion.subject_entity_id
        film = session.get(Film, film_id) if film_id else None
        return {
            "film_id": film_id,
            "display_title": film.canonical_title if film else None,
        }


event_store = EventStore()
