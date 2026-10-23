/** Explicit v2 plans stay in the URL; restoring them never performs inference. */
export interface SearchPerson { name: string; role: "any" | "actor" | "director"; exclude: boolean }
export interface SearchPlan {
  version: "search-plan.v2";
  genres: string[]; countries: string[]; exclude_genres: string[]; exclude_countries: string[];
  people: SearchPerson[];
  film_ids?: string[]; exclude_film_ids?: string[];
  year_min: number | null; year_max: number | null;
  duration_min: number | null; duration_max: number | null;
  duration_min_exclusive: boolean; duration_max_exclusive: boolean;
  view: "all" | "watched" | "unwatched";
  sort: "title" | "year"; direction: "asc" | "desc";
}
export const emptySearchPlan: SearchPlan = { version: "search-plan.v2", genres: [], countries: [],
  exclude_genres: [], exclude_countries: [], people: [], year_min: null, year_max: null,
  duration_min: null, duration_max: null, duration_min_exclusive: false, duration_max_exclusive: false,
  view: "all", sort: "title", direction: "asc" };
const fields = Object.keys(emptySearchPlan);
const term = (v: unknown): v is string => typeof v === "string" && v.trim().length > 0 && v.length <= 100;
export function isSearchPlan(value: unknown): value is SearchPlan {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const p = value as SearchPlan;
  if (fields.some(k => !Object.hasOwn(p, k)) || Object.keys(p).some(k => !fields.includes(k) && !["film_ids", "exclude_film_ids"].includes(k))
    || p.version !== "search-plan.v2" || !["all", "watched", "unwatched"].includes(p.view)
    || !["title", "year"].includes(p.sort) || !["asc", "desc"].includes(p.direction)) return false;
  for (const field of ["genres", "countries", "exclude_genres", "exclude_countries"] as const) {
    if (!Array.isArray(p[field]) || p[field].length > 10 || !p[field].every(term)
      || new Set(p[field]).size !== p[field].length) return false;
  }
  for (const field of ["film_ids", "exclude_film_ids"] as const) {
    const ids = p[field];
    if (ids !== undefined && (!Array.isArray(ids) || ids.length > 8
      || ids.some(id => typeof id !== "string" || !/^film_[0-9a-f]{32}$/.test(id))
      || new Set(ids).size !== ids.length)) return false;
  }
  if (!Array.isArray(p.people) || p.people.length > 8 || p.people.some(v => !v || typeof v !== "object"
    || Object.keys(v).length !== 3 || !term(v.name) || !["any", "actor", "director"].includes(v.role)
    || typeof v.exclude !== "boolean") || new Set(p.people.map(v => `${v.name.toLowerCase()}:${v.role}:${v.exclude}`)).size !== p.people.length) return false;
  for (const field of ["year", "duration"] as const) {
    const lower = p[`${field}_min`], upper = p[`${field}_max`];
    const min = field === "year" ? 1870 : 1, max = field === "year" ? 2100 : 10000;
    if ([lower, upper].some(n => n !== null && (!Number.isInteger(n) || n < min || n > max))
      || lower !== null && upper !== null && lower > upper) return false;
  }
  if (typeof p.duration_min_exclusive !== "boolean" || typeof p.duration_max_exclusive !== "boolean"
    || p.duration_min === null && p.duration_min_exclusive || p.duration_max === null && p.duration_max_exclusive
    || p.duration_min !== null && p.duration_min === p.duration_max && (p.duration_min_exclusive || p.duration_max_exclusive)) return false;
  return true;
}
export function parsePeopleIds(raw?: string): Record<string, string> | null {
  if (!raw) return {};
  try {
    if (raw.length > 500) return null;
    const value = JSON.parse(raw);
    if (!value || typeof value !== "object" || Array.isArray(value) || Object.keys(value).length > 8
      || Object.entries(value).some(([k, v]) => !/^[0-7]$/.test(k) || typeof v !== "string" || !/^person_[0-9a-f]{32}$/.test(v))) return null;
    return value;
  } catch { return null; }
}
export function removeSearchCondition(plan: SearchPlan, field: string, index?: number): SearchPlan {
  if (field === "film_ids" || field === "exclude_film_ids")
    return { ...plan, [field]: (plan[field] ?? []).filter((_, i) => i !== index) };
  if (["genres", "countries", "exclude_genres", "exclude_countries", "people"].includes(field)) {
    const key = field as "genres" | "countries" | "exclude_genres" | "exclude_countries" | "people";
    return { ...plan, [key]: plan[key].filter((_, i) => i !== index) };
  }
  if (field === "year") return { ...plan, year_min: null, year_max: null };
  if (field === "duration") return { ...plan, duration_min: null, duration_max: null,
    duration_min_exclusive: false, duration_max_exclusive: false };
  return plan;
}
export function removePersonSelection(ids: Record<string, string>, index: number): Record<string, string> {
  return Object.fromEntries(Object.entries(ids).filter(([k]) => Number(k) !== index)
    .map(([k, value]) => [String(Number(k) > index ? Number(k) - 1 : Number(k)), value]));
}
export function formatSearchRange(value: { min?: number | null; max?: number | null; min_exclusive?: boolean; max_exclusive?: boolean }) {
  const lower = value.min, upper = value.max;
  if (lower !== null && lower !== undefined && upper !== null && upper !== undefined) {
    if (lower === upper) return String(lower);
    return value.min_exclusive || value.max_exclusive
      ? `${value.min_exclusive ? ">" : "≥"} ${lower} · ${value.max_exclusive ? "<" : "≤"} ${upper}`
      : `${lower}–${upper}`;
  }
  return lower !== null && lower !== undefined ? `${value.min_exclusive ? ">" : "≥"} ${lower}`
    : `${value.max_exclusive ? "<" : "≤"} ${upper}`;
}
