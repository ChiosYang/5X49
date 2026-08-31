import assert from "node:assert/strict";
import test from "node:test";

import { parseMetadataSearchInput, parseTmdbId } from "./metadata-search.ts";

test("treats only a direct ID or explicit TMDB movie URL as a TMDB ID", () => {
  assert.equal(parseTmdbId("603"), 603);
  assert.equal(parseTmdbId("https://www.themoviedb.org/movie/603-the-matrix"), 603);
  assert.equal(parseTmdbId("Inception 2010"), null);
  assert.equal(parseTmdbId("Movie 603 cut"), null);
});

test("extracts a release year from a title search", () => {
  assert.deepEqual(parseMetadataSearchInput("Inception 2010"), {
    query: "Inception",
    year: 2010,
  });
});
