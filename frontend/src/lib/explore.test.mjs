import assert from "node:assert/strict";
import test from "node:test";

import {
  buildExploreContextSearchParams,
  buildExploreSearchParams,
  clearExploreFilters,
  exploreNavigation,
  formatExploreFacetLabel,
  graphNodeHref,
  initialExploreLens,
  parseExploreQuery,
  withExploreFacet,
} from "./explore.ts";

const genre = `con_${"a".repeat(32)}`;
const person = `person_${"b".repeat(32)}`;

test("Explore query parsing rejects malformed values and serializes in stable order", () => {
  const query = parseExploreQuery({
    person,
    genre: [genre, `concept_${"a".repeat(32)}`, "bad", genre],
    country: ["JP", "Japan"],
    decade: ["1990", "1995"],
    view: "unwatched",
    sort: "year",
    offset: "40",
  });
  assert.deepEqual(query.genre, [genre]);
  assert.deepEqual(query.country, ["JP"]);
  assert.deepEqual(query.decade, ["1990"]);
  assert.equal(
    buildExploreSearchParams(query).toString(),
    `genre=${genre}&person=${person}&country=JP&decade=1990&view=unwatched&sort=year&offset=40`,
  );
  assert.equal(
    buildExploreContextSearchParams(query).toString(),
    `genre=${genre}&person=${person}&country=JP&decade=1990&view=unwatched&limit=6`,
  );
});

test("Explore facet changes reset pagination and clear only factual constraints", () => {
  const query = parseExploreQuery({ genre, view: "watched", offset: "40" });
  assert.deepEqual(withExploreFacet(query, "person", person).person, [person]);
  assert.equal(withExploreFacet(query, "person", person).offset, 0);
  assert.equal(clearExploreFilters(query).view, "watched");
  assert.deepEqual(clearExploreFilters(query).genre, []);
  assert.equal(initialExploreLens(query), "genre");
  assert.equal(exploreNavigation(query, "filter").scroll, false);
  assert.equal(exploreNavigation(query, "filter").focusResults, false);
  assert.equal(exploreNavigation(query, "page").focusResults, true);
});

test("Graph links route owned Films, people and Genres without exposing other Concepts", () => {
  const film = `film_${"c".repeat(32)}`;
  assert.equal(graphNodeHref({ id: film, entity_type: "film", in_library: true }, "film_" + "d".repeat(32)), `/library/${film}`);
  assert.equal(graphNodeHref({ id: person, entity_type: "person", in_library: false }, film), `/explore?person=${person}`);
  assert.equal(graphNodeHref({ id: genre, entity_type: "concept", concept_kind: "genre", in_library: false }, film), `/explore?genre=${genre}`);
  assert.equal(graphNodeHref({ id: genre, entity_type: "concept", concept_kind: "theme", in_library: false }, film), null);
});

test("Explore localizes country and decade labels without changing stable keys", () => {
  assert.equal(formatExploreFacetLabel("decade", "1990", "1990s", "zh"), "1990年代");
  assert.equal(formatExploreFacetLabel("decade", "1990", "1990s", "en"), "1990s");
  assert.equal(
    formatExploreFacetLabel("country", "JP", "JP", "zh"),
    new Intl.DisplayNames(["zh"], { type: "region" }).of("JP"),
  );
});

test("Explore country labels keep the server and hydration render deterministic", () => {
  const OriginalDisplayNames = Intl.DisplayNames;
  try {
    Intl.DisplayNames = class {
      of() { return "Hong Kong SAR China"; }
    };
    const server = formatExploreFacetLabel("country", "HK", "HK", "en", false);

    Intl.DisplayNames = class {
      of() { return "Hong Kong"; }
    };
    const hydration = formatExploreFacetLabel("country", "HK", "HK", "en", false);

    assert.equal(server, "HK");
    assert.equal(hydration, server);
  } finally {
    Intl.DisplayNames = OriginalDisplayNames;
  }
});
