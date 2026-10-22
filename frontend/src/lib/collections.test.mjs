import assert from "node:assert/strict";
import test from "node:test";
import { catalogHref, collectionCategory, collectionHref, discoverySearchHref, hasLegacyExploreQuery, validCollection } from "./collections.ts";
import { exploreHref, parseExploreQuery } from "./explore.ts";

test("Collection identity is a stable validated path independent of viewing and sorting", () => {
  assert.equal(collectionHref({kind:"country",key:"JP"}), "/explore/collections/country/JP");
  assert.equal(validCollection("director", `person_${"a".repeat(32)}`), true);
  for (const [kind,key] of [["series","unknown"],["country","Japan"],["decade","1991"],["person","../film"]]) assert.equal(validCollection(kind,key), false);
  assert.equal(exploreHref(parseExploreQuery({view:"unwatched",sort:"year",offset:"40"}), "/explore/collections/country/JP"), "/explore/collections/country/JP?view=unwatched&sort=year&offset=40");
});

test("Retired manual query markers are recognized for redirects while catalog pagination stays on Explore", () => {
  for (const params of [{person:"person_bad"},{country:"JP"},{genre:[]},{view:"all"},{sort:"title"}]) assert.equal(hasLegacyExploreQuery(params), true);
  assert.equal(hasLegacyExploreQuery({}), false);
  assert.equal(hasLegacyExploreQuery({q:"Nolan"}), false);
  assert.equal(hasLegacyExploreQuery({category:"country",offset:"24"}), false);
});

test("Directory categories and independent discovery pagination round-trip without query editing", () => {
  assert.equal(collectionCategory(["country","director"]), "country");
  assert.equal(collectionCategory("unknown"), "all");
  assert.equal(catalogHref(), "/explore");
  assert.equal(catalogHref("director",24), "/explore?category=director&offset=24");
  const url = new URL(discoverySearchHref("A & 日本",2,12,24), "http://local");
  assert.equal(url.searchParams.get("q"), "A & 日本");
  assert.equal(url.searchParams.get("page"), "2");
  assert.equal(url.searchParams.get("people_offset"), "12");
  assert.equal(url.searchParams.get("collection_offset"), "24");
});
