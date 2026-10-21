import assert from "node:assert/strict";
import test from "node:test";
import { discoveryHref, discoveryFailure, discoveryKeywords, discoveryReason, hasPrivateDiscoveryInput, normalizeDiscoverySearch, parseDiscoveryPlan, resolutionHref } from "./discovery-search.ts";

const plan = { genre:null,person:"Shared Person",person_role:"director",country:"JP",decade:1990,view:"unwatched",sort:"year",direction:"desc" };
test("only explicit leading search commands change the lookup term, preserving title words", () => {
  for(const [raw,term] of [["find Alpha","Alpha"],["Please find The Alpha","The Alpha"],["找Alpha","Alpha"],
    ["请帮我找一下是枝裕和","是枝裕和"],["The Alpha","The Alpha"],["In the Mood for Love","In the Mood for Love"],
    ["Finding Nemo","Finding Nemo"],["A place to find Alpha","A place to find Alpha"]])
    assert.equal(discoveryKeywords(raw),term);
});
test("private path roots are blocked without rejecting ordinary slash-containing titles", () => {
  for(const path of ["C:\\Movies\\private","\\\\server\\Movies\\private.mkv","file:///private.mkv",
    "/mnt/private/films","/private.mkv","~/Movies/private.mkv","~user/Movies/private.mkv",
    "./Movies/private.mkv","../Movies/private.mkv","../../private.mkv",
    ".\\Movies\\private.mkv","..\\Movies\\private.mkv","\\private.mkv",
    "'/private.mkv'","(~/Movies/private.mkv)","路径：./私密/片单.txt","my api_key=private","use sk-abcdefgh12345678"])
    assert.equal(hasPrivateDiscoveryInput("Japanese films featuring "+path),true,path);
  for(const title of ["Face/Off","V/H/S","9/11","Fate/stay night","D: The Movie","The Secret Life of Walter Mitty","In the Mood for Love","日与夜","1/2"]){
    assert.equal(hasPrivateDiscoveryInput(title),false,title);
    assert.equal(hasPrivateDiscoveryInput("find "+title),false,title);
  }
});
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
