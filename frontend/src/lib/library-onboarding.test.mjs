import assert from "node:assert/strict";
import test from "node:test";

import {
  FIRST_RUN_INTRO_SESSION_KEY,
  saveDirectoryAndScan,
  getWorkflowScanState,
  getFirstScanState,
  getLibraryEmptyState,
  isMediaDirectoryReady,
  shouldPlayFirstRunIntro,
} from "./library-onboarding.ts";

test("plays the first-run intro only once per motion-enabled session", () => {
  assert.equal(FIRST_RUN_INTRO_SESSION_KEY, "5x49:first-run-intro-seen:v1");
  assert.equal(shouldPlayFirstRunIntro({ hasPlayed: false, reducedMotion: false }), true);
  assert.equal(shouldPlayFirstRunIntro({ hasPlayed: true, reducedMotion: false }), false);
  assert.equal(shouldPlayFirstRunIntro({ hasPlayed: false, reducedMotion: true }), false);
});

test("shows onboarding only when the complete Library is empty", () => {
  assert.equal(getLibraryEmptyState(0, 0), "onboarding");
  assert.equal(getLibraryEmptyState(3, 0), "filtered-empty");
  assert.equal(getLibraryEmptyState(3, 2), "content");
});

test("enables scanning only for an existing readable media directory", () => {
  assert.equal(isMediaDirectoryReady(), false);
  assert.equal(isMediaDirectoryReady({ media_dir: "/media", exists: false, readable: false }), false);
  assert.equal(isMediaDirectoryReady({ media_dir: "/media", exists: true, readable: false }), false);
  assert.equal(isMediaDirectoryReady({ media_dir: "/media", exists: true, readable: true }), true);
});

test("derives queued, running, success, empty, and failed first-scan states", () => {
  const base = {
    requested: true,
    queueing: false,
    baselineFinishedAt: "before",
  };

  assert.equal(getFirstScanState({ ...base, lastFinishedAt: "before" }), "queued");
  assert.equal(getFirstScanState({ ...base, syncState: "running" }), "running");
  assert.equal(getFirstScanState({ ...base, lastFinishedAt: "after", scanned: 1 }), "success");
  assert.equal(getFirstScanState({ ...base, lastFinishedAt: "after", scanned: 0 }), "empty");
  assert.equal(
    getFirstScanState({ ...base, syncState: "error", lastFinishedAt: "after", lastError: "failed" }),
    "error",
  );
});


test("waits for directory validation then scans the returned path, not stale settings", async () => {
  let resolveSave;
  const calls = [];
  const pending = saveDirectoryAndScan(" /new/path ", (path) => {
    calls.push(["save", path]);
    return new Promise((resolve) => { resolveSave = resolve; });
  }, async (path) => { calls.push(["scan", path]); return { workflow_id: "new-scan" }; });
  assert.deepEqual(calls, [["save", "/new/path"]]);
  resolveSave({ media_dir: "/validated/path", exists: true, readable: true });
  assert.deepEqual(await pending, { workflow_id: "new-scan" });
  assert.deepEqual(calls[1], ["scan", "/validated/path"]);
});

test("a failed directory save never queues a scan", async () => {
  let scans = 0;
  await assert.rejects(saveDirectoryAndScan("/missing", async () => { throw new Error("missing"); }, async () => { scans++; }), /missing/);
  await assert.rejects(saveDirectoryAndScan("/unreadable", async () => ({ media_dir: "/unreadable", exists: true, readable: false }), async () => { scans++; }), /not readable/);
  assert.equal(scans, 0);
});

test("restored scan IDs follow their own terminal and cancellation states", () => {
  assert.equal(getWorkflowScanState(undefined, false, true), "queued");
  assert.equal(getWorkflowScanState({ status: "running", cancel_requested: true }, false, true), "cancelling");
  assert.equal(getWorkflowScanState({ status: "cancelled", cancel_requested: true }, false, true), "cancelled");
  assert.equal(getWorkflowScanState({ status: "failed" }, false, true), "error");
  assert.equal(getWorkflowScanState({ status: "succeeded" }, false, true), "success");
  assert.equal(getWorkflowScanState({ status: "succeeded", progress: { counts: { scanned: 0 } } }, false, true), "empty");
});
