from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from sqlmodel import Session, select

from app.database import engine
from app.models import Job, WorkflowRun, WorkflowStep
from app.workflows.definitions import WorkflowDefinition, workflow_definition


ACTIVE_STATUSES = ("queued", "running")
_ABSOLUTE_PATH = re.compile(r"(?:^[A-Za-z]:[\\/]|^/[^/])")
_SECRET_TEXT = re.compile(r"(?:api[_-]?key|bearer\s+[A-Za-z0-9._-]+)", re.IGNORECASE)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash(value: Any) -> str:
    serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _bounded_summary(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if _ABSOLUTE_PATH.search(text) or _SECRET_TEXT.search(text):
        return "Workflow step completed"
    return text[:240]


class WorkflowStore:
    def create(
        self,
        workflow_type: str,
        payload: dict[str, Any] | None,
        *,
        dedupe_key: str | None = None,
        priority: int = 0,
        subject_type: str | None = None,
        subject_id: str | None = None,
    ) -> tuple[dict[str, Any], bool]:
        with Session(engine) as session:
            run, _job, created = self.enqueue_in_session(
                session,
                workflow_type,
                payload,
                dedupe_key=dedupe_key,
                priority=priority,
                subject_type=subject_type,
                subject_id=subject_id,
            )
            session.commit()
            return self.public_view_from_session(session, run.id), created

    def enqueue_in_session(
        self,
        session: Session,
        workflow_type: str,
        payload: dict[str, Any] | None,
        *,
        dedupe_key: str | None = None,
        priority: int = 0,
        subject_type: str | None = None,
        subject_id: str | None = None,
    ) -> tuple[WorkflowRun, Job, bool]:
        definition = workflow_definition(workflow_type)
        if dedupe_key:
            existing = session.exec(
                select(WorkflowRun)
                .where(WorkflowRun.dedupe_key == dedupe_key)
                .where(WorkflowRun.status.in_(ACTIVE_STATUSES))
                .order_by(WorkflowRun.created_at)
            ).first()
            if existing is not None:
                job = session.exec(
                    select(Job)
                    .where(Job.workflow_run_id == existing.id)
                    .where(Job.status.in_(("queued", "running", "cancelling")))
                    .order_by(Job.created_at.desc())
                ).first()
                if job is None:
                    raise RuntimeError("active workflow is missing its execution job")
                return existing, job, False
        payload = dict(payload or {})
        resolved_type, resolved_id = self._subject(payload, subject_type, subject_id)
        input_hash = _hash(payload)
        run = WorkflowRun(
            type=workflow_type,
            definition_version=definition.version,
            subject_type=resolved_type,
            subject_id=resolved_id,
            input_hash=input_hash,
            dedupe_key=dedupe_key,
            status="queued",
            current_step_key=definition.steps[0],
        )
        session.add(run)
        session.flush()
        steps = self._new_steps(run, definition)
        session.add_all(steps)
        session.flush()
        job = Job(
            id=f"job_{uuid4().hex}",
            type=workflow_type,
            payload=payload,
            max_attempts=definition.max_attempts,
            priority=priority,
            dedupe_key=dedupe_key,
            workflow_run_id=run.id,
            workflow_step_id=steps[0].id,
        )
        session.add(job)
        session.flush()
        return run, job, True

    def get(self, workflow_id: str) -> dict[str, Any] | None:
        with Session(engine) as session:
            if session.get(WorkflowRun, workflow_id) is None:
                return None
            return self.public_view_from_session(session, workflow_id)

    def list(
        self,
        *,
        status: str | None = None,
        workflow_type: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        with Session(engine) as session:
            statement = select(WorkflowRun)
            if status:
                statement = statement.where(WorkflowRun.status == status)
            if workflow_type:
                statement = statement.where(WorkflowRun.type == workflow_type)
            runs = session.exec(statement.order_by(WorkflowRun.created_at.desc()).limit(max(1, min(limit, 200)))).all()
            return [self.public_view_from_session(session, run.id) for run in runs]

    def start_job(self, job_id: str) -> dict[str, Any] | None:
        with Session(engine) as session:
            job = session.get(Job, job_id)
            if job is None or not job.workflow_run_id:
                return None
            run = session.get(WorkflowRun, job.workflow_run_id)
            if run is None:
                return None
            step = self._current_step(session, run)
            now = _now()
            run.status = "running"
            run.started_at = run.started_at or now
            run.updated_at = now
            if step is not None:
                step.status = "running"
                step.attempt = max(step.attempt + 1, int(job.attempts or 1))
                step.started_at = step.started_at or now
                step.lease_expires_at = (datetime.now(timezone.utc) + timedelta(seconds=90)).isoformat()
                step.updated_at = now
                job.workflow_step_id = step.id
                session.add(step)
            session.add(run)
            session.add(job)
            session.commit()
            return self.public_view_from_session(session, run.id)

    def progress(self, job_id: str, stage: str, summary: object | None = None) -> dict[str, Any] | None:
        with Session(engine) as session:
            job = session.get(Job, job_id)
            if job is None or not job.workflow_run_id:
                return None
            run = session.get(WorkflowRun, job.workflow_run_id)
            if run is None:
                return None
            steps = self._steps(session, run.id)
            target = next((step for step in steps if step.step_key == stage), None)
            if target is None:
                return self.public_view_from_session(session, run.id)
            now = _now()
            for step in steps:
                if step.position < target.position and step.status not in {"succeeded", "failed", "cancelled"}:
                    step.status = "succeeded"
                    step.output_hash = _hash({"step": step.step_key, "input": step.input_hash})
                    step.result_summary = step.result_summary or "Step completed"
                    step.finished_at = now
                    step.lease_expires_at = None
                    step.updated_at = now
                    session.add(step)
            if target.status != "succeeded":
                target.status = "running"
                target.attempt = max(target.attempt, int(job.attempts or 1))
                target.started_at = target.started_at or now
                target.lease_expires_at = (datetime.now(timezone.utc) + timedelta(seconds=90)).isoformat()
                target.result_summary = _bounded_summary(summary)
                target.updated_at = now
                session.add(target)
            run.status = "running"
            run.current_step_key = target.step_key
            run.updated_at = now
            job.workflow_step_id = target.id
            session.add(run)
            session.add(job)
            session.commit()
            return self.public_view_from_session(session, run.id)

    def succeed_job(self, job_id: str, result: dict[str, Any] | None) -> dict[str, Any] | None:
        with Session(engine) as session:
            job = session.get(Job, job_id)
            if job is None or not job.workflow_run_id:
                return None
            run = session.get(WorkflowRun, job.workflow_run_id)
            if run is None:
                return None
            now = _now()
            output_hash = _hash(result or {})
            for step in self._steps(session, run.id):
                if step.status not in {"failed", "cancelled"}:
                    step.status = "succeeded"
                    step.output_hash = step.output_hash or _hash(
                        {"workflow_output": output_hash, "step": step.step_key}
                    )
                    step.result_summary = step.result_summary or "Step completed"
                    step.finished_at = step.finished_at or now
                    step.lease_expires_at = None
                    step.updated_at = now
                    session.add(step)
            run.status = "succeeded"
            run.current_step_key = workflow_definition(run.type).steps[-1]
            run.finished_at = now
            run.updated_at = now
            run.error_code = None
            run.error_message = None
            session.add(run)
            session.commit()
            return self.public_view_from_session(session, run.id)

    def fail_job(self, job_id: str, *, cancelled: bool, error_code: str) -> dict[str, Any] | None:
        with Session(engine) as session:
            job = session.get(Job, job_id)
            if job is None or not job.workflow_run_id:
                return None
            run = session.get(WorkflowRun, job.workflow_run_id)
            if run is None:
                return None
            now = _now()
            status = "cancelled" if cancelled else "failed"
            step = self._current_step(session, run)
            if step is not None:
                step.status = status
                step.result_summary = "Workflow cancelled" if cancelled else "Workflow step failed"
                step.finished_at = now
                step.lease_expires_at = None
                step.updated_at = now
                session.add(step)
            run.status = status
            run.cancel_requested = cancelled or run.cancel_requested
            run.error_code = "workflow_cancelled" if cancelled else error_code[:80]
            run.error_message = "Workflow cancelled" if cancelled else "Workflow execution failed"
            run.finished_at = now
            run.updated_at = now
            session.add(run)
            session.commit()
            return self.public_view_from_session(session, run.id)

    def request_cancel(self, workflow_id: str) -> dict[str, Any] | None:
        with Session(engine) as session:
            run = session.get(WorkflowRun, workflow_id)
            if run is None:
                return None
            if run.status not in ACTIVE_STATUSES:
                return self.public_view_from_session(session, run.id)
            now = _now()
            run.cancel_requested = True
            run.updated_at = now
            job = self._latest_job(session, run.id)
            if job is not None:
                job.cancel_requested = True
                if job.status == "queued":
                    job.status = "cancelled"
                    job.finished_at = now
                    run.status = "cancelled"
                    run.finished_at = now
                    run.error_code = "workflow_cancelled"
                    run.error_message = "Workflow cancelled"
                    step = self._current_step(session, run)
                    if step is not None:
                        step.status = "cancelled"
                        step.finished_at = now
                        step.updated_at = now
                        session.add(step)
                elif job.status == "running":
                    job.status = "cancelling"
                job.updated_at = now
                session.add(job)
            session.add(run)
            session.commit()
            return self.public_view_from_session(session, run.id)

    def retry(self, workflow_id: str) -> dict[str, Any] | None:
        with Session(engine) as session:
            run = session.get(WorkflowRun, workflow_id)
            if run is None:
                return None
            if run.status not in {"failed", "cancelled"}:
                return self.public_view_from_session(session, run.id)
            previous = self._latest_job(session, run.id)
            if previous is None:
                raise RuntimeError("workflow is missing its execution job")
            steps = self._steps(session, run.id)
            resume = next((step for step in steps if step.status in {"failed", "cancelled"}), None)
            if resume is None:
                resume = next((step for step in steps if step.status != "succeeded"), steps[-1])
            now = _now()
            for step in steps:
                if step.position >= resume.position:
                    step.status = "pending"
                    step.output_hash = None
                    step.result_summary = None
                    step.started_at = None
                    step.finished_at = None
                    step.lease_expires_at = None
                    step.updated_at = now
                    session.add(step)
            resume.status = "queued"
            run.status = "queued"
            run.current_step_key = resume.step_key
            run.cancel_requested = False
            run.error_code = None
            run.error_message = None
            run.finished_at = None
            run.updated_at = now
            job = Job(
                id=f"job_{uuid4().hex}",
                type=run.type,
                payload=previous.payload or {},
                max_attempts=previous.max_attempts,
                priority=previous.priority,
                dedupe_key=run.dedupe_key,
                workflow_run_id=run.id,
                workflow_step_id=resume.id,
                created_at=now,
                updated_at=now,
            )
            session.add(run)
            session.add(job)
            session.commit()
            return self.public_view_from_session(session, run.id)

    def recover_interrupted(self) -> int:
        recovered = 0
        with Session(engine) as session:
            runs = session.exec(
                select(WorkflowRun).where(WorkflowRun.status.in_(ACTIVE_STATUSES))
            ).all()
            now = _now()
            for run in runs:
                job = self._latest_job(session, run.id)
                if job is None:
                    run.status = "failed"
                    run.error_code = "workflow_job_missing"
                    run.error_message = "Workflow execution failed"
                    run.finished_at = now
                elif job.status == "queued":
                    run.status = "queued"
                    step = self._current_step(session, run)
                    if step is not None and step.status == "running":
                        step.status = "queued"
                        step.lease_expires_at = None
                        step.updated_at = now
                        session.add(step)
                elif job.status in {"failed", "cancelled"}:
                    run.status = job.status
                    run.error_code = "workflow_interrupted"
                    run.error_message = "Workflow execution was interrupted"
                    run.finished_at = now
                run.updated_at = now
                session.add(run)
                recovered += 1
            session.commit()
        return recovered

    def public_view_from_session(self, session: Session, workflow_id: str) -> dict[str, Any]:
        run = session.get(WorkflowRun, workflow_id)
        if run is None:
            raise LookupError("Workflow not found")
        job = self._latest_job(session, run.id)
        progress = dict(job.progress or {}) if job is not None else {}
        progress = {
            key: value
            for key, value in progress.items()
            if key in {"stage", "current", "total", "percent", "counts"}
            and isinstance(value, (str, int, float, bool, dict))
        }
        return {
            "id": run.id,
            "type": run.type,
            "definition_version": run.definition_version,
            "subject_type": run.subject_type,
            "subject_id": run.subject_id,
            "status": run.status,
            "current_step": run.current_step_key,
            "cancel_requested": run.cancel_requested,
            "progress": progress or None,
            "result_summary": _bounded_summary(job.result_summary if job else None),
            "error_code": run.error_code,
            "error_message": _bounded_summary(run.error_message),
            "created_at": run.created_at,
            "updated_at": run.updated_at,
            "started_at": run.started_at,
            "finished_at": run.finished_at,
            "steps": [self._step_view(step) for step in self._steps(session, run.id)],
        }

    @staticmethod
    def _new_steps(run: WorkflowRun, definition: WorkflowDefinition) -> list[WorkflowStep]:
        return [
            WorkflowStep(
                workflow_run_id=run.id,
                step_key=step_key,
                position=position,
                status="queued" if position == 0 else "pending",
                max_attempts=definition.max_attempts,
                retry_policy={"kind": "bounded", "max_attempts": definition.max_attempts},
                input_hash=_hash(
                    {
                        "definition": definition.version,
                        "run_input": run.input_hash,
                        "step": step_key,
                    }
                ),
            )
            for position, step_key in enumerate(definition.steps)
        ]

    @staticmethod
    def _subject(
        payload: dict[str, Any],
        subject_type: str | None,
        subject_id: str | None,
    ) -> tuple[str, str | None]:
        if subject_type:
            return subject_type, subject_id
        if isinstance(payload.get("film_id"), str):
            return "film", payload["film_id"]
        if isinstance(payload.get("library_item_id"), str):
            return "library_item", payload["library_item_id"]
        return "library", None

    @staticmethod
    def _step_view(step: WorkflowStep) -> dict[str, Any]:
        return {
            "id": step.id,
            "step_key": step.step_key,
            "position": step.position,
            "status": step.status,
            "attempt": step.attempt,
            "max_attempts": step.max_attempts,
            "result_summary": _bounded_summary(step.result_summary),
            "compensation_status": step.compensation_status,
            "started_at": step.started_at,
            "finished_at": step.finished_at,
        }

    @staticmethod
    def _steps(session: Session, workflow_id: str) -> list[WorkflowStep]:
        return session.exec(
            select(WorkflowStep)
            .where(WorkflowStep.workflow_run_id == workflow_id)
            .order_by(WorkflowStep.position)
        ).all()

    def _current_step(self, session: Session, run: WorkflowRun) -> WorkflowStep | None:
        steps = self._steps(session, run.id)
        return next((step for step in steps if step.step_key == run.current_step_key), None)

    @staticmethod
    def _latest_job(session: Session, workflow_id: str) -> Job | None:
        return session.exec(
            select(Job)
            .where(Job.workflow_run_id == workflow_id)
            .order_by(Job.created_at.desc())
        ).first()


workflow_store = WorkflowStore()


__all__ = ["WorkflowStore", "workflow_store"]
