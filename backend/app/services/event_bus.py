import asyncio
import json
from datetime import datetime, timezone
from threading import Lock
from typing import Optional

from fastapi import Request


class LibraryEventBus:
    """Thread-safe SSE broadcaster for library invalidation events."""

    def __init__(self):
        self._lock = Lock()
        self._subscribers: dict[asyncio.Queue[str], asyncio.AbstractEventLoop] = {}

    def publish(self, event: str, data: Optional[dict] = None):
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **(data or {}),
        }
        message = self._format_event(event, payload)

        with self._lock:
            subscribers = list(self._subscribers.items())

        for subscriber, loop in subscribers:
            try:
                loop.call_soon_threadsafe(self._enqueue, subscriber, message)
            except RuntimeError:
                # A disconnected subscriber's event loop may already be closed.
                pass

    @staticmethod
    def _enqueue(subscriber: asyncio.Queue[str], message: str):
        # Queue operations stay on the subscriber's loop, including drop-oldest.
        if subscriber.full():
            subscriber.get_nowait()
        subscriber.put_nowait(message)

    def publish_library_changed(self, reason: str, **payload):
        self.publish("library_changed", {"reason": reason, **payload})

    async def subscribe(self, request: Request):
        subscriber: asyncio.Queue[str] = asyncio.Queue(maxsize=20)
        with self._lock:
            self._subscribers[subscriber] = asyncio.get_running_loop()

        try:
            yield self._format_event("connected", {})
            while True:
                if await request.is_disconnected():
                    break

                try:
                    # Cancellation must not leave a blocking executor worker
                    # behind for every SSE connection closed during navigation.
                    message = await asyncio.wait_for(subscriber.get(), timeout=25)
                except TimeoutError:
                    yield self._format_event("heartbeat", {})
                    continue

                yield message
        finally:
            with self._lock:
                self._subscribers.pop(subscriber, None)

    def _format_event(self, event: str, data: dict) -> str:
        return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


library_event_bus = LibraryEventBus()
