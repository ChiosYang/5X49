import assert from "node:assert/strict";
import test from "node:test";

import { isFilmResourceId } from "./resource-id.ts";

test("accepts canonical Film resource IDs", () => {
  assert.equal(isFilmResourceId("film_0123456789abcdef0123456789abcdef"), true);
});

test("rejects static library routes and malformed Film IDs", () => {
  for (const value of [
    "manage",
    "activity",
    "not-a-film",
    "film_0123456789abcdef0123456789abcde",
    "film_0123456789abcdef0123456789abcdef0",
    "film_0123456789ABCDEF0123456789ABCDEF",
    "film_01234567-89ab-cdef-0123-456789abcdef",
  ]) {
    assert.equal(isFilmResourceId(value), false, value);
  }
});
