import assert from "node:assert/strict";
import test from "node:test";

import {
  groupViewingEntries,
  todayLocalDate,
  viewingDateMode,
  watchedActionFor,
} from "./viewing-diary.ts";

const entry = (id, watchedAt, precision) => ({
  viewing: {
    id,
    film_id: `film_${"a".repeat(32)}`,
    watched_at: watchedAt,
    watched_at_precision: precision,
    source: "diary",
    editable: true,
    created_at: "2026-08-31T00:00:00Z",
    updated_at: "2026-08-31T00:00:00Z",
  },
  film: { id: `film_${"a".repeat(32)}`, title: "Film", year: 2026, in_library: true },
  profile_state: { watched: true, manual_watched: false, favorite: false },
});

test("groups exact and timestamp Viewings by month, year precision separately, and unknown last", () => {
  const groups = groupViewingEntries([
    entry("one", "2026-08-31", "date"),
    entry("two", "2026-08-15T20:00:00+08:00", "timestamp"),
    entry("three", "2025", "year"),
    entry("four", null, "unknown"),
  ]);
  assert.deepEqual(groups.map((group) => [group.key, group.entries.length]), [
    ["month:2026-08", 2],
    ["year:2025", 1],
    ["unknown", 1],
  ]);
});

test("derived watched action never creates a manual Viewing over a Diary-only state", () => {
  assert.equal(watchedActionFor({ watched: false, manual_watched: false }), "mark_watched");
  assert.equal(watchedActionFor({ watched: true, manual_watched: true }), "mark_unwatched");
  assert.equal(watchedActionFor({ watched: true, manual_watched: false }), "open_diary");
});

test("editor mode and local date defaults are deterministic", () => {
  assert.equal(viewingDateMode(entry("one", "2026", "year").viewing), "year");
  assert.equal(viewingDateMode(entry("one", null, "unknown").viewing), "unknown");
  assert.equal(viewingDateMode(entry("one", "2026-08-31T20:00:00Z", "timestamp").viewing), "date");
  assert.equal(todayLocalDate(new Date(2026, 7, 31, 23, 59)), "2026-08-31");
});
