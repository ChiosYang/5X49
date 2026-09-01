import assert from "node:assert/strict";
import test from "node:test";

import {
  buildLibraryCareState,
  buildLibraryHref,
  normalizeLibraryView,
} from "./library-care.ts";

const film = (status = "matched") => ({
  primary_item: { metadata: { scrape_status: status } },
});
const candidate = (stable) => ({ stable });

test("normalizes shareable Library care views", () => {
  assert.equal(normalizeLibraryView(), "all");
  assert.equal(normalizeLibraryView("metadata"), "metadata");
  assert.equal(normalizeLibraryView("inbox"), "inbox");
  assert.equal(normalizeLibraryView("offline"), "offline");
  assert.equal(normalizeLibraryView("unknown"), "all");
});

test("care links preserve poster sorting and filtering state", () => {
  const state = {
    view: "all",
    sort: "added",
    direction: "desc",
    filter: "favorite",
  };
  assert.equal(
    buildLibraryHref(state, "metadata"),
    "/library?view=metadata&sort=added&dir=desc&filter=favorite",
  );
  assert.equal(
    buildLibraryHref({ ...state, view: "metadata" }, "all"),
    "/library?sort=added&dir=desc&filter=favorite",
  );
});

test("a healthy Library does not render maintenance chrome", () => {
  const state = buildLibraryCareState({
    films: [film()],
    organizationCandidates: [],
    missingItems: [],
    activeView: "all",
  });
  assert.deepEqual(state.visibleViews, []);
  assert.equal(state.recommendedView, null);
  assert.equal(state.showStatus, false);
});

test("prioritizes metadata, actionable inbox, then offline records", () => {
  const all = buildLibraryCareState({
    films: [film("needs_review")],
    organizationCandidates: [candidate(true), candidate(false)],
    missingItems: [{ library_item_id: "missing" }],
    activeView: "all",
  });
  assert.equal(all.recommendedView, "metadata");
  assert.equal(all.totalActionable, 3);
  assert.deepEqual(all.visibleViews, ["all", "metadata", "inbox", "offline"]);

  const inbox = buildLibraryCareState({
    films: [],
    organizationCandidates: [candidate(true)],
    missingItems: [{ library_item_id: "missing" }],
    activeView: "all",
  });
  assert.equal(inbox.recommendedView, "inbox");
});

test("waiting files are visible but are not actionable", () => {
  const state = buildLibraryCareState({
    films: [],
    organizationCandidates: [candidate(false), candidate(false)],
    missingItems: [],
    activeView: "all",
  });
  assert.equal(state.actionableInbox, 0);
  assert.equal(state.waitingInbox, 2);
  assert.equal(state.totalActionable, 0);
  assert.equal(state.recommendedView, null);
  assert.deepEqual(state.visibleViews, ["all", "inbox"]);
  assert.equal(state.showStatus, true);
});
test("keeps an emptied active queue visible and isolates auxiliary failures", () => {
  const state = buildLibraryCareState({
    films: [],
    organizationCandidates: [],
    missingItems: [],
    activeView: "offline",
    organizationUnavailable: true,
  });
  assert.deepEqual(state.visibleViews, ["all", "offline"]);
  assert.equal(state.partialUnavailable, true);
  assert.equal(state.showStatus, true);
});
