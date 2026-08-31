import type { FilmProfileState, ViewingTimelineEntry, ViewingView } from "@/types/movie";

export type WatchedAction = "mark_watched" | "mark_unwatched" | "open_diary";

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

export function viewingDateMode(viewing?: ViewingView | null): "date" | "year" | "unknown" {
  if (!viewing || viewing.watched_at_precision === "date" || viewing.watched_at_precision === "timestamp") {
    return "date";
  }
  return viewing.watched_at_precision === "year" ? "year" : "unknown";
}

export function todayLocalDate(now = new Date()) {
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}
