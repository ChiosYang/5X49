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
