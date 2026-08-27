import tempfile
import unittest
from pathlib import Path

from sqlmodel import SQLModel, Session, create_engine

from app.canonical_models import Concept, ConceptAlias, ExternalIdentity, Film, GraphEntity
from app.contracts.analysis_v2 import AnalysisV2Output
from app.models import EventRecord  # noqa: F401 - registers the full SQLModel graph
from app.services.analysis_critic import ANALYSIS_CRITIC_VERSION, AnalysisPolicyCritic


SUBJECT_ID = "film_11111111111111111111111111111111"
TARGET_ID = "film_22222222222222222222222222222222"
CONCEPT_A = "concept_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
CONCEPT_B = "concept_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"


class AnalysisPolicyCriticTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.engine = create_engine(f"sqlite:///{Path(self._tmp.name) / 'library.db'}")
        SQLModel.metadata.create_all(self.engine)
        with Session(self.engine) as session:
            self._film(session, SUBJECT_ID, "Subject", 2000)
            self._film(session, TARGET_ID, "Target", 1990)
            session.add(
                ExternalIdentity(
                    id="identity_target",
                    entity_id=TARGET_ID,
                    provider="tmdb.movie",
                    external_id="42",
                    identity_status="active",
                    provenance_kind="curated",
                    provenance_ref="rule:test",
                )
            )
            for concept_id, name in ((CONCEPT_A, "Dream Logic"), (CONCEPT_B, "Oneiric")):
                session.add(GraphEntity(id=concept_id, entity_type="concept"))
                session.add(
                    Concept(
                        id=concept_id,
                        kind="theme",
                        canonical_key=f"theme:{concept_id}",
                        canonical_name=name,
                    )
                )
                session.add(
                    ConceptAlias(
                        id=f"alias_{concept_id[-8:]}",
                        concept_id=concept_id,
                        locale="und",
                        alias="Dreamlike",
                        normalized_alias="dreamlike",
                        provenance_ref="rule:test",
                    )
                )
            session.commit()

    def tearDown(self):
        self.engine.dispose()
        self._tmp.cleanup()

    @staticmethod
    def _film(session: Session, film_id: str, title: str, year: int) -> None:
        session.add(GraphEntity(id=film_id, entity_type="film"))
        session.add(Film(id=film_id, canonical_title=title, release_year=year))

    @staticmethod
    def _output(assertions: list[dict]) -> AnalysisV2Output:
        return AnalysisV2Output.model_validate(
            {
                "subject_film_id": SUBJECT_ID,
                "summary": "Bounded summary",
                "assertions": assertions,
            }
        )

    @staticmethod
    def _candidate(target: dict, **overrides) -> dict:
        return {
            "predicate": overrides.pop("predicate", "INFLUENCED_BY"),
            "target": target,
            "rationale": overrides.pop("rationale", "Bounded rationale"),
            **overrides,
        }

    def _evaluate(self, output: AnalysisV2Output, **kwargs):
        with Session(self.engine) as session:
            return AnalysisPolicyCritic().evaluate(
                session,
                subject_film_id=SUBJECT_ID,
                output=output,
                **kwargs,
            )

    def test_identity_title_and_year_conflicts_are_rejected_before_persistence(self):
        output = self._output(
            [
                self._candidate(
                    {
                        "entity_type": "film",
                        "provider": "tmdb.movie",
                        "external_id": "42",
                        "display_name": "Wrong title",
                        "release_year": 1991,
                    }
                )
            ]
        )
        result = self._evaluate(output)
        self.assertEqual(result.policy_version, ANALYSIS_CRITIC_VERSION)
        self.assertEqual(result.accepted_keys, ())
        self.assertEqual(result.rejections[0].reason_code, "identity_conflict")

    def test_ambiguous_concept_alias_and_wrong_predicate_type_are_rejected(self):
        output = self._output(
            [
                self._candidate(
                    {"entity_type": "concept", "display_name": "Dreamlike"},
                    predicate="HAS_THEME",
                ),
                self._candidate(
                    {"entity_type": "film", "entity_id": TARGET_ID},
                    predicate="HAS_THEME",
                ),
            ]
        )
        result = self._evaluate(output)
        self.assertEqual(
            [(item.reason_code, item.policy_code) for item in result.rejections],
            [
                ("ambiguous_reference", "ambiguous_name_or_alias"),
                ("predicate_type_mismatch", "predicate_type_mismatch"),
            ],
        )

    def test_semantic_duplicates_qualifiers_self_reference_and_limit_are_bounded(self):
        assertions = [
            self._candidate({"entity_type": "film", "entity_id": TARGET_ID}),
            self._candidate(
                {"entity_type": "film", "display_name": "Target", "release_year": 1990}
            ),
            self._candidate(
                {"entity_type": "film", "entity_id": SUBJECT_ID},
                predicate="VISUALLY_SIMILAR_TO",
            ),
            self._candidate(
                {"entity_type": "film", "entity_id": TARGET_ID},
                predicate="REMAKE_OF",
                qualifiers={"relationship_type": "unnecessary"},
            ),
        ]
        for index in range(8):
            film_id = f"film_{index + 3:032x}"
            with Session(self.engine) as session:
                self._film(session, film_id, f"Extra {index}", 1980 + index)
                session.commit()
            assertions.append(
                self._candidate(
                    {"entity_type": "film", "entity_id": film_id},
                    predicate="VISUALLY_SIMILAR_TO",
                )
            )
        result = self._evaluate(self._output(assertions))
        policy_codes = {item.policy_code for item in result.rejections}
        self.assertIn("semantic_duplicate", policy_codes)
        self.assertIn("self_reference", policy_codes)
        self.assertIn("qualifier_not_allowed", policy_codes)
        self.assertIn("assertion_limit_exceeded", policy_codes)
        self.assertEqual(len(result.accepted_keys), 8)

    def test_preferred_evidence_is_reported_without_inventing_a_hard_requirement(self):
        result = self._evaluate(
            self._output([self._candidate({"entity_type": "film", "entity_id": TARGET_ID})])
        )
        self.assertEqual(result.accepted_keys, ("a000",))
        self.assertEqual(result.warnings, ("a000:preferred_evidence_missing",))


if __name__ == "__main__":
    unittest.main()
