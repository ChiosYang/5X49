import logging
from typing import Optional

from sqlmodel import Session, select

from app.database import engine
from app.models import EventRecord


logger = logging.getLogger("event_store")


class EventStore:
    """Persistent audit event store.

    Stage 1 keeps this as a sidecar audit log: existing services still update
    their current-state tables, and append semantic events best-effort.
    """

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
        statement = statement.order_by(EventRecord.occurred_at.desc(), EventRecord.id.desc()).limit(limit)

        with Session(engine) as session:
            return [event.model_dump() for event in session.exec(statement).all()]


event_store = EventStore()
