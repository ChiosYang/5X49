from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WorkflowDefinition:
    type: str
    version: str
    steps: tuple[str, ...]
    max_attempts: int = 2


def _definition(workflow_type: str, *steps: str, max_attempts: int = 2) -> WorkflowDefinition:
    return WorkflowDefinition(
        type=workflow_type,
        version=f"{workflow_type}.v1",
        steps=tuple(steps),
        max_attempts=max_attempts,
    )


WORKFLOW_DEFINITIONS = {
    item.type: item
    for item in (
        _definition(
            "library.reconcile",
            "discover",
            "inspect",
            "resolve",
            "persist",
            "reconcile_missing",
            "finalize",
        ),
        _definition("library.scan_folder", "resolve_subject", "inspect", "persist", "finalize"),
        _definition("library.mark_path_missing", "resolve_subject", "persist", "finalize"),
        _definition("library.refresh_item", "resolve_subject", "inspect", "persist", "finalize"),
        _definition("library.resolve_relink", "inspect", "resolve", "persist", "finalize"),
        _definition(
            "metadata.scrape_library",
            "resolve_subject",
            "search_match",
            "fetch",
            "persist",
            "artwork_scores",
            "finalize",
        ),
        _definition("organizer.organize_root", "resolve_subject", "inspect", "persist", "finalize"),
        _definition("organizer.confirm_root_video", "resolve_subject", "inspect", "persist", "finalize"),
        _definition(
            "analysis.analyze_film",
            "build_input",
            "generate",
            "resolve",
            "critic",
            "verify_evidence",
            "persist",
            "finalize",
        ),
        _definition("external_scores.refresh_film", "resolve_subject", "fetch", "persist", "finalize"),
        _definition("external_scores.refresh_library", "resolve_subject", "fetch", "persist", "finalize"),
    )
}


def workflow_definition(workflow_type: str) -> WorkflowDefinition:
    try:
        return WORKFLOW_DEFINITIONS[workflow_type]
    except KeyError as exc:
        raise ValueError(f"Unknown workflow type: {workflow_type}") from exc


__all__ = ["WORKFLOW_DEFINITIONS", "WorkflowDefinition", "workflow_definition"]
