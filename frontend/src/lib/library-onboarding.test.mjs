import assert from "node:assert/strict";
import test from "node:test";

import {
  FIRST_RUN_INTRO_SESSION_KEY,
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
