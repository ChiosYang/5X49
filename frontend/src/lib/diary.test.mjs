import assert from "node:assert/strict";
import test from "node:test";

import {
  createViewingDateDraft,
  diaryEditorFilmId,
  diaryViewFromQuery,
  groupViewingEntries,
  todayLocalDate,
  viewingDateDraftDirty,
  viewingDateDraftValid,
  viewingDraftWatchedAt,
  viewingDateMode,
  watchedActionFor,
} from "./diary.ts";

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

test("Diary query mode defaults safely and Film filters always show the full timeline", () => {
  assert.equal(diaryViewFromQuery(null), "timeline");
  assert.equal(diaryViewFromQuery("timeline"), "timeline");
  assert.equal(diaryViewFromQuery("recent"), "recent");
  assert.equal(diaryViewFromQuery("invalid"), "timeline");
  assert.equal(diaryViewFromQuery("recent", `film_${"a".repeat(32)}`), "timeline");
});

test("Diary editor targets the selected Viewing before the page Film filter", () => {
  const pageFilmId = `film_${"a".repeat(32)}`;
  const selectedFilmId = `film_${"b".repeat(32)}`;

  assert.equal(diaryEditorFilmId(undefined, { film_id: selectedFilmId }), selectedFilmId);
  assert.equal(diaryEditorFilmId(pageFilmId, { film_id: selectedFilmId }), selectedFilmId);
  assert.equal(diaryEditorFilmId(pageFilmId, null), pageFilmId);
  assert.equal(diaryEditorFilmId(undefined, null), undefined);
});

test("editor mode and local date defaults are deterministic", () => {
  assert.equal(viewingDateMode(entry("one", "2026", "year").viewing), "year");
  assert.equal(viewingDateMode(entry("one", null, "unknown").viewing), "unknown");
  assert.equal(viewingDateMode(entry("one", "2026-08-31T20:00:00Z", "timestamp").viewing), "date");
  assert.equal(todayLocalDate(new Date(2026, 7, 31, 23, 59)), "2026-08-31");
});

test("Viewing date drafts normalize payloads and validate supported precision", () => {
  const now = new Date(2026, 7, 31, 23, 59);
  const draft = createViewingDateDraft(null, now);

  assert.deepEqual(draft, { mode: "date", dateValue: "2026-08-31", yearValue: "2026" });
  assert.equal(viewingDraftWatchedAt(draft), "2026-08-31");
  assert.equal(viewingDraftWatchedAt({ ...draft, mode: "year", yearValue: "2025" }), "2025");
  assert.equal(viewingDraftWatchedAt({ ...draft, mode: "unknown" }), null);
  assert.equal(viewingDateDraftValid({ ...draft, mode: "year", yearValue: "2027" }, now), false);
  assert.equal(viewingDateDraftValid({ ...draft, mode: "year", yearValue: "2026" }, now), true);
});

test("Viewing date drafts detect meaningful changes without rewriting timestamps", () => {
  const viewing = entry("one", "2026-08-31T20:00:00Z", "timestamp").viewing;
  const draft = createViewingDateDraft(viewing, new Date(2026, 7, 31));

  assert.equal(viewingDateDraftDirty(draft, viewing), false);
  assert.equal(viewingDateDraftDirty({ ...draft, dateValue: "2026-08-30" }, viewing), true);
  assert.equal(viewingDateDraftDirty({ ...draft, mode: "unknown" }, viewing), true);
  assert.equal(viewingDateDraftDirty(draft, null), true);
});
