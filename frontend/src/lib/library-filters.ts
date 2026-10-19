import type { LibraryQueryState } from "./library-care.ts";

export const LIBRARY_RANGES = [
  { key: "duration", min: 1, max: 10000 },
  { key: "rating", min: 1, max: 5 },
  { key: "year", min: 1870, max: 2100 },
] as const;
export type LibraryRange = typeof LIBRARY_RANGES[number]["key"];
export type LibraryRangeField = `${LibraryRange}_${"min" | "max"}`;
export type LibraryRanges = Partial<Record<LibraryRangeField, string>>;

/** Count committed condition groups, including invalid ranges needing correction. */
export function libraryFilterCount(state: LibraryQueryState): number {
  return Number(Boolean(state.query)) + Number(state.filter === "watched" || state.filter === "unwatched")
    + Number(Boolean(state.favorite || state.filter === "favorite"))
    + LIBRARY_RANGES.filter(({ key }) => state[`${key}_min`] || state[`${key}_max`]).length;
}

export function readLibraryRanges(params: Record<string, string | string[] | undefined>): LibraryRanges {
  const ranges: LibraryRanges = {};
  for (const { key } of LIBRARY_RANGES) {
    for (const suffix of ["min", "max"] as const) {
      const field = `${key}_${suffix}` as const;
      const raw = params[field];
      ranges[field] = (Array.isArray(raw) ? raw[0] : raw)?.trim().slice(0, 40) ?? "";
    }
  }
  return ranges;
}

export function invalidLibraryRanges(ranges: LibraryRanges): LibraryRange[] {
  return LIBRARY_RANGES.filter(({ key, min, max }) => {
    const lower = ranges[`${key}_min`] || "", upper = ranges[`${key}_max`] || "";
    const invalid = (value: string) => value !== "" && (!/^\d+$/.test(value) || Number(value) < min || Number(value) > max);
    return invalid(lower) || invalid(upper) || (lower !== "" && upper !== "" && Number(lower) > Number(upper));
  }).map(({ key }) => key);
}

export function clearLibraryFilters(state: LibraryQueryState): LibraryQueryState {
  return { view: state.view, sort: state.sort, direction: state.direction, filter: "all", page: 1 };
}
