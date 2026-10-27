import assert from "node:assert/strict";
import test from "node:test";
import { emptySearchPlan, formatSearchRange, isSearchPlan, parsePeopleIds, removePersonSelection, removeSearchCondition } from "./search-plan.ts";
import { discoveryHref, parseDiscoveryPlan, resolutionHref } from "./discovery-search.ts";

const id = value => `person_${value.repeat(32)}`;
test("locally bound film IDs preserve old v2 URLs and removable inclusion/exclusion chips", () => {
  const first = `film_${"a".repeat(32)}`, second = `film_${"b".repeat(32)}`;
  assert.equal(isSearchPlan(emptySearchPlan), true);
  const plan = {...emptySearchPlan, film_ids:[first], exclude_film_ids:[second], year_min:1990};
  assert.equal(isSearchPlan(plan), true);
  const url = new URL(resolutionHref("Silver Road, after 1989, not the original film", {plan,source:"local"}), "https://local.test");
  assert.deepEqual(parseDiscoveryPlan(url.searchParams.get("p")), plan);
  assert.deepEqual(removeSearchCondition(plan,"film_ids",0).film_ids, []);
  assert.deepEqual(removeSearchCondition(plan,"exclude_film_ids",0).exclude_film_ids, []);
  assert.equal(removeSearchCondition(plan,"exclude_film_ids",0).year_min, 1990);
  for (const value of [null, [first, first], [id("a")], ["https://outside.test"], Array(9).fill(first)]) {
    assert.equal(isSearchPlan({...emptySearchPlan,film_ids:value}), false);
    assert.equal(isSearchPlan({...emptySearchPlan,exclude_film_ids:value}), false);
  }
});
test("range labels preserve exclusive and inclusive bounds", () => {
  assert.equal(formatSearchRange({min:60,max:90,min_exclusive:true,max_exclusive:true}),"> 60 · < 90");
  assert.equal(formatSearchRange({min:60,max:90,max_exclusive:true}),"≥ 60 · < 90");
  assert.equal(formatSearchRange({min:1990,max:1999}),"1990–1999");
  assert.equal(formatSearchRange({max:90,max_exclusive:true}),"< 90");
});
test("v2 plans and identity selections round-trip without model re-interpretation", () => {
  const plan = { ...emptySearchPlan, countries: ["JP", "FR"], exclude_genres: ["Horror"],
    people: [{ name: "是枝裕和", role: "director", exclude: false }, { name: "Shared Person", role: "actor", exclude: false }],
    year_min: 1990, year_max: 2000, duration_max: 90, duration_max_exclusive: true, view: "unwatched" };
  assert.equal(isSearchPlan(plan), true);
  const url = new URL(resolutionHref("原始找片需求", { plan, person_id: null, people_ids: {0:id("a"),1:id("b")}, source:"local" }), "https://local.test");
  assert.deepEqual(parseDiscoveryPlan(url.searchParams.get("p")), plan);
  assert.deepEqual(parsePeopleIds(url.searchParams.get("people_ids")), {0:id("a"),1:id("b")});
  assert.equal(url.searchParams.get("q"), "原始找片需求");
  assert.equal(url.searchParams.has("results"), false);
});
test("removing a person preserves the identity of the remaining clauses", () => {
  assert.deepEqual(removePersonSelection({0:id("a"),1:id("b"),2:id("c")},1), {0:id("a"),1:id("c")});
  const plan = { ...emptySearchPlan, people: [{name:"A",role:"actor",exclude:false},{name:"B",role:"director",exclude:true}] };
  assert.deepEqual(removeSearchCondition(plan,"people",0).people, [plan.people[1]]);
  assert.equal(plan.people.length,2);
});
test("removing an alternative or range never broadens other conditions", () => {
  const plan = { ...emptySearchPlan, countries:["JP","FR"], duration_min:60, duration_min_exclusive:true, year_min:1990 };
  assert.deepEqual(removeSearchCondition(plan,"countries",0).countries,["FR"]);
  const next = removeSearchCondition(plan,"duration");
  assert.equal(next.duration_min,null); assert.equal(next.duration_min_exclusive,false);
  assert.equal(next.year_min,1990); assert.deepEqual(next.countries,["JP","FR"]);
  const url = new URL(discoveryHref("request",{plan:next,edited:true,offset:40}),"https://local.test");
  assert.equal(url.searchParams.get("edited"),"1"); assert.equal(url.searchParams.get("offset"),"40");
});
test("restoration rejects invalid v2 shapes, types, ranges and unbounded clauses", () => {
  for(const value of [{...emptySearchPlan,sql:"SELECT"},{...emptySearchPlan,version:"future"},
    {...emptySearchPlan,year_min:true},{...emptySearchPlan,year_min:2000,year_max:1990},
    {...emptySearchPlan,duration_min_exclusive:true},{...emptySearchPlan,duration_min:90,duration_max:90,duration_max_exclusive:true},
    {...emptySearchPlan,countries:["JP","JP"]},{...emptySearchPlan,genres:Array(11).fill("Drama")},
    {...emptySearchPlan,people:[{name:"A",role:"producer",exclude:false}]},
    {...emptySearchPlan,people:[{name:"A",role:"actor",exclude:false,sql:"x"}]}]){
    assert.equal(isSearchPlan(value),false); assert.equal(parseDiscoveryPlan(JSON.stringify(value)),null);
  }
});
test("identity selections accept only bounded internal Person IDs", () => {
  assert.deepEqual(parsePeopleIds(undefined),{});
  for(const value of [null,[],{8:id("a")},{0:"https://outside.test"},{0:id("a"),sql:id("b")},"bad json"])
    assert.equal(parsePeopleIds(JSON.stringify(value)),null);
});


test("language conditions round-trip and remove independently from other hard filters", () => {
  const plan = {...emptySearchPlan, year_min:2000, languages:[
    {kind:"original",code:"en",exclude:false}, {kind:"spoken",code:"ja",exclude:true}]};
  const url = new URL(discoveryHref("original English, not in Japanese", {plan,edited:true}),"https://local.test");
  assert.deepEqual(parseDiscoveryPlan(url.searchParams.get("p")),plan);
  const next=removeSearchCondition(plan,"languages",0);
  assert.deepEqual(next.languages,[plan.languages[1]]);
  assert.equal(next.year_min,2000);
  assert.equal(plan.languages.length,2);
});
test("language URL input rejects malformed, contradictory and unbounded conditions", () => {
  for(const languages of [null, [{kind:"country",code:"en",exclude:false}],
    [{kind:"spoken",code:"English",exclude:false}], [{kind:"spoken",code:"zz",exclude:false}],
    [{kind:"spoken",code:"en",exclude:"false"}], [{kind:"spoken",code:"en",exclude:false,sql:"x"}],
    [{kind:"spoken",code:"en",exclude:false},{kind:"spoken",code:"en",exclude:false}],
    [{kind:"spoken",code:"en",exclude:false},{kind:"spoken",code:"en",exclude:true}],
    Array(9).fill({kind:"spoken",code:"en",exclude:false})]){
    assert.equal(isSearchPlan({...emptySearchPlan,languages}),false);
  }
});
