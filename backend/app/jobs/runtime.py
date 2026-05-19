import threading

from app.jobs.actors import JOB_HANDLERS
from app.jobs.store import job_store
from app.services.event_bus import library_event_bus


class JobRuntime:
    def __init__(self):
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

    def start(self):
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            job_store.reset_interrupted()
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run, name="job-runtime", daemon=True)
            self._thread.start()

    def stop(self):
        self._stop_event.set()
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=5)

    def enqueue(self, job_type: str, payload: dict | None = None, max_attempts: int = 1) -> dict:
        if job_type not in JOB_HANDLERS:
            raise ValueError(f"Unknown job type: {job_type}")
        job = job_store.create(job_type, payload, max_attempts)
        library_event_bus.publish("job_queued", {"job": self._public_job(job)})
        return job

    def get(self, job_id: str) -> dict | None:
        return job_store.get(job_id)

    def list(self, status: str | None = None, limit: int = 50) -> list[dict]:
        return job_store.list(status, limit)

    def _run(self):
        while not self._stop_event.is_set():
            job = job_store.claim_next()
            if not job:
                self._stop_event.wait(1)
                continue
            self._execute(job)

    def _execute(self, job: dict):
        job_id = job["id"]
        job_type = job["type"]
        library_event_bus.publish("job_started", {"job": self._public_job(job)})

        try:
            handler = JOB_HANDLERS[job_type]
            result = handler(job.get("payload") or {})
            updated = job_store.update(
                job_id,
                status="succeeded",
                result=result or {},
                finished=True,
            )
            if updated:
                library_event_bus.publish("job_succeeded", {"job": self._public_job(updated)})
        except Exception as exc:
            failed = job_store.update(
                job_id,
                status="failed",
                error=str(exc),
                finished=True,
            )
            if failed:
                library_event_bus.publish("job_failed", {"job": self._public_job(failed)})

    def _public_job(self, job: dict) -> dict:
        return {
            "id": job["id"],
            "type": job["type"],
            "status": job["status"],
            "progress": job.get("progress"),
            "result": job.get("result"),
            "error": job.get("error"),
            "attempts": job.get("attempts"),
            "created_at": job.get("created_at"),
            "updated_at": job.get("updated_at"),
            "started_at": job.get("started_at"),
            "finished_at": job.get("finished_at"),
        }


job_runtime = JobRuntime()
