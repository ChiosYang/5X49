"""Resumable indexing and restoration with explicit fake vectors, no model quality claim."""
import json
import sqlite3
import unittest

from app.services.search_index import SearchIndexStore
from app.services.semantic_search import ContentDocument, ContentSource, ProviderSpec, SemanticError


SPEC = ProviderSpec("synthetic/index", "test.v1", 3)


def doc(number, text=None):
    return ContentDocument("film_" + f"{number:032x}", "Public Film " + str(number), (),
                           (ContentSource("overview", text or f"Public test story number {number}.", "tmdb"),))


class Provider:
    spec = SPEC

    def __init__(self):
        self.calls = []
        self.after = lambda: None

    def embed(self, texts, *, query):
        self.calls.append((tuple(texts), query))
        self.after()
        return [[1., 0., 0.] for _ in texts]


class SearchIndexTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.addCleanup(self.db.close)
        self.store = SearchIndexStore(self.db, clock=lambda: 1000)
        self.provider = Provider()
        self.docs = tuple(doc(i) for i in range(1, 7))

    def finish(self, documents=None):
        state = self.store.begin(documents or self.docs, SPEC)
        while state["state"] != "complete":
            state = self.store.step(state["id"], self.provider)
        return state

    def test_batches_survive_reopen_without_reembedding_acknowledged_inputs(self):
        state = self.store.begin(self.docs, SPEC)
        first = self.store.step(state["id"], self.provider)
        self.assertEqual(first["remaining_chunks"], 2)
        restarted = SearchIndexStore(self.db)
        resumed = restarted.begin(self.docs, SPEC)
        self.assertEqual(resumed["id"], state["id"])
        done = restarted.step(resumed["id"], self.provider)
        self.assertEqual(done["state"], "complete")
        self.assertEqual(sum(len(c[0]) for c in self.provider.calls), 6)
        self.assertEqual(len(restarted.read(SPEC)[0]), 6)

    def test_cancel_inflight_retains_vectors_and_resume_has_no_duplicate_call(self):
        state = self.store.begin(self.docs, SPEC)
        self.provider.after = lambda: self.store.cancel(state["id"], SPEC)
        cancelled = self.store.step(state["id"], self.provider)
        self.assertEqual(cancelled["state"], "cancelled")
        self.assertEqual(cancelled["remaining_chunks"], 2)
        self.provider.after = lambda: None
        self.store.resume(state["id"], SPEC)
        self.assertEqual(self.store.step(state["id"], self.provider)["state"], "complete")
        self.assertEqual(sum(len(c[0]) for c in self.provider.calls), 6)

    def test_changed_document_only_is_encoded_old_generation_remains_usable_until_commit(self):
        self.finish()
        previous_revision = self.store.meta("revision")
        calls = len(self.provider.calls)
        changed = (*self.docs[:5], doc(6, "A changed public story."))
        state = self.store.begin(changed, SPEC)
        self.assertEqual(state["remaining_chunks"], 1)
        self.assertEqual(self.store.read(SPEC)[2], previous_revision)
        self.store.step(state["id"], self.provider)
        self.assertEqual(len(self.provider.calls), calls + 1)
        self.assertEqual(self.provider.calls[-1][0], ("A changed public story.",))
        self.assertNotEqual(self.store.read(SPEC)[2], previous_revision)

    def test_removed_films_and_empty_generation_publish_without_reencoding(self):
        self.finish()
        calls = len(self.provider.calls)
        state = self.store.begin(self.docs[:2], SPEC)
        self.store.step(state["id"], self.provider)
        self.assertEqual(len(self.store.read(SPEC)[0]), 2)
        empty = self.store.begin((), SPEC)
        self.store.step(empty["id"], self.provider)
        self.assertEqual(self.store.read(SPEC)[0], ())
        self.assertEqual(len(self.provider.calls), calls)

    def test_model_change_never_reuses_old_vectors(self):
        self.finish()
        changed = ProviderSpec(SPEC.name, "different-revision", 3)
        with self.assertRaisesRegex(SemanticError, "search_index_stale"):
            self.store.read(changed)
        self.assertEqual(self.store.begin(self.docs, changed)["remaining_chunks"], 6)

    def test_malformed_vectors_never_replace_active_generation(self):
        self.finish()
        revision = self.store.meta("revision")
        state = self.store.begin((doc(1, "A changed plot."),), SPEC)
        self.provider.embed = lambda *args, **kwargs: [[float("nan"), 0., 1.]]
        with self.assertRaisesRegex(SemanticError, "invalid_vector"):
            self.store.step(state["id"], self.provider)
        self.assertEqual(self.store.read(SPEC)[2], revision)

    def test_full_path_screening_happens_before_provider(self):
        for text in ("Movies//Private.mkv", "~/Movies/private.mkv", "Movies\\\\My Private Film.mkv"):
            with self.subTest(text=text), self.assertRaisesRegex(SemanticError, "private_input"):
                self.store.begin((doc(1, text),), SPEC)
        self.assertEqual(self.provider.calls, [])

    def test_slash_title_boundary_remains_valid_with_another_film(self):
        films = (doc(1, "a" * 498 + "Face/Off"), doc(2, "A story involving V/H/S and 9/11."))
        self.finish(films)
        self.assertEqual(len(self.store.read(SPEC)[0]), 2)

    def test_cancel_before_dispatch_and_interrupted_job_cannot_be_blindly_resumed(self):
        state = self.store.begin(self.docs, SPEC)
        self.assertEqual(self.store.step(state["id"], self.provider, cancelled=lambda: True)["state"], "cancelled")
        self.assertEqual(self.provider.calls, [])
        with self.db:
            self.db.execute("UPDATE search_index_jobs SET state='working' WHERE id=?", (state["id"],))
        with self.assertRaisesRegex(SemanticError, "search_index_job_busy"):
            self.store.resume(state["id"], SPEC)

    def test_snapshots_expire_and_bind_question_without_inference(self):
        token = self.store.save_snapshot("family reunion", {"ranked": [self.docs[0].film_id], "query_vector": [1, 0, 0]})
        self.assertEqual(self.store.snapshot(token, "family reunion")["ranked"], [self.docs[0].film_id])
        with self.assertRaisesRegex(SemanticError, "search_snapshot_invalid"):
            self.store.snapshot(token, "another query")
        self.store.clock = lambda: 1000000
        with self.assertRaisesRegex(SemanticError, "search_snapshot_expired"):
            self.store.snapshot(token, "family reunion")
        self.assertEqual(self.provider.calls, [])

    def test_modified_cache_document_is_revalidated_before_read(self):
        self.finish()
        raw = json.loads(self.db.execute("SELECT document FROM search_index_active LIMIT 1").fetchone()[0])
        raw["sources"][0]["text"] = "Movies//My Private Film.mkv"
        with self.db:
            self.db.execute("UPDATE search_index_active SET document=? WHERE film_id=?", (json.dumps(raw), raw["film_id"]))
        with self.assertRaises(SemanticError):
            self.store.read(SPEC)


if __name__ == "__main__":
    unittest.main()
