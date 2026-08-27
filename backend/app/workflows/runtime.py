from __future__ import annotations

from typing import Any

from app.services.event_bus import library_event_bus
from app.workflows.store import workflow_store


class WorkflowRuntime:
    def enqueue(
        self,
        workflow_type: str,
        payload: dict[str, Any] | None = None,
        *,
        dedupe_key: str | None = None,
        priority: int = 0,
        subject_type: str | None = None,
        subject_id: str | None = None,
    ) -> dict[str, Any]:
        workflow, created = workflow_store.create(
            workflow_type,
            payload,
            dedupe_key=dedupe_key,
            priority=priority,
            subject_type=subject_type,
            subject_id=subject_id,
        )
        if created:
            library_event_bus.publish("workflow_queued", {"workflow": workflow})
        return workflow

    def get(self, workflow_id: str) -> dict[str, Any] | None:
        return workflow_store.get(workflow_id)

    def list(self, *, status: str | None = None, workflow_type: str | None = None, limit: int = 50):
        return workflow_store.list(status=status, workflow_type=workflow_type, limit=limit)

    def cancel(self, workflow_id: str) -> dict[str, Any] | None:
        workflow = workflow_store.request_cancel(workflow_id)
        if workflow is not None:
            event = "workflow_cancelled" if workflow["status"] == "cancelled" else "workflow_progress"
            library_event_bus.publish(event, {"workflow": workflow})
        return workflow

    def retry(self, workflow_id: str) -> dict[str, Any] | None:
        workflow = workflow_store.retry(workflow_id)
        if workflow is not None:
            library_event_bus.publish("workflow_queued", {"workflow": workflow})
        return workflow


workflow_runtime = WorkflowRuntime()


__all__ = ["WorkflowRuntime", "workflow_runtime"]
