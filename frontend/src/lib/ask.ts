import type { ExploreDimension, ExploreFilmPage } from "@/types/movie";

export interface AskPlan {
  genre: string | null;
  person: string | null;
  person_role: "any" | "director" | "actor";
  country: string | null;
  decade: number | null;
  view: "all" | "watched" | "unwatched";
  sort: "title" | "year";
  direction: "asc" | "desc";
  duration_min: number | null;
  duration_max: number | null;
  duration_min_inclusive: boolean;
  duration_max_inclusive: boolean;
  rating_min: number | null;
  rating_max: number | null;
}
export const emptyAskPlan: AskPlan = {
  genre: null, person: null, person_role: "any", country: null,
  decade: null, view: "all", sort: "title", direction: "asc",
  duration_min: null, duration_max: null, duration_min_inclusive: true,
  duration_max_inclusive: true, rating_min: null, rating_max: null,
};
export interface AskResolution {
  version: "ask.v2";
  status: "ready" | "needs_clarification" | "clarify" | "unsupported";
  plan: AskPlan | null;
  person_id: string | null;
  constraints: Array<{ dimension: ExploreDimension; key: string; label: string; role?: AskPlan["person_role"] }>;
  issues: Array<{
    field: "genre" | "person" | "country";
    code: "unknown_value" | "choose_person";
    candidates: Array<{ key: string; label: string; films: Array<{ title: string; year: number | null }> }>;
  }>;
  reason?: "negation" | "similarity" | "recommendation" | "unsupported_filter" | "multiple_values" | "non_search" | "ambiguous_rating" | "ambiguous_duration" | "ambiguous_request" | null;
  observation?: AskObservation | null;
  results?: Omit<ExploreFilmPage, "items"> & { items: Array<ExploreFilmPage["items"][number] & {
    matched_values: Array<{ field: "duration" | "rating"; value: number; unit: "seconds" | "stars"; source: "video" | "film_runtime" | "film_profile" }>;
  }> } | null;
}

export function askQueryPayload(resolution: AskResolution, offset = 0) {
  if (resolution.status !== "ready" || !resolution.plan) throw new Error("Ask plan is not resolved");
  return { plan: resolution.plan, person_id: resolution.person_id, confirmed: true, offset };
}

export function askErrorCode(status: number, body: { detail?: { code?: string } } | null): string {
  const allowed = new Set(["ask_not_configured", "ask_private_input", "ask_busy", "ask_timeout",
    "ask_invalid_response", "ask_provider_unavailable", "ask_provider_configuration", "ask_invalid_selection", "projection_unavailable"]);
  const code = body?.detail?.code;
  return code && allowed.has(code) ? code : status === 422 ? "invalid_request" : "unavailable";
}

export interface AskObservation {
  requested_model: string | null;
  response_model: string | null;
  latency_ms: number | null;
  input_tokens: number | null;
  output_tokens: number | null;
  total_tokens: number | null;
  cost_usd: number | null;
  cost_source: "unavailable" | "provider_usage.cost";
}

export const ASK_SESSION_KEY = "5x49.ask.confirmed.v2";

export function validAskNumbers(plan: AskPlan): boolean {
  for (const [field, maximum] of [["duration", 10000], ["rating", 5]] as const) {
    const lower = plan[`${field}_min`], upper = plan[`${field}_max`];
    if (![lower, upper].every(value => value === null || (Number.isInteger(value) && value >= 1 && value <= maximum))
      || (lower !== null && upper !== null && lower > upper)) return false;
  }
  if (typeof plan.duration_min_inclusive !== "boolean" || typeof plan.duration_max_inclusive !== "boolean"
    || (plan.duration_min === null && !plan.duration_min_inclusive)
    || (plan.duration_max === null && !plan.duration_max_inclusive)
    || (plan.duration_min !== null && plan.duration_min === plan.duration_max
      && (!plan.duration_min_inclusive || !plan.duration_max_inclusive))) return false;
  return true;
}

export function askNumericConditions(plan: AskPlan) {
  return (["duration", "rating"] as const).flatMap(field => (["min", "max"] as const).flatMap(bound => {
    const value = plan[`${field}_${bound}`];
    const inclusive = field === "rating" || plan[`duration_${bound}_inclusive`];
    return value === null ? [] : [{ field, value, operator: bound === "min" ? (inclusive ? "≥" : ">") : (inclusive ? "≤" : "<") }];
  }));
}

/** Cancellation invalidates even a response that already escaped AbortController. */
export function createAskRequestGate() {
  let generation = 0;
  let controller: AbortController | null = null;
  return {
    cancel() { generation += 1; controller?.abort(); controller = null; },
    begin() { controller?.abort(); controller = new AbortController(); return { id: ++generation, signal: controller.signal }; },
    current(id: number) { return id === generation; },
  };
}

/** Only the confirmed structured query is retained; never the typed question or results. */
export function parseAskSession(raw: string | null): ReturnType<typeof askQueryPayload> | null {
  try {
    const value = JSON.parse(raw || "null");
    const plan = value?.plan;
    if (!plan || !["genre", "person", "country"].every((key) => plan[key] === null || (typeof plan[key] === "string" && plan[key].length <= 100))
      || !["any", "director", "actor"].includes(plan.person_role)
      || !["all", "watched", "unwatched"].includes(plan.view)
      || !["title", "year"].includes(plan.sort) || !["asc", "desc"].includes(plan.direction)
      || !(plan.decade === null || (Number.isInteger(plan.decade) && plan.decade >= 1880 && plan.decade <= 2190 && plan.decade % 10 === 0))
      || !(value.person_id === null || (typeof value.person_id === "string" && /^person_[0-9a-f]{32}$/.test(value.person_id)))
      || !validAskNumbers(plan) || (!plan.person && (plan.person_role !== "any" || value.person_id !== null))
      || !Number.isInteger(value.offset) || value.offset < 0 || value.offset > 100000 || value.confirmed !== true) return null;
    return { plan: Object.fromEntries(Object.keys(emptyAskPlan).map((key) => [key, plan[key]])) as unknown as AskPlan,
      person_id: value.person_id, offset: value.offset, confirmed: true };
  } catch { return null; }
}

export function removeAskConstraint(plan: AskPlan, dimension: "genre" | "person" | "country" | "decade" | "view" | "duration" | "rating"): AskPlan {
  if (dimension === "duration") return { ...plan, duration_min: null, duration_max: null, duration_min_inclusive: true, duration_max_inclusive: true };
  if (dimension === "rating") return { ...plan, rating_min: null, rating_max: null };
  return { ...plan, [dimension]: dimension === "view" ? "all" : null,
    ...(dimension === "person" ? { person_role: "any" as const } : {}) };
}
