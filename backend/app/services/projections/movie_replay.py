from collections import Counter
from typing import Optional

from app.models import EventRecord, Movie
from app.services.projections.movie_fields import (
    ARTWORK_SELECTION_FIELDS,
    EXTERNAL_SCORE_FIELDS,
    FILE_OBSERVED_FIELDS,
    METADATA_MATCH_FIELDS,
    MOVIE_DISCOVERED_FIELDS,
    NFO_METADATA_FIELDS,
    NFO_SIGNATURE_FIELDS,
    PROJECTABLE_EVENT_TYPES,
    event_movie_id,
    values_from_payload,
)


class MovieEventReplayer:
    """In-memory movie event replay shared by dry-run projections."""

    def replay(
        self,
        *,
        events: list[EventRecord],
        projected_movies: dict[str, dict],
        projectable_event_types: Optional[set[str]] = None,
        max_skipped_events: int = 20,
    ) -> dict:
        enabled_projectable_event_types = projectable_event_types or PROJECTABLE_EVENT_TYPES
        touched_movie_ids: set[str] = set()
        unsupported_event_types: Counter[str] = Counter()
        projectable_events = 0
        skipped_projectable_events = 0
        skipped_events: list[dict] = []
        missing_payload: list[dict] = []

        for event in events:
            if event.type not in enabled_projectable_event_types:
                unsupported_event_types[event.type] += 1
                continue
            projectable_events += 1
            touched_id = event_movie_id(event.payload or {}, event.aggregate_id)
            if not touched_id:
                skipped_projectable_events += 1
                self._record_skipped_event(
                    skipped_events,
                    missing_payload,
                    event,
                    "Missing movie aggregate ID",
                    max_skipped_events,
                )
                continue
            state = projected_movies.get(touched_id)
            if state is None:
                if event.type == "MovieDiscovered":
                    state = self.state_from_discovered(event)
                    if state is None:
                        skipped_projectable_events += 1
                        self._record_skipped_event(
                            skipped_events,
                            missing_payload,
                            event,
                            "MovieDiscovered payload is missing id, title, or year",
                            max_skipped_events,
                        )
                        continue
                    projected_movies[touched_id] = state
                else:
                    skipped_projectable_events += 1
                    self._record_skipped_event(
                        skipped_events,
                        missing_payload,
                        event,
                        "No projected movie state exists for this event",
                        max_skipped_events,
                    )
                    continue
            skip_reason = self.apply_event(state, event)
            if skip_reason:
                skipped_projectable_events += 1
                self._record_skipped_event(
                    skipped_events,
                    missing_payload,
                    event,
                    skip_reason,
                    max_skipped_events,
                )
                continue
            touched_movie_ids.add(touched_id)

        return {
            "projectable_events": projectable_events,
            "skipped_projectable_events": skipped_projectable_events,
            "skipped_events": skipped_events,
            "missing_payload": missing_payload,
            "unsupported_events": sum(unsupported_event_types.values()),
            "unsupported_event_types": dict(sorted(unsupported_event_types.items())),
            "touched_movie_ids": touched_movie_ids,
        }

    def apply_event(self, state: dict, event: EventRecord) -> Optional[str]:
        payload = event.payload or {}
        if event.type == "MovieDiscovered":
            state.update(self.discovered_payload(payload, event))
        elif event.type == "MovieFileObserved":
            return self._apply_payload_fields(
                state,
                payload,
                FILE_OBSERVED_FIELDS,
                "MovieFileObserved payload is missing current payload",
            )
        elif event.type == "MovieMetadataParsedFromNfo":
            return self._apply_payload_fields(
                state,
                payload,
                (*NFO_METADATA_FIELDS, *NFO_SIGNATURE_FIELDS),
                "MovieMetadataParsedFromNfo payload is missing current payload",
            )
        elif event.type == "MovieIgnored":
            state["library_status"] = "ignored"
            state["missing_since"] = None
        elif event.type == "MovieMarkedMissing":
            if state.get("library_status") not in {"ignored", "reverted"}:
                state["library_status"] = "missing"
                state["missing_since"] = payload.get("missing_since")
        elif event.type == "MovieRestored":
            if state.get("library_status") != "ignored":
                state["library_status"] = "available"
                state["missing_since"] = None
        elif event.type == "RootVideoOrganizationReverted":
            state["library_status"] = "reverted"
            state["missing_since"] = None
        elif event.type == "MovieStateBackfilled":
            return self._apply_payload_fields(
                state,
                payload,
                tuple(Movie.model_fields),
                "MovieStateBackfilled payload is missing current payload",
            )
        elif event.type == "MetadataMatched":
            return self._apply_payload_fields(
                state,
                payload,
                METADATA_MATCH_FIELDS,
                "MetadataMatched payload is missing current payload",
            )
        elif event.type == "ArtworkSelected":
            return self._apply_payload_fields(
                state,
                payload,
                ARTWORK_SELECTION_FIELDS,
                "ArtworkSelected payload is missing current payload",
            )
        elif event.type in {"MovieStateRestored", "MetadataRestored", "ArtworkSelectionRestored"}:
            return self._apply_restored_fields(state, payload)
        elif event.type == "AnalysisStarted":
            state["analysis_status"] = "processing"
        elif event.type == "AnalysisCompleted":
            state["analysis_status"] = "completed"
            state["analysis_data"] = payload.get("analysis_data")
            state["micro_genre"] = payload.get("micro_genre")
            state["micro_genre_definition"] = payload.get("micro_genre_definition")
        elif event.type == "AnalysisFailed":
            state["analysis_status"] = "failed"
        elif event.type == "ExternalScoresRefreshed":
            return self._apply_payload_fields(
                state,
                payload,
                EXTERNAL_SCORE_FIELDS,
                "ExternalScoresRefreshed payload is missing current payload",
            )
        return None

    def state_from_discovered(self, event: EventRecord) -> Optional[dict]:
        payload = event.payload or {}
        movie_id = payload.get("movie_id") or payload.get("id") or event.aggregate_id
        if not movie_id or not payload.get("title") or payload.get("year") is None:
            return None
        state = {
            "id": movie_id,
            "title": payload["title"],
            "year": payload["year"],
            "library_status": "available",
            "analysis_status": "pending",
            "scrape_status": "pending",
        }
        state.update(self.discovered_payload(payload, event))
        return state

    def discovered_payload(self, payload: dict, event: EventRecord) -> dict:
        movie_id = payload.get("movie_id") or payload.get("id") or event.aggregate_id
        return {
            key: value
            for key, value in {
                **payload,
                "id": movie_id,
            }.items()
            if (key in MOVIE_DISCOVERED_FIELDS or key == "id") and value is not None
        }

    def _apply_payload_fields(
        self,
        state: dict,
        payload: dict,
        fields: tuple[str, ...],
        missing_reason: str,
    ) -> Optional[str]:
        values = values_from_payload(payload, fields)
        if not values:
            return missing_reason
        state.update(values)
        return None

    def _apply_restored_fields(self, state: dict, payload: dict) -> Optional[str]:
        restored_fields = payload.get("restored_fields")
        if not isinstance(restored_fields, list):
            return "Restored event payload is missing restored_fields"
        for item in restored_fields:
            if not isinstance(item, dict):
                continue
            field = item.get("field")
            if isinstance(field, str) and field in Movie.model_fields:
                state[field] = item.get("restored")
        return None

    def _record_skipped_event(
        self,
        skipped_events: list[dict],
        missing_payload: list[dict],
        event: EventRecord,
        reason: str,
        max_skipped_events: int,
    ):
        item = {
            "event_id": event.id,
            "type": event.type,
            "aggregate_id": event.aggregate_id,
            "reason": reason,
        }
        if len(skipped_events) < max_skipped_events:
            skipped_events.append(item)
        if "missing" in reason.lower():
            missing_payload.append(item)


movie_event_replayer = MovieEventReplayer()
