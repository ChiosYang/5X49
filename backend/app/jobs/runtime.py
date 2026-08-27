import threading

from app.jobs.actors import JOB_HANDLERS
from app.jobs.store import job_store
from app.services.event_bus import library_event_bus
from app.workflows.store import workflow_store


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
        workflow = workflow_store.progress(self.job_id, stage, message)
        if workflow:
            library_event_bus.publish("workflow_progress", {"workflow": workflow})
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
            workflow_store.recover_interrupted()
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run, name="job-runtime", daemon=True)
            self._thread.start()

    def stop(self):
        self._stop_event.set()
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=5)

    def _run(self):
        while not self._stop_event.is_set():
            job = job_store.claim_next()
            if not job:
                self._stop_event.wait(1)
                continue
            workflow = workflow_store.start_job(job["id"])
            if workflow:
                library_event_bus.publish("workflow_running", {"workflow": workflow})
            self._execute(job)

    def _execute(self, job: dict):
        job_id = job["id"]
        job_type = job["type"]
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
                workflow = workflow_store.succeed_job(job_id, result or {})
                if workflow:
                    library_event_bus.publish("workflow_succeeded", {"workflow": workflow})
        except JobCancelled as exc:
            cancelled = job_store.update(
                job_id,
                status="cancelled",
                error=str(exc),
                result_summary="Cancelled",
                finished=True,
            )
            if cancelled:
                workflow = workflow_store.fail_job(
                    job_id,
                    cancelled=True,
                    error_code="workflow_cancelled",
                )
                if workflow:
                    library_event_bus.publish("workflow_cancelled", {"workflow": workflow})
        except Exception as exc:
            failed = job_store.update(
                job_id,
                status="failed",
                error=exc.__class__.__name__,
                result_summary="Job failed",
                finished=True,
            )
            if failed:
                workflow = workflow_store.fail_job(
                    job_id,
                    cancelled=False,
                    error_code=f"{job_type.replace('.', '_')}_failed",
                )
                if workflow:
                    library_event_bus.publish("workflow_failed", {"workflow": workflow})

    @staticmethod
    def _result_summary(job_type: str, result: dict) -> str:
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
        if job_type == "external_scores.refresh_film":
            return "External scores refreshed" if result.get("updated_sources") else "No external score match"
        if job_type == "analysis.analyze_film":
            return "Analysis finished"
        if job_type == "library.resolve_relink":
            return (
                f"Relink {result.get('status', 'completed')}, "
                f"matched {result.get('matched', 0)}"
            )
        if result.get("status"):
            return str(result["status"])
        return "Completed"


job_runtime = JobRuntime()
