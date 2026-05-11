import asyncio
import json
from datetime import datetime, timezone
from queue import Empty, Queue
from threading import Lock
from typing import Optional

from fastapi import Request


class LibraryEventBus:
    """Thread-safe SSE broadcaster for library invalidation events."""

    def __init__(self):
        self._lock = Lock()
        self._subscribers: set[Queue[str]] = set()

    def publish(self, event: str, data: Optional[dict] = None):
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **(data or {}),
        }
        message = self._format_event(event, payload)

        with self._lock:
            subscribers = list(self._subscribers)

        for subscriber in subscribers:
            if subscriber.full():
                try:
                    subscriber.get_nowait()
                except Empty:
                    pass
            subscriber.put_nowait(message)

    def publish_library_changed(self, reason: str, **payload):
        self.publish("library_changed", {"reason": reason, **payload})

    async def subscribe(self, request: Request):
        subscriber: Queue[str] = Queue(maxsize=20)
        with self._lock:
            self._subscribers.add(subscriber)

        try:
            yield self._format_event("connected", {})
            while True:
                if await request.is_disconnected():
                    break

                try:
                    message = await asyncio.to_thread(subscriber.get, True, 25)
                except Empty:
                    yield self._format_event("heartbeat", {})
                    continue

                yield message
        finally:
            with self._lock:
                self._subscribers.discard(subscriber)

    def _format_event(self, event: str, data: dict) -> str:
        return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


library_event_bus = LibraryEventBus()
