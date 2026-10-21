import assert from "node:assert/strict";
import test from "node:test";
import { discoveryHref, discoveryFailure, discoveryReason, normalizeDiscoverySearch, parseDiscoveryPlan, resolutionHref } from "./discovery-search.ts";

const plan = { genre:null,person:"Shared Person",person_role:"director",country:"JP",decade:1990,view:"unwatched",sort:"year",direction:"desc" };
test("unified search preserves raw input, corrected conditions and independent page in a local URL", () => {
  const q = "未看日本电影 & Shared Person";
  const href = discoveryHref(q, {plan,personId:`person_${"a".repeat(32)}`,source:"ai",edited:true,offset:40});
  const url = new URL(href,"https://local.test");
  assert.equal(url.pathname,"/explore/search"); assert.equal(url.searchParams.get("q"),q);
  assert.deepEqual(parseDiscoveryPlan(url.searchParams.get("p")),plan);
  assert.equal(url.searchParams.get("edited"),"1"); assert.equal(url.searchParams.get("offset"),"40");
  assert.equal(discoveryHref("  "),"/explore");
  assert.equal(normalizeDiscoverySearch([" q ","ignore"]),"q");
  assert.equal(normalizeDiscoverySearch("x".repeat(601)).length,600);
});
test("unresolved and error URLs retain input but never serialize arbitrary response data", () => {
  const result={...discoveryFailure("ask_timeout"),question:"provider text",results:{secret:true}};
  const url=new URL(resolutionHref("request",result),"https://local.test");
  assert.equal(url.searchParams.get("q"),"request"); assert.equal(url.searchParams.get("reason"),"ask_timeout");
  assert.equal(url.searchParams.has("p"),false); assert.equal(url.href.includes("provider"),false);
  assert.equal(discoveryReason("private provider body"),"unavailable");
});
test("restored plans reject extra fields, invalid dimensions and malformed types", () => {
  assert.deepEqual(parseDiscoveryPlan(JSON.stringify(plan)),plan);
  for(const value of [null,[],{}, {...plan,sql:"bad"},{...plan,decade:true},{...plan,person:null},
    {...plan,country:["JP"]},{...plan,view:"relaxed"},{...plan,direction:"other"},{...plan,decade:1995}])
    assert.equal(parseDiscoveryPlan(JSON.stringify(value)),null);
  assert.equal(parseDiscoveryPlan("bad json"),null);
  assert.equal(parseDiscoveryPlan("x".repeat(2001)),null);
});
