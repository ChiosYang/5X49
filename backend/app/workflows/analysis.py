from __future__ import annotations

from typing import Any, Protocol

from app.workflows.definitions import workflow_definition


ANALYSIS_WORKFLOW_VERSION = workflow_definition("analysis.analyze_film").version


class AnalysisWorkflowService(Protocol):
    def analyze_film(self, film_id: str, ctx: Any | None = None) -> dict: ...


def execute_analysis_workflow(
    service: AnalysisWorkflowService,
    film_id: str,
    *,
    ctx: Any | None = None,
) -> dict:
    """Single production/evaluation entrypoint for the Analysis workflow."""
    return service.analyze_film(film_id, ctx=ctx)


__all__ = ["ANALYSIS_WORKFLOW_VERSION", "execute_analysis_workflow"]
