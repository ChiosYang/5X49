import assert from "node:assert/strict";
import test from "node:test";
import { metadataActionError, reviewSession } from "./metadata-review.ts";

test("empty TMDB searches have actionable localized feedback; other failures retain their cause", () => {
  assert.equal(metadataActionError(new Error("No TMDB matches found"), "Failed", "Check title/year"), "Check title/year");
  assert.equal(metadataActionError(new Error("Service unavailable"), "Failed", "No match"), "Service unavailable");
  assert.equal(metadataActionError(null, "Failed", "No match"), "Failed");
});

const films = [{ id: "a" }, { id: "b" }, { id: "c" }];
test("skipping the first film advances without completing or reducing pending work", () => {
  const result = reviewSession(films, ["a"], []);
  assert.deepEqual(result.available, [films[1], films[2]]);
  assert.equal(result.pending.length, 3);
  assert.equal(result.skippedCount, 1);
});
test("stale library data cannot reintroduce a successfully confirmed film", () => {
  const result = reviewSession(films, ["a"], ["b"]);
  assert.deepEqual(result.available, [films[2]]);
  assert.deepEqual(result.pending, [films[0], films[2]]);
});
test("a pass containing only skipped films stays pending and can be revisited", () => {
  const result = reviewSession(films, ["a", "c"], ["b"]);
  assert.equal(result.available.length, 0);
  assert.equal(result.pending.length, 2);
  assert.equal(result.skippedCount, 2);
  assert.deepEqual(reviewSession(films, [], ["b"]).available, [films[0], films[2]]);
});
test("refreshed data that drops a skipped film does not leave phantom pending work", () => {
  assert.deepEqual(reviewSession([], ["a"], ["b"]), { pending: [], available: [], skippedCount: 0 });
});
