from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlmodel import Session, select

from app.database import engine
from app.models import Job


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobStore:
    def create(self, job_type: str, payload: Optional[dict] = None, max_attempts: int = 1) -> dict:
        job = Job(
            id=f"job_{uuid4().hex}",
            type=job_type,
            payload=payload or {},
            max_attempts=max_attempts,
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

    def list(self, status: Optional[str] = None, limit: int = 50) -> list[dict]:
        limit = max(1, min(limit, 200))
        with Session(engine) as session:
            statement = select(Job).order_by(Job.created_at.desc()).limit(limit)
            if status:
                statement = select(Job).where(Job.status == status).order_by(Job.created_at.desc()).limit(limit)
            return [job.model_dump() for job in session.exec(statement).all()]

    def claim_next(self) -> Optional[dict]:
        now = utc_now_iso()
        with Session(engine) as session:
            statement = (
                select(Job)
                .where(Job.status == "queued")
                .order_by(Job.created_at)
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
            if error is not None:
                job.error = error
            if finished:
                job.finished_at = now
            job.updated_at = now

            session.add(job)
            session.commit()
            session.refresh(job)
            return job.model_dump()

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
