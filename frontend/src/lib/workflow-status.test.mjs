import assert from "node:assert/strict";
import test from "node:test";
import { retainRecentWorkflows } from "./workflow-status.ts";

test("old active tasks survive an influx of recent completed tasks", () => {
  const tasks = Array.from({ length: 12 }, (_, index) => ({ id: `${index}`, status: index < 2 ? ["queued", "running"][index] : "succeeded", created_at: new Date(2026, 1, index + 1).toISOString() }));
  const visible = retainRecentWorkflows(tasks);
  assert.equal(visible.length, 10);
  assert.ok(visible.some((task) => task.id === "0"));
  assert.ok(visible.some((task) => task.id === "1"));
  assert.ok(!visible.some((task) => task.id === "2"));
  assert.equal(tasks[0].id, "0");
});
