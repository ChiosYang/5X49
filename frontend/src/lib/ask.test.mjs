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
