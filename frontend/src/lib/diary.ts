import type { FilmProfileState, ViewingTimelineEntry, ViewingView } from "@/types/movie";

export type WatchedAction = "mark_watched" | "mark_unwatched" | "open_diary";
export type DiaryView = "timeline" | "recent";
export type ViewingDateMode = "date" | "year" | "unknown";

export interface ViewingDateDraft {
  dateValue: string;
  mode: ViewingDateMode;
  yearValue: string;
}

export interface ViewingGroup {
  key: string;
  kind: "month" | "year" | "unknown";
  year?: string;
  month?: string;
  entries: ViewingTimelineEntry[];
}

export function watchedActionFor(state: Pick<FilmProfileState, "watched" | "manual_watched">): WatchedAction {
  if (!state.watched) return "mark_watched";
  return state.manual_watched ? "mark_unwatched" : "open_diary";
}

export function diaryViewFromQuery(value: string | null, filmId?: string): DiaryView {
  if (filmId) return "timeline";
  return value === "recent" ? "recent" : "timeline";
}

export function diaryEditorFilmId(
  pageFilmId?: string,
  selectedViewing?: Pick<ViewingView, "film_id"> | null,
) {
  return selectedViewing?.film_id || pageFilmId;
}

export function groupViewingEntries(entries: ViewingTimelineEntry[]): ViewingGroup[] {
  const groups = new Map<string, ViewingGroup>();
  entries.forEach((entry) => {
    const viewing = entry.viewing;
    let group: ViewingGroup;
    if (viewing.watched_at_precision === "unknown" || !viewing.watched_at) {
      group = { key: "unknown", kind: "unknown", entries: [] };
    } else if (viewing.watched_at_precision === "year") {
      group = {
        key: `year:${viewing.watched_at}`,
        kind: "year",
        year: viewing.watched_at,
        entries: [],
      };
    } else {
      const year = viewing.watched_at.slice(0, 4);
      const month = viewing.watched_at.slice(5, 7);
      group = {
        key: `month:${year}-${month}`,
        kind: "month",
        year,
        month,
        entries: [],
      };
    }
    const current = groups.get(group.key) || group;
    current.entries.push(entry);
    groups.set(group.key, current);
  });
  return Array.from(groups.values());
}

export function viewingDateMode(viewing?: ViewingView | null): ViewingDateMode {
  if (!viewing || viewing.watched_at_precision === "date" || viewing.watched_at_precision === "timestamp") {
    return "date";
  }
  return viewing.watched_at_precision === "year" ? "year" : "unknown";
}

export function createViewingDateDraft(viewing?: ViewingView | null, now = new Date()): ViewingDateDraft {
  const currentYear = String(now.getFullYear());
  return {
    mode: viewingDateMode(viewing),
    dateValue: viewing?.watched_at?.slice(0, 10) || todayLocalDate(now),
    yearValue: viewing?.watched_at_precision === "year"
      ? viewing.watched_at || currentYear
      : currentYear,
  };
}

export function viewingDraftWatchedAt(draft: ViewingDateDraft) {
  if (draft.mode === "unknown") return null;
  return draft.mode === "year" ? draft.yearValue : draft.dateValue;
}

export function viewingDateDraftValid(draft: ViewingDateDraft, now = new Date()) {
  if (draft.mode === "unknown") return true;
  if (draft.mode === "date") return Boolean(draft.dateValue);
  return /^[0-9]{4}$/.test(draft.yearValue)
    && Number(draft.yearValue) > 0
    && Number(draft.yearValue) <= now.getFullYear();
}

export function viewingDateDraftDirty(draft: ViewingDateDraft, viewing?: ViewingView | null) {
  if (!viewing) return true;
  const initialMode = viewingDateMode(viewing);
  if (draft.mode !== initialMode) return true;
  if (draft.mode === "unknown") return false;
  if (draft.mode === "year") return draft.yearValue !== viewing.watched_at;
  return draft.dateValue !== viewing.watched_at?.slice(0, 10);
}

export function todayLocalDate(now = new Date()) {
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}
