import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { discoveryHref, discoveryFailure, discoveryKeywords, discoveryReason, discoveryRequestId, hasPrivateDiscoveryInput, normalizeDiscoverySearch, parseDiscoveryPlan, parseSemanticSnapshot, resolutionHref } from "./discovery-search.ts";
import { emptySearchPlan } from "./search-plan.ts";

const plan = { genre:null,person:"Shared Person",person_role:"director",country:"JP",decade:1990,view:"unwatched",sort:"year",direction:"desc" };
test("HTTP-safe cancellation capabilities use secure entropy without randomUUID", t => {
  const crypto = globalThis.crypto;
  t.mock.getter(globalThis, "crypto", () => ({ getRandomValues: crypto.getRandomValues.bind(crypto) }));
  const ids = new Set(Array.from({ length: 100 }, () => discoveryRequestId()));
  assert.equal(ids.size, 100);
  for (const id of ids) assert.match(id, /^rq_[0-9a-f]{32}$/);
});
test("missing or failing crypto leaves the optional cancellation capability absent", t => {
  t.mock.getter(globalThis, "crypto", () => undefined);
  assert.equal(discoveryRequestId(), null);
  t.mock.restoreAll();
  t.mock.getter(globalThis, "crypto", () => ({ getRandomValues() { throw Error("Unavailable"); } }));
  assert.equal(discoveryRequestId(), null);
});
test("content removal keeps its original question and proof through further local edits", () => {
  const token = `ds_${"a".repeat(32)}`, raw = "Japanese films about a family reunion";
  const url = new URL(discoveryHref(raw, {plan:emptySearchPlan,edited:true,semanticSnapshot:token,semanticRemoved:true}), "http://local.test");
  assert.equal(url.searchParams.get("q"), raw);
  assert.equal(url.searchParams.get("semantic_snapshot"), token);
  assert.equal(url.searchParams.get("semantic_removed"), "1");
  assert.equal(url.searchParams.get("edited"), "1");
  assert.equal(new URL(discoveryHref(raw, {plan,semanticRemoved:true}), "http://local.test").searchParams.has("semantic_removed"), false);
});
test("unsupported content exclusions and identity ambiguities retain specific bilingual reasons", () => {
  for (const locale of ["en", "zh"]) {
    const copy = JSON.parse(readFileSync(new URL(`../../messages/${locale}.json`, import.meta.url), "utf8"));
    for (const reason of ["unsupported_content_negation", "unknown_film", "ambiguous_film", "ambiguous_reference", "search_rerank_uncalibrated"]) {
      assert.equal(discoveryReason(reason), reason);
      assert.equal(typeof copy.Discovery.reasons[reason], "string");
      assert.notEqual(copy.Discovery.reasons[reason], copy.Discovery.reasons.unavailable);
    }
  }
});
test("keyword normalization is response data while the URL retains the original exact request", () => {
  const raw = "Please find the film Silver Road.";
  const url = new URL(resolutionHref(raw, {status:"keyword",keyword_query:"Silver Road",source:"local"}), "https://local.test");
  assert.equal(url.searchParams.get("q"), raw);
  assert.equal(url.searchParams.has("keyword_query"), false);
});
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
    "Movies/private.mkv","Movies\\private.mkv","Movies/subdir/private.mkv",
    "Movies/字幕.srt","Movies/poster.jpg","路径：Movies/片单.nfo",
    "Movies/private.MKV","\u0060Movies/private.mkv\u0060","notes/.env",
    "Movies/private film.mkv","Movies\\private film.mkv","'My Movies/private film.mkv'",
    "'Movies/My Private Film.mkv'",'"Movies/My Private Film.mkv"',
    "Movies/O'Brien's Private Film.mkv","Movies/私人的电影.mkv",
    "\u0060/private.mkv\u0060","\u0060~/Movies/private.mkv\u0060","\u0060./Movies/private.mkv\u0060",
    "'/private.mkv'","(~/Movies/private.mkv)","路径：./私密/片单.txt","my api_key=private","use sk-abcdefgh12345678",
    "Ｃ：＼Movies＼private.mkv","～／Movies／private.mkv"])
    assert.equal(hasPrivateDiscoveryInput("Japanese films featuring "+path),true,path);
  for(const title of ["Face/Off","V/H/S","9/11","Fate/stay night","D: The Movie","The Secret Life of Walter Mitty","In the Mood for Love","日与夜","1/2","provider/model-2.5"]){
    assert.equal(hasPrivateDiscoveryInput(title),false,title);
    assert.equal(hasPrivateDiscoveryInput("find "+title),false,title);
    for(const quote of ["'",'"',"\u0060"])
      assert.equal(hasPrivateDiscoveryInput(quote+title+quote),false,title);
  }
});
test("repeated and mixed path separators stay private with spaces and quote boundaries", () => {
  for(const separator of ["//","///","\\".repeat(2),"\\".repeat(3),"/\\","\\/","//\\//","\\//\\\\"])
    for(const [folder,filename] of [["Movies","My Private Film.mkv"],["My Movies","私人字幕.srt"]])
      for(const quote of ["","'",'"',"\u0060"]){
        const path=quote+folder+separator+filename+quote;
        assert.equal(hasPrivateDiscoveryInput("Japanese films featuring "+path),true,path);
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

test("semantic snapshots restore with complete hard filters and no provider payload in the URL", () => {
  const snapshot=`ds_${"a".repeat(32)}`;
  const q="films about a family reunion";
  const result={plan:{...emptySearchPlan,countries:["JP"]},snapshot,source:"ai",edited:true,
    people_ids:{},semantic:{text:"a family reunion",evaluation_only:true,order:"year"},
    results:{privateData:"never in URL"},usage:{key:"never in URL"}};
  const url=new URL(resolutionHref(q,result),"https://local.test");
  assert.equal(url.searchParams.get("q"),q);
  assert.equal(parseSemanticSnapshot(url.searchParams.get("semantic_snapshot")),snapshot);
  assert.equal(url.searchParams.get("order"),"year");
  assert.equal(url.searchParams.get("edited"),"1");
  assert.deepEqual(parseDiscoveryPlan(url.searchParams.get("p")),result.plan);
  assert.equal(url.href.includes("never"),false);
  for(const invalid of ["ds_short","//outside.test",`ds_${"a".repeat(33)}`,"ds_"+"z".repeat(32)])
    assert.equal(parseSemanticSnapshot(invalid),null);
  assert.equal(discoveryReason("search_snapshot_expired"),"search_snapshot_expired");
});
