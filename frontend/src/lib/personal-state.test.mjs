import assert from "node:assert/strict";
import test from "node:test";
import { personalStateChanges } from "./personal-state.ts";
import { normalizeLibrarySearch } from "./library-search.ts";

test("personal edits send only changed fields, preserving concurrent watched/favorite state", () => {
  assert.deepEqual(personalStateChanges({ rating: 4, notes: "old", watched: true }, { rating: 4, notes: "new" }), { notes: "new" });
  assert.deepEqual(personalStateChanges({ rating: 4, notes: "old" }, { rating: 5, notes: "old" }), { rating: 5 });
});

test("rating and notes can be cleared explicitly while unchanged empty values are omitted", () => {
  assert.deepEqual(personalStateChanges({ rating: 4, notes: "old" }, { rating: null, notes: "  " }), { rating: null, notes: null });
  assert.deepEqual(personalStateChanges({}, { rating: null, notes: "" }), {});
  assert.deepEqual(personalStateChanges({}, { rating: 1, notes: "line 1\nline 2" }), { rating: 1, notes: "line 1\nline 2" });
});

test("search normalizes repeated/empty query parameters and enforces the API length bound", () => {
  assert.equal(normalizeLibrarySearch(["  王家卫  ", "ignored"]), "王家卫");
  assert.equal(normalizeLibrarySearch(undefined), "");
  assert.equal(normalizeLibrarySearch("  "), "");
  assert.equal(normalizeLibrarySearch("x".repeat(210)).length, 200);
  assert.equal(normalizeLibrarySearch("a&b ? /"), "a&b ? /");
});
