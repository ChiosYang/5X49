import threading

from app.jobs.actors import JOB_HANDLERS
from app.jobs.store import job_store
from app.services.event_bus import library_event_bus


class JobCancelled(Exception):
    pass


class JobContext:
    def __init__(self, job_id: str):
        self.job_id = job_id

    def progress(
        self,
        *,
        stage: str,
        current: int | None = None,
        total: int | None = None,
        message: str | None = None,
        **extra,
    ) -> dict | None:
        progress = {
            "stage": stage,
            "current": current,
            "total": total,
            "message": message,
            **extra,
        }
        progress = {key: value for key, value in progress.items() if value is not None}
        job = job_store.update(self.job_id, progress=progress)
        if job:
            library_event_bus.publish("job_progress", {"job": JobRuntime.public_job(job)})
        return job

    def is_cancel_requested(self) -> bool:
        return job_store.is_cancel_requested(self.job_id)

    def raise_if_cancelled(self):
        if self.is_cancel_requested():
            raise JobCancelled("Job cancelled")


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

    def enqueue(
        self,
        job_type: str,
        payload: dict | None = None,
        max_attempts: int = 1,
        priority: int = 0,
        dedupe_key: str | None = None,
    ) -> dict:
        if job_type not in JOB_HANDLERS:
            raise ValueError(f"Unknown job type: {job_type}")
        if dedupe_key:
            existing_job = job_store.find_active(dedupe_key)
            if existing_job:
                return existing_job
        job = job_store.create(job_type, payload, max_attempts, priority, dedupe_key)
        library_event_bus.publish("job_queued", {"job": self.public_job(job)})
        return job

    def get(self, job_id: str) -> dict | None:
        return job_store.get(job_id)

    def list(
        self,
        status: str | None = None,
        job_type: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        return job_store.list(status, job_type, limit)

    def cancel(self, job_id: str) -> dict | None:
        job = job_store.request_cancel(job_id)
        if job:
            event = "job_cancelled" if job["status"] == "cancelled" else "job_progress"
            library_event_bus.publish(event, {"job": self.public_job(job)})
        return job

    def retry(self, job_id: str) -> dict | None:
        job = job_store.retry(job_id)
        if job:
            library_event_bus.publish("job_retried", {"job": self.public_job(job)})
            library_event_bus.publish("job_queued", {"job": self.public_job(job)})
        return job

    def delete(self, job_id: str) -> bool:
        return job_store.delete(job_id)

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
        library_event_bus.publish("job_started", {"job": self.public_job(job)})

        try:
            handler = JOB_HANDLERS[job_type]
            ctx = JobContext(job_id)
            result = handler(job.get("payload") or {}, ctx)
            updated = job_store.update(
                job_id,
                status="succeeded",
                result=result or {},
                result_summary=self._result_summary(job_type, result or {}),
                finished=True,
            )
            if updated:
                library_event_bus.publish("job_succeeded", {"job": self.public_job(updated)})
        except JobCancelled as exc:
            cancelled = job_store.update(
                job_id,
                status="cancelled",
                error=str(exc),
                result_summary="Cancelled",
                finished=True,
            )
            if cancelled:
                library_event_bus.publish("job_cancelled", {"job": self.public_job(cancelled)})
        except Exception as exc:
            failed = job_store.update(
                job_id,
                status="failed",
                error=str(exc),
                result_summary=str(exc),
                finished=True,
            )
            if failed:
                library_event_bus.publish("job_failed", {"job": self.public_job(failed)})

    @staticmethod
    def public_job(job: dict) -> dict:
        return {
            "id": job["id"],
            "type": job["type"],
            "status": job["status"],
            "payload": job.get("payload"),
            "progress": job.get("progress"),
            "result": job.get("result"),
            "result_summary": job.get("result_summary"),
            "error": job.get("error"),
            "attempts": job.get("attempts"),
            "max_attempts": job.get("max_attempts"),
            "priority": job.get("priority"),
            "dedupe_key": job.get("dedupe_key"),
            "cancel_requested": job.get("cancel_requested"),
            "created_at": job.get("created_at"),
            "updated_at": job.get("updated_at"),
            "started_at": job.get("started_at"),
            "finished_at": job.get("finished_at"),
        }

    def _result_summary(self, job_type: str, result: dict) -> str:
        if job_type == "library.reconcile":
            return (
                f"Scanned {result.get('scanned', 0)}, "
                f"added {result.get('added', 0)}, missing {result.get('missing', 0)}"
            )
        if job_type == "metadata.scrape_library":
            return (
                f"Scraped {result.get('succeeded', 0)}, "
                f"review {result.get('needs_review', 0)}, failed {result.get('failed', 0)}"
            )
        if job_type == "organizer.organize_root":
            return (
                f"Organized {result.get('organized', 0)}, "
                f"review {result.get('needs_review', 0)}, failed {result.get('failed', 0)}"
            )
        if job_type == "external_scores.refresh_library":
            return (
                f"Updated {result.get('updated', 0)}, "
                f"skipped {result.get('skipped', 0)}, failed {result.get('failed', 0)}"
            )
        if job_type == "external_scores.refresh_movie":
            return "External scores refreshed" if result.get("updated_sources") else "No external score match"
        if job_type == "analysis.analyze_movie":
            return "Analysis finished"
        if result.get("status"):
            return str(result["status"])
        return "Completed"


job_runtime = JobRuntime()
