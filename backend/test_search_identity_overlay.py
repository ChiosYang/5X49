"""Synthetic credit crosswalks: source immutability, real SQL and homonyms."""
from copy import deepcopy
from hashlib import sha256
import json
import unittest
from unittest.mock import patch

from sqlmodel import create_engine

from app.evaluation.search_corpus import CorpusFilm, documents, seed_projection_database
from app.evaluation.search_identity_overlay import derive_identity_corpus
from app.services.search_local import LocalSearch
from app.services.semantic_search import SemanticError


class IdentityOverlayTests(unittest.TestCase):
    def setUp(self):
        self.local_id = "person_" + "a" * 16
        self.target = "Q900001"
        self.unrelated = "Q900002"
        def fact(value):
            return {"status": "accepted", "value": value, "sources": ["synthetic-credit"], "reason": "Synthetic test fact"}
        def film(i, person):
            return {"id": "film_" + f"{i:032x}", "title_en": f"Synthetic Film {i}", "title_zh": None,
                "titles": [{"locale": "en", "value": f"Synthetic Film {i}"}], "document_text": "A family reconnects.",
                "year": fact(2000 + i), "minutes": fact(100), "countries": fact(["Japan"]),
                "genres": fact(["Drama"]), "directors": fact([person]), "director_names": fact(["Shared Director"])}
        self.payload = {"version": "synthetic-public-corpus.v1", "films": [film(1, self.target), film(2, self.local_id),
            film(3, self.local_id), film(4, self.unrelated)], "sources": [{"id": "synthetic-credit", "url": "https://example.org/credit"}]}
        self.raw = json.dumps(self.payload).encode()
        self.manifest = {"version": "public-person-identity-overlay.v1", "parent_sha256": sha256(self.raw).hexdigest(),
            "verification": "reviewed-source-credit-links", "links": [{"source_id": self.local_id, "target_id": self.target,
            "evidence": [{"film_id": self.payload["films"][i]["id"], "source_ref": "synthetic-credit",
                "film_qid": f"Q{800000+i}", "director_qid": self.target,
                "reference": f"https://www.wikidata.org/wiki/Q{800000+i}#P57", "retrieved": "2026-10-26"}
                for i in (1, 2)]}]}
        self.network = patch("socket.socket.connect", side_effect=AssertionError("Offline identity test"))
        self.network.start(); self.addCleanup(self.network.stop)

    def seed(self, payload, films):
        engine = create_engine("sqlite://"); self.addCleanup(engine.dispose)
        seed_projection_database(engine, payload, films)
        return LocalSearch(engine)

    def test_explicit_links_restore_filter_coverage_and_keep_same_name_other_person_separate(self):
        original = tuple(CorpusFilm.model_validate(f) for f in self.payload["films"])
        before = self.seed(self.payload, original)
        plan = before.interpret("films directed by Shared Director after 2000")
        self.assertEqual(plan["status"], "needs_clarification")
        target_id = "person_" + sha256(self.target.encode()).hexdigest()[:32]
        from app.contracts.bound_search_plan import SearchPlan
        hard = SearchPlan.model_validate(plan["plan"])
        original_result = before.executor.query(hard, people_ids={"0": target_id})
        self.assertEqual(original_result["results"]["total"], 1)
        derived, films = derive_identity_corpus(self.raw, self.manifest)
        after = self.seed(derived, films)
        result = after.executor.query(hard, people_ids={"0": target_id})
        self.assertEqual({r["film"]["id"] for r in result["results"]["items"]}, {f["id"] for f in self.payload["films"][:3]})
        choices = after.interpret("films directed by Shared Director after 2000")
        self.assertEqual(choices["status"], "needs_clarification")
        self.assertEqual(len(choices["issues"][0]["candidates"]), 2)
        self.assertEqual(documents(films), documents(original))
        self.assertEqual(json.loads(self.raw), self.payload)
        self.assertEqual(derived["films"][1]["source_director_ids"], [self.local_id])
        self.assertNotIn("identity_overlay", self.payload)

    def test_all_source_credits_need_matching_external_evidence(self):
        for mutate in (lambda m: m["links"][0]["evidence"].pop(),
                       lambda m: m["links"][0]["evidence"].append(deepcopy(m["links"][0]["evidence"][0])),
                       lambda m: m["links"][0]["evidence"][0].update(director_qid=self.unrelated),
                       lambda m: m["links"][0]["evidence"][0].update(source_ref="not-in-parent"),
                       lambda m: m["links"][0]["evidence"][0].update(reference="https://example.org/claim"),
                       lambda m: m["links"][0].update(source_id=self.target),
                       lambda m: m["links"][0].update(target_id="Q999999"),
                       lambda m: m["links"].append(deepcopy(m["links"][0])),
                       lambda m: m.update(parent_sha256="0" * 64),
                       lambda m: m.update(qrels=[])):
            manifest = deepcopy(self.manifest); mutate(manifest)
            with self.assertRaises(SemanticError): derive_identity_corpus(self.raw, manifest)
        self.assertEqual(json.loads(self.raw), self.payload)

    def test_no_name_based_mapping_or_unknown_fact_promotion(self):
        payload = deepcopy(self.payload)
        payload["films"][1]["directors"].update(status="unknown", value=[])
        raw = json.dumps(payload).encode(); manifest = deepcopy(self.manifest)
        manifest["parent_sha256"] = sha256(raw).hexdigest()
        with self.assertRaises(SemanticError): derive_identity_corpus(raw, manifest)
        # Equal text alone is never input to the mapping algorithm.
        manifest = deepcopy(self.manifest); manifest["links"][0]["source_id"] = "Shared Director"
        with self.assertRaises(SemanticError): derive_identity_corpus(self.raw, manifest)

    def test_derivation_is_deterministic_and_cannot_silently_reapply_to_changed_parent(self):
        a, _ = derive_identity_corpus(self.raw, self.manifest)
        b, _ = derive_identity_corpus(self.raw, self.manifest)
        self.assertEqual(a, b)
        with self.assertRaises(SemanticError): derive_identity_corpus(json.dumps(a).encode(), self.manifest)


if __name__ == "__main__":
    unittest.main()
