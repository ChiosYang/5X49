from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictContract(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class AnonymousEventName(StrEnum):
    INSTALL_COMPLETED = "install_completed"
    LIBRARY_IMPORT_COMPLETED = "library_import_completed"
    FIRST_FILM_OPENED = "first_film_opened"
    ANALYSIS_COMPLETED = "analysis_completed"
    GRAPH_OPENED = "graph_opened"
    VIEWING_CREATED = "viewing_created"
    EXPLORE_USED = "explore_used"
    ASK_USED = "ask_used"
    APP_REOPENED = "app_reopened"


class AnonymousEventProperties(StrictContract):
    result: Literal["success", "failure", "cancelled", "skipped"] | None = None
    source_type: Literal["local_nfo", "local_folder", "seed", "unknown"] | None = None
    capability: Literal["import", "analysis", "graph", "viewing", "explore", "ask"] | None = None
    error_category: Literal[
        "configuration",
        "provider",
        "validation",
        "filesystem",
        "database",
        "cancelled",
        "unknown",
    ] | None = None
    duration_ms: int | None = Field(default=None, ge=0, le=86_400_000)
    item_count: int | None = Field(default=None, ge=0, le=10_000_000)
    attempt_number: int | None = Field(default=None, ge=1, le=100)
    offline_mode: bool | None = None


class LocalAnonymousEvent(StrictContract):
    contract_version: Literal["local-anonymous-event.v1"] = "local-anonymous-event.v1"
    event_id: str = Field(pattern=r"^anon_evt_[0-9a-f]{32}$")
    session_id: str = Field(pattern=r"^anon_session_[0-9a-f]{32}$")
    name: AnonymousEventName
    occurred_at: datetime
    app_version: str = Field(min_length=1, max_length=80)
    properties: AnonymousEventProperties = Field(default_factory=AnonymousEventProperties)


class AnonymousMetricCounters(StrictContract):
    sessions: int = Field(ge=0)
    successful_imports: int = Field(ge=0)
    imported_item_count: int = Field(ge=0)
    analysis_started: int = Field(ge=0)
    analysis_succeeded: int = Field(ge=0)
    graph_opened: int = Field(ge=0)
    viewing_created: int = Field(ge=0)
    explore_used: int = Field(ge=0)
    ask_used: int = Field(ge=0)
    app_reopened: int = Field(ge=0)


class AnonymousMetricsExport(StrictContract):
    format_version: Literal["anonymous-metrics-export.v1"] = "anonymous-metrics-export.v1"
    consent: Literal["explicit_user_export"]
    export_id: str = Field(pattern=r"^anon_export_[0-9a-f]{32}$")
    generated_at: datetime
    window_started_at: datetime
    window_ended_at: datetime
    app_version: str = Field(min_length=1, max_length=80)
    platform_family: Literal["windows", "macos", "linux", "container", "other"]
    counters: AnonymousMetricCounters
    failure_categories: dict[str, int] = Field(default_factory=dict, max_length=20)

    @model_validator(mode="after")
    def validate_window_and_failures(self):
        if self.window_started_at > self.window_ended_at:
            raise ValueError("metrics window start must not be after its end")
        if any(not key or value < 0 for key, value in self.failure_categories.items()):
            raise ValueError("failure category counts must be non-negative")
        return self
