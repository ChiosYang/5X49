import assert from "node:assert/strict";
import test from "node:test";
import { askErrorCode, askQueryPayload, emptyAskPlan } from "./ask.ts";

test("local query requires a resolved plan and preserves every constraint and selected identity", () => {
  const plan = { ...emptyAskPlan, person: "Same Name", person_role: "director", country: "JP", decade: 1990, view: "unwatched" };
  const resolution = { status: "ready", plan, person_id: "person_selected" };
  assert.deepEqual(askQueryPayload(resolution, 20), { plan, person_id: "person_selected", confirmed: true, offset: 20 });
  for (const status of ["needs_clarification", "unsupported", "clarify"]) {
    assert.throws(() => askQueryPayload({ ...resolution, status }));
  }
  assert.throws(() => askQueryPayload({ status: "ready", plan: null }));
});

test("Ask failure codes never surface arbitrary provider text", () => {
  assert.equal(askErrorCode(502, { detail: { code: "secret provider body" } }), "unavailable");
  assert.equal(askErrorCode(504, { detail: { code: "ask_timeout" } }), "ask_timeout");
  assert.equal(askErrorCode(422, null), "invalid_request");
  assert.equal(askErrorCode(503, { detail: { code: "projection_unavailable" } }), "projection_unavailable");
});

test("session state retains only a validated confirmed structured query", async () => {
  const { parseAskSession } = await import("./ask.ts");
  const payload = { plan: { ...emptyAskPlan, person: "Same Name", question: "private input" }, person_id: `person_${"a".repeat(32)}`, confirmed: true, offset: 20, question: "private input", results: { items: [] } };
  const parsed = parseAskSession(JSON.stringify(payload));
  assert.equal(parsed.offset, 20);
  assert.equal(parsed.person_id, payload.person_id);
  assert.equal("question" in parsed, false);
  assert.equal("question" in parsed.plan, false);
  assert.equal("results" in parsed, false);
  for (const patch of [{ confirmed: false }, { offset: -1 }, { person_id: "invalid" }, { plan: { ...emptyAskPlan, view: "silently-relaxed" } }]) {
    assert.equal(parseAskSession(JSON.stringify({ ...payload, ...patch })), null);
  }
  assert.equal(parseAskSession("broken"), null);
});

test("explicit single-filter removal preserves every other condition and resets person role only with person", async () => {
  const { removeAskConstraint } = await import("./ask.ts");
  const plan = { ...emptyAskPlan, person: "Name", person_role: "director", country: "JP", decade: 1990, view: "unwatched" };
  assert.deepEqual(removeAskConstraint(plan, "country"), { ...plan, country: null });
  assert.deepEqual(removeAskConstraint(plan, "person"), { ...plan, person: null, person_role: "any" });
  assert.deepEqual(removeAskConstraint(plan, "view"), { ...plan, view: "all" });
  assert.equal(plan.country, "JP");
});

test("numeric range session validation and explicit relaxation preserve boundary semantics", async () => {
  const { validAskNumbers, askNumericConditions, removeAskConstraint, parseAskSession } = await import("./ask.ts");
  const plan = { ...emptyAskPlan, duration_min: 90, duration_max: 120, duration_max_inclusive: false, rating_min: 4 };
  assert.equal(validAskNumbers(plan), true);
  assert.deepEqual(askNumericConditions(plan), [{ field: "duration", value: 90, operator: "≥" }, { field: "duration", value: 120, operator: "<" }, { field: "rating", value: 4, operator: "≥" }]);
  assert.deepEqual(removeAskConstraint(plan, "duration"), { ...plan, duration_min: null, duration_max: null, duration_min_inclusive: true, duration_max_inclusive: true });
  for (const changes of [{ rating_min: 6 }, { rating_max: 3 }, { duration_min: 121 }, { duration_max: true }, { duration_min: 90.5 }, { duration_max: 90 }]) {
    assert.equal(validAskNumbers({ ...plan, ...changes }), false);
    assert.equal(parseAskSession(JSON.stringify({ plan: { ...plan, ...changes }, confirmed: true, person_id: null, offset: 0 })), null);
  }
});

test("cancelled and earlier responses cannot commit after a later request or unmount", async () => {
  const { createAskRequestGate } = await import("./ask.ts");
  const gate = createAskRequestGate();
  const earlier = gate.begin();
  const later = gate.begin();
  assert.equal(earlier.signal.aborted, true);
  assert.equal(gate.current(earlier.id), false);
  assert.equal(gate.current(later.id), true);
  gate.cancel();
  assert.equal(later.signal.aborted, true);
  assert.equal(gate.current(later.id), false);
});
