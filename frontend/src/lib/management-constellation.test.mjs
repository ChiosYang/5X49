import assert from "node:assert/strict";
import test from "node:test";

import { buildManagementConstellation } from "./management-constellation.ts";

const film = (id, title, scrapeStatus = "matched", scrapeError = null) => ({
  id,
  title,
  year: 2000,
  primary_item: {
    id: `lib_${id}`,
    metadata: { scrape_status: scrapeStatus, scrape_error: scrapeError },
  },
});

const base = (overrides = {}) => ({
  films: [],
  organizationCandidates: [],
  missingItems: [],
  workflows: [],
  tmdbConfigured: true,
  watcher: { state: "idle", running: true, configured: true },
  sync: { state: "idle" },
  metadata: { state: "idle" },
  scores: { state: "idle" },
  organizer: { state: "idle" },
  ...overrides,
});

test("system nodes have stable ids and positions when there are no exceptions", () => {
  const model = buildManagementConstellation(base());
  assert.deepEqual(
    model.nodes.map((node) => [node.id, node.x, node.y]),
    [
      ["library", 50, 52],
      ["watcher", 16, 24],
      ["sync", 20, 70],
      ["metadata", 50, 14],
      ["scores", 83, 25],
      ["organizer", 81, 70],
    ],
  );
  assert.equal(model.attentionCount, 0);
});

test("failed workflows outrank running and attention service states", () => {
  const model = buildManagementConstellation(base({
    films: [film("review", "Review", "needs_review")],
    metadata: { state: "running" },
    workflows: [{ type: "metadata.scrape_library", status: "failed" }],
  }));
  assert.equal(model.nodes.find((node) => node.id === "metadata").state, "failed");
  assert.equal(model.nodes.find((node) => node.id === "metadata-review").count, 1);
});

test("exception children are capped while complete queues remain available", () => {
  const films = Array.from({ length: 10 }, (_, index) => (
    film(`film-${index}`, `Film ${String(index).padStart(2, "0")}`, "needs_review")
  ));
  const desktop = buildManagementConstellation(base({ films, childLimit: 8 }));
  const mobile = buildManagementConstellation(base({ films, childLimit: 6 }));
  assert.equal(desktop.nodes.filter((node) => node.kind === "film").length, 8);
  assert.equal(mobile.nodes.filter((node) => node.kind === "film").length, 6);
  assert.equal(desktop.reviewFilms.length, 10);
});

test("action registry covers all commands and reports disabled reasons", () => {
  const model = buildManagementConstellation(base({ tmdbConfigured: false }));
  assert.deepEqual(
    model.actions.map((action) => action.id),
    [
      "scan",
      "scrape-metadata",
      "refresh-scores",
      "review-metadata",
      "organize-files",
      "cleanup-missing",
      "open-settings",
      "open-activity",
      "clear-data",
    ],
  );
  assert.equal(model.actions.find((action) => action.id === "scrape-metadata").disabledReason, "tmdb-unconfigured");
  assert.equal(model.actions.find((action) => action.id === "cleanup-missing").disabledReason, "empty");
  assert.equal(model.actions.find((action) => action.id === "review-metadata").destination, "/library?view=metadata");
  assert.equal(model.actions.find((action) => action.id === "organize-files").destination, "/library?view=inbox");
  assert.equal(model.actions.find((action) => action.id === "cleanup-missing").destination, "/library?view=offline");
  assert.equal(model.actions.find((action) => action.id === "clear-data").destination, "/settings?section=library#danger-zone");
  assert.equal(model.nodes.find((node) => node.id === "metadata").state, "unavailable");
});

test("partial query failure stays local and running workflows animate their service", () => {
  const model = buildManagementConstellation(base({
    libraryAvailable: false,
    workflows: [{ type: "external_scores.refresh_library", status: "running" }],
  }));
  assert.equal(model.nodes.find((node) => node.id === "library").state, "unavailable");
  assert.equal(model.nodes.find((node) => node.id === "scores").state, "running");
  assert.equal(model.nodes.find((node) => node.id === "sync").state, "idle");
});

test("organization priority is actionable, then stable time and title", () => {
  const candidate = (sourcePath, stable, mtime, title) => ({
    source_path: sourcePath,
    source_location: "root",
    filename: `${title}.mkv`,
    size: 1,
    mtime,
    stable,
    parsed_title: title,
    parsed_year: 2000,
    status: stable ? "needs_organize" : "waiting_for_stability",
  });
  const model = buildManagementConstellation(base({
    organizationCandidates: [
      candidate("waiting", false, 1, "A"),
      candidate("ready-new", true, 3, "B"),
      candidate("ready-old", true, 2, "C"),
    ],
  }));
  assert.deepEqual(
    model.organizationCandidates.map((item) => item.source_path),
    ["ready-old", "ready-new", "waiting"],
  );
});
