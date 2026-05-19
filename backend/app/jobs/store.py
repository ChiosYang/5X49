from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import or_
from sqlmodel import Session, select, delete

from app.database import engine
from app.models import Job


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


ACTIVE_STATUSES = {"queued", "running", "cancelling"}


class JobStore:
    def create(
        self,
        job_type: str,
        payload: Optional[dict] = None,
        max_attempts: int = 1,
        priority: int = 0,
        dedupe_key: Optional[str] = None,
    ) -> dict:
        job = Job(
            id=f"job_{uuid4().hex}",
            type=job_type,
            payload=payload or {},
            max_attempts=max_attempts,
            priority=priority,
            dedupe_key=dedupe_key,
        )
        with Session(engine) as session:
            session.add(job)
            session.commit()
            session.refresh(job)
            return job.model_dump()

    def get(self, job_id: str) -> Optional[dict]:
        with Session(engine) as session:
            job = session.get(Job, job_id)
            return job.model_dump() if job else None

    def find_active(self, dedupe_key: str) -> Optional[dict]:
        with Session(engine) as session:
            statement = (
                select(Job)
                .where(Job.dedupe_key == dedupe_key)
                .where(Job.status.in_(ACTIVE_STATUSES))
                .order_by(Job.created_at)
                .limit(1)
            )
            job = session.exec(statement).first()
            return job.model_dump() if job else None

    def list(
        self,
        status: Optional[str] = None,
        job_type: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict]:
        limit = max(1, min(limit, 200))
        with Session(engine) as session:
            statement = select(Job)
            if status:
                statement = statement.where(Job.status == status)
            if job_type:
                statement = statement.where(Job.type == job_type)
            statement = statement.order_by(Job.created_at.desc()).limit(limit)
            return [job.model_dump() for job in session.exec(statement).all()]

    def claim_next(self) -> Optional[dict]:
        now = utc_now_iso()
        with Session(engine) as session:
            statement = (
                select(Job)
                .where(Job.status == "queued")
                .order_by(Job.priority.desc(), Job.created_at)
                .limit(1)
            )
            job = session.exec(statement).first()
            if not job:
                return None

            job.status = "running"
            job.attempts += 1
            job.started_at = now
            job.updated_at = now
            job.error = None
            job.cancel_requested = False
            session.add(job)
            session.commit()
            session.refresh(job)
            return job.model_dump()

    def update(
        self,
        job_id: str,
        *,
        status: Optional[str] = None,
        progress: Optional[dict] = None,
        result: Optional[dict] = None,
        result_summary: Optional[str] = None,
        error: Optional[str] = None,
        finished: bool = False,
    ) -> Optional[dict]:
        now = utc_now_iso()
        with Session(engine) as session:
            job = session.get(Job, job_id)
            if not job:
                return None

            if status is not None:
                job.status = status
            if progress is not None:
                job.progress = progress
            if result is not None:
                job.result = result
            if result_summary is not None:
                job.result_summary = result_summary
            if error is not None:
                job.error = error
            if finished:
                job.finished_at = now
            job.updated_at = now

            session.add(job)
            session.commit()
            session.refresh(job)
            return job.model_dump()

    def request_cancel(self, job_id: str) -> Optional[dict]:
        now = utc_now_iso()
        with Session(engine) as session:
            job = session.get(Job, job_id)
            if not job:
                return None
            if job.status == "queued":
                job.status = "cancelled"
                job.cancel_requested = True
                job.finished_at = now
            elif job.status == "running":
                job.status = "cancelling"
                job.cancel_requested = True
            elif job.status == "cancelling":
                job.cancel_requested = True
            job.updated_at = now
            session.add(job)
            session.commit()
            session.refresh(job)
            return job.model_dump()

    def is_cancel_requested(self, job_id: str) -> bool:
        with Session(engine) as session:
            job = session.get(Job, job_id)
            return bool(job and job.cancel_requested)

    def retry(self, job_id: str) -> Optional[dict]:
        now = utc_now_iso()
        with Session(engine) as session:
            job = session.get(Job, job_id)
            if not job:
                return None
            if job.status not in {"failed", "cancelled"}:
                return job.model_dump()
            if job.dedupe_key:
                existing_job = self.find_active(job.dedupe_key)
                if existing_job:
                    return existing_job
            retry_job = Job(
                id=f"job_{uuid4().hex}",
                type=job.type,
                payload=job.payload or {},
                max_attempts=job.max_attempts,
                priority=job.priority,
                dedupe_key=job.dedupe_key,
                progress={"stage": "queued", "message": "Retry queued"},
                result_summary=f"Retry of {job.id}",
                created_at=now,
                updated_at=now,
            )
            session.add(retry_job)
            session.commit()
            session.refresh(retry_job)
            return retry_job.model_dump()

    def delete(self, job_id: str) -> bool:
        with Session(engine) as session:
            statement = delete(Job).where(Job.id == job_id).where(
                or_(Job.status == "succeeded", Job.status == "failed", Job.status == "cancelled")
            )
            result = session.exec(statement)
            session.commit()
            return bool(result.rowcount)

    def reset_interrupted(self) -> int:
        now = utc_now_iso()
        updated = 0
        with Session(engine) as session:
            statement = select(Job).where(Job.status == "running")
            for job in session.exec(statement).all():
                if job.attempts < job.max_attempts:
                    job.status = "queued"
                    job.error = "Interrupted by backend restart"
                else:
                    job.status = "failed"
                    job.error = "Interrupted by backend restart"
                    job.finished_at = now
                job.updated_at = now
                session.add(job)
                updated += 1
            session.commit()
        return updated


job_store = JobStore()
