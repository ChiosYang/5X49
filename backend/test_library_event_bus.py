import asyncio
import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Event, Thread

from app.services.event_bus import LibraryEventBus


class ConnectedRequest:
    async def is_disconnected(self):
        return False


def payload(message):
    return json.loads(message.split("data: ", 1)[1])


class LibraryEventBusTests(unittest.IsolatedAsyncioTestCase):
    async def test_delivery_does_not_wait_for_default_executor_capacity(self):
        loop = asyncio.get_running_loop()
        loop.set_default_executor(ThreadPoolExecutor(max_workers=1))
        started, release = Event(), Event()

        def occupy_worker():
            started.set()
            release.wait()

        worker = loop.run_in_executor(None, occupy_worker)
        bus = LibraryEventBus()
        stream = bus.subscribe(ConnectedRequest())
        try:
            while not started.is_set():
                await asyncio.sleep(0)
            self.assertIn("event: connected", await anext(stream))
            pending = asyncio.create_task(anext(stream))
            await asyncio.sleep(0)
            bus.publish_library_changed("profile_state_updated", film_id="film_test")
            message = await asyncio.wait_for(pending, 1)
            self.assertEqual(payload(message)["film_id"], "film_test")
        finally:
            release.set()
            await worker
            await stream.aclose()

    async def test_threaded_publish_preserves_order_and_keeps_latest_bounded_events(self):
        bus = LibraryEventBus()
        stream = bus.subscribe(ConnectedRequest())
        await anext(stream)
        try:
            thread = Thread(target=lambda: [bus.publish("library_changed", {"index": i}) for i in range(25)])
            thread.start()
            thread.join()
            await asyncio.sleep(0)  # Drain thread-safe enqueue callbacks.
            messages = [payload(await asyncio.wait_for(anext(stream), 1))["index"] for _ in range(20)]
            self.assertEqual(messages, list(range(5, 25)))
        finally:
            await stream.aclose()
        self.assertFalse(bus._subscribers)

    async def test_cancelled_subscriber_does_not_delay_replacement(self):
        bus = LibraryEventBus()
        old_stream = bus.subscribe(ConnectedRequest())
        await anext(old_stream)
        pending = asyncio.create_task(anext(old_stream))
        await asyncio.sleep(0)
        pending.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await pending
        self.assertFalse(bus._subscribers)
        stream = bus.subscribe(ConnectedRequest())
        await anext(stream)
        try:
            bus.publish_library_changed("scan_complete")
            self.assertEqual(payload(await asyncio.wait_for(anext(stream), 1))["reason"], "scan_complete")
        finally:
            await stream.aclose()


if __name__ == "__main__":
    unittest.main()
