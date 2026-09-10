import assert from "node:assert/strict";
import test from "node:test";

import { changeDnaQuery, dnaHref, isDnaCacheKey, parseDnaQuery } from "./cinema-dna.ts";
import { diaryViewFromQuery } from "./diary.ts";
import { API } from "./api.ts";

test("DNA URL round-trips metric, dimension, selection and both pages", () => {
  const query = { dimension: "country", metric: "preference", facet: "JP", offset: 20, contributorsOffset: 40 };
  assert.deepEqual(parseDnaQuery(new URL(dnaHref(query), "https://local.test").searchParams), query);
  assert.equal(dnaHref(parseDnaQuery(new URLSearchParams())), "/diary?view=dna");
});

test("DNA defaults reject malformed offsets and dimension or metric values", () => {
  const query = parseDnaQuery(new URLSearchParams("dimension=style&metric=rating&offset=-1&contributors_offset=Infinity"));
  assert.deepEqual(query, { dimension: "genre", metric: "exposure", facet: null, offset: 0, contributorsOffset: 0 });
  assert.equal(parseDnaQuery(new URLSearchParams("offset=20junk")).offset, 0);
  assert.equal(parseDnaQuery(new URLSearchParams("offset=9007199254740992")).offset, 0);
});

test("changing dimensions clears stale category and page state, metric keeps category", () => {
  const query = { dimension: "country", metric: "exposure", facet: "JP", offset: 20, contributorsOffset: 40 };
  assert.deepEqual(changeDnaQuery(query, { dimension: "person" }), { ...query, dimension: "person", facet: null, offset: 0, contributorsOffset: 0 });
  assert.deepEqual(changeDnaQuery(query, { metric: "preference" }), { ...query, metric: "preference", offset: 0, contributorsOffset: 0 });
  assert.equal(changeDnaQuery(query, { offset: 40 }).facet, null);
  assert.equal(changeDnaQuery(query, { facet: "US" }).contributorsOffset, 0);
  assert.equal(changeDnaQuery(query, { contributorsOffset: 80 }).facet, "JP");
});

test("Film-filtered Diary remains a timeline even with view=dna", () => {
  assert.equal(diaryViewFromQuery("dna"), "dna");
  assert.equal(diaryViewFromQuery("dna", "film_example"), "timeline");
});

test("DNA uses its own endpoints and invalidates only its cache family", () => {
  const base = API.cinemaDna();
  const contributors = API.cinemaDnaContributors("person", "person_" + "a".repeat(32), "preference", 40);
  assert.equal(new URL(contributors, "https://local.test").searchParams.get("offset"), "40");
  for (const key of [base, contributors, API.cinemaDnaFacets("genre", "exposure")]) assert.equal(isDnaCacheKey(key, base), true);
  for (const key of [API.profileViewings(), `${base}-other`, null, [], 1]) assert.equal(isDnaCacheKey(key, base), false);
});
