import unittest
from datetime import datetime, timezone

from pydantic import ValidationError

from app.contracts.analysis_v2 import (
    AnalysisEvaluationCase,
    AnalysisEvaluationDataset,
    AnalysisV2Input,
    AnalysisV2Output,
)
from app.contracts.anonymous_events import AnonymousMetricsExport, LocalAnonymousEvent


FILM_ID = "film_" + "1" * 32


class ProductContractTests(unittest.TestCase):
    def test_analysis_v2_accepts_traceable_assertions_without_hidden_reasoning(self):
        output = AnalysisV2Output.model_validate({
            "subject_film_id": FILM_ID,
            "summary": "A concise user-facing genealogy summary.",
            "assertions": [{
                "predicate": "INFLUENCED_BY",
                "target": {
                    "entity_type": "film",
                    "provider": "imdb.title",
                    "external_id": "tt0000001",
                    "display_name": "Reference Film",
                    "release_year": 1960,
                },
                "rationale": "The later film reuses the earlier film's spatial staging.",
            }],
        })

        self.assertEqual(output.schema_version, "analysis-output.v2")
        self.assertEqual(output.assertions[0].source_scope, "inferred")
        with self.assertRaises(ValidationError):
            AnalysisV2Output.model_validate({
                **output.model_dump(mode="json"),
                "chain_of_thought": "must never be accepted",
            })

    def test_analysis_v2_rejects_untraceable_film_and_duplicate_assertions(self):
        assertion = {
            "predicate": "REMAKE_OF",
            "target": {"entity_type": "film", "display_name": "Unknown Film"},
            "rationale": "A concise explanation.",
        }
        with self.assertRaisesRegex(ValidationError, "release_year"):
            AnalysisV2Output.model_validate({
                "subject_film_id": FILM_ID,
                "summary": "Summary",
                "assertions": [assertion],
            })

        assertion["target"]["release_year"] = 1970
        with self.assertRaisesRegex(ValidationError, "duplicate"):
            AnalysisV2Output.model_validate({
                "subject_film_id": FILM_ID,
                "summary": "Summary",
                "assertions": [assertion, assertion],
            })

    def test_evaluation_dataset_requires_30_to_50_cases_and_identity_coverage(self):
        tags = ["same_title", "cold_title", "non_latin_title", "cross_decade"]
        cases = [self._evaluation_case(index, tags[index] if index < 4 else "influence") for index in range(30)]
        dataset = AnalysisEvaluationDataset.model_validate({
            "dataset_id": "genealogy-v2-baseline",
            "description": "Synthetic contract fixture without user library data.",
            "cases": cases,
        })

        self.assertEqual(len(dataset.cases), 30)
        with self.assertRaises(ValidationError):
            AnalysisEvaluationDataset.model_validate({
                "dataset_id": "too-small",
                "description": "Too small",
                "cases": cases[:29],
            })

    def test_local_anonymous_event_rejects_library_identifiers_and_paths(self):
        event = LocalAnonymousEvent.model_validate({
            "event_id": "anon_evt_" + "2" * 32,
            "session_id": "anon_session_" + "3" * 32,
            "name": "library_import_completed",
            "occurred_at": "2026-08-21T00:00:00Z",
            "app_version": "0.1.0",
            "properties": {"result": "success", "item_count": 12, "offline_mode": True},
        })
        self.assertEqual(event.properties.item_count, 12)

        payload = event.model_dump(mode="json")
        payload["properties"]["media_path"] = "D:/private/library"
        with self.assertRaises(ValidationError):
            LocalAnonymousEvent.model_validate(payload)

    def test_anonymous_export_contains_aggregates_only_and_requires_explicit_consent(self):
        now = datetime.now(timezone.utc)
        payload = {
            "consent": "explicit_user_export",
            "export_id": "anon_export_" + "4" * 32,
            "generated_at": now,
            "window_started_at": now,
            "window_ended_at": now,
            "app_version": "0.1.0",
            "platform_family": "windows",
            "counters": {
                "sessions": 1,
                "successful_imports": 1,
                "imported_item_count": 12,
                "analysis_started": 0,
                "analysis_succeeded": 0,
                "graph_opened": 0,
                "viewing_created": 1,
                "explore_used": 0,
                "ask_used": 0,
                "app_reopened": 0,
            },
        }
        exported = AnonymousMetricsExport.model_validate(payload)
        self.assertEqual(exported.counters.imported_item_count, 12)
        with self.assertRaises(ValidationError):
            AnonymousMetricsExport.model_validate({**payload, "consent": "automatic"})

    @staticmethod
    def _evaluation_case(index: int, tag: str) -> dict:
        language = "zh" if index % 2 == 0 else "en"
        return AnalysisEvaluationCase(
            case_id=f"eval_case_{index:02d}",
            language=language,
            tags=[tag],
            input=AnalysisV2Input(
                film_id=f"film_{index:032x}",
                canonical_title=f"Synthetic Film {index}",
                release_year=1950 + index,
            ),
            expected_assertions=[],
            annotator_count=2,
            adjudication_status="adjudicated",
        ).model_dump(mode="json")


if __name__ == "__main__":
    unittest.main()
