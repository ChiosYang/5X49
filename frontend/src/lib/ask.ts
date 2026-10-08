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
}
export const emptyAskPlan: AskPlan = {
  genre: null, person: null, person_role: "any", country: null,
  decade: null, view: "all", sort: "title", direction: "asc",
};
export interface AskResolution {
  version: "ask.v1";
  status: "ready" | "needs_clarification" | "clarify" | "unsupported";
  plan: AskPlan | null;
  person_id: string | null;
  constraints: Array<{ dimension: ExploreDimension; key: string; label: string; role?: AskPlan["person_role"] }>;
  issues: Array<{
    field: "genre" | "person" | "country";
    code: "unknown_value" | "choose_person";
    candidates: Array<{ key: string; label: string; films: Array<{ title: string; year: number | null }> }>;
  }>;
  results?: ExploreFilmPage | null;
}

export function askQueryPayload(resolution: AskResolution, offset = 0) {
  if (resolution.status !== "ready" || !resolution.plan) throw new Error("Ask plan is not resolved");
  return { plan: resolution.plan, person_id: resolution.person_id, confirmed: true, offset };
}

export function askErrorCode(status: number, body: { detail?: { code?: string } } | null): string {
  const allowed = new Set(["ask_not_configured", "ask_private_input", "ask_busy", "ask_timeout",
    "ask_invalid_response", "ask_provider_unavailable", "ask_invalid_selection", "projection_unavailable"]);
  const code = body?.detail?.code;
  return code && allowed.has(code) ? code : status === 422 ? "invalid_request" : "unavailable";
}

export const ASK_SESSION_KEY = "5x49.ask.confirmed.v1";

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
      || !Number.isInteger(value.offset) || value.offset < 0 || value.confirmed !== true) return null;
    return { plan: Object.fromEntries(Object.keys(emptyAskPlan).map((key) => [key, plan[key]])) as unknown as AskPlan,
      person_id: value.person_id, offset: value.offset, confirmed: true };
  } catch { return null; }
}

export function removeAskConstraint(plan: AskPlan, dimension: "genre" | "person" | "country" | "decade" | "view"): AskPlan {
  return { ...plan, [dimension]: dimension === "view" ? "all" : null,
    ...(dimension === "person" ? { person_role: "any" as const } : {}) };
}
