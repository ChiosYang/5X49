import type { AskPlan, AskResolution } from "./ask";
import { isSearchPlan, type SearchPlan } from "./search-plan.ts";
const PLAN_FIELDS = ["genre", "person", "person_role", "country", "decade", "view", "sort", "direction"];

export type DiscoveryStatus = "keyword" | "ready" | "needs_clarification" | "clarify" | "unsupported" | "unavailable" | "needs_ai";
export interface DiscoveryResolution extends Omit<AskResolution, "version" | "status" | "plan" | "constraints" | "issues"> {
  version: "discovery.v1" | "discovery.v2" | "discovery.v3";
  plan: AskPlan | SearchPlan | null;
  people_ids?: Record<string, string>;
  keyword_query?: string;
  constraints: Array<{ dimension: "genre" | "person" | "country" | "decade" | "year" | "duration" | "film";
    key: string; label: string; role?: "any" | "actor" | "director"; id?: string; field?: string; index?: number;
    labels?: Record<string, string>; exclude?: boolean; min?: number | null; max?: number | null; min_exclusive?: boolean; max_exclusive?: boolean }>;
  issues: Array<{ field: string; index?: number; code: "unknown_value" | "choose_person" | "choose_reference";
    candidates: Array<{ key: string; label: string; year?: number | null; films?: Array<{ title: string; year: number | null }> }> }>;
  status: DiscoveryStatus;
  source: "local" | "ai";
  reason: string | null;
  snapshot?: string;
  edited?: boolean;
  semantic?: { text: string; evaluation_only: boolean; requires_submit?: boolean; reference_id?: string | null;
    route?: "semantic" | "hybrid"; mode?: "factual" | "exploratory" | "reference";
    order?: "relevance" | "title" | "year"; fallback?: string | null; indexed_films?: number; bounded_candidates?: number };
}
export interface DiscoveryState {
  plan?: AskPlan | SearchPlan | null;
  peopleIds?: Record<string, string>;
  personId?: string | null;
  edited?: boolean;
  source?: "local" | "ai";
  status?: DiscoveryStatus;
  reason?: string | null;
  offset?: number;
  semanticSnapshot?: string | null;
  semanticOrder?: "relevance" | "title" | "year";
}
export interface DiscoverySubmission {
  people_ids?: Record<string, string>;
  reference_id?: string;
  edited_plan?: SearchPlan;
  evaluation_only?: boolean;
}
export function parseSemanticSnapshot(value?: string) {
  return value && /^ds_[0-9a-f]{32}$/.test(value) ? value : null;
}

export function normalizeDiscoverySearch(value?: string | string[] | null) {
  return (Array.isArray(value) ? value[0] : value)?.trim().slice(0, 600) ?? "";
}
export function discoveryKeywords(query: string) {
  // Mirror discovery_search.keyword_text, keeping the original query in the URL
  // and input. Only leading find/找 commands affect the local lookup term.
  const match = /^(?:please\s+)?find\s+(.+)$/i.exec(query) ?? /^(?:请)?(?:帮我)?找(?:一下)?\s*(.+)$/.exec(query);
  return match ? match[1].trim() : query;
}
export function hasPrivateDiscoveryInput(value: string) {
  return hasPrivateInputForm(value) || hasPrivateInputForm(value.normalize("NFKC"));
}
function hasPrivateInputForm(value: string) {
  // Keep both path patterns aligned with the shared search_privacy.py guard.
  const credentialOrRoot = /(?:\bsk-[A-Za-z0-9_-]{8,}|\bgh[pousr]_[A-Za-z0-9]{10,}|\b(?:api[_ -]?key|authorization|password|secret|token)\s*[:=]|\bbearer\s+\S+|[A-Za-z]:[\\/]|\\\\[^\s\\]+\\|file:\/\/|(?:^|[\s"'(\[{=，。！？；：\u0060])(?:~[^\\/\s]*[\\/]|\.{1,2}[\\/]|[\\/])[^\s"'<>)}\]]+)/i.test(value);
  const relativeMediaPath = /(?:^|[\s"'(\[{=，。！？；：\u0060])(?:[^\s\\/"'<>:|?*\u0060]+[\\/]+)+[^\\/\r\n]*\.(?:mkv|mp4|m4v|avi|mov|webm|wmv|mpg|mpeg|m2ts|ts|vob|iso|nfo|srt|ass|ssa|vtt|sub|idx|jpe?g|png|gif|webp|txt|json|xml|db|sqlite3?|env|pem|key)(?=$|[\s"')\]}>,.;:!?，。！？；：\u0060])/i.test(value);
  return credentialOrRoot || relativeMediaPath;
}
export function discoveryHref(query: string, state: DiscoveryState = {}) {
  const q = normalizeDiscoverySearch(query);
  if (!q) return "/explore";
  const params = new URLSearchParams({ q });
  if (state.plan) {
    params.set("p", JSON.stringify(state.plan));
    if (state.peopleIds && Object.keys(state.peopleIds).length) params.set("people_ids", JSON.stringify(state.peopleIds));
    if (state.personId) params.set("person_id", state.personId);
    if (state.edited) params.set("edited", "1");
    if (state.source === "ai") params.set("source", "ai");
    if (state.offset && state.offset > 0) params.set("offset", String(state.offset));
    if (state.semanticSnapshot) {
      params.set("semantic_snapshot", state.semanticSnapshot);
      if (state.semanticOrder && state.semanticOrder !== "relevance") params.set("order", state.semanticOrder);
    }
  } else if (state.status && state.status !== "keyword") {
    params.set("state", state.status);
    if (state.reason) params.set("reason", state.reason);
  }
  return `/explore/search?${params}`;
}
export function resolutionHref(query: string, result: DiscoveryResolution) {
  return discoveryHref(query, { plan: result.plan, personId: result.person_id, peopleIds: result.people_ids, source: result.source,
    status: result.status, reason: result.reason, edited: result.edited,
    semanticSnapshot: result.snapshot, semanticOrder: result.semantic?.order });
}
export function parseDiscoveryPlan(raw: string | undefined): AskPlan | SearchPlan | null {
  try {
    if (!raw || raw.length > 6000) return null;
    const p = JSON.parse(raw);
    if (isSearchPlan(p)) return p;
    if (!p || typeof p !== "object" || Object.keys(p).length !== PLAN_FIELDS.length
      || Object.keys(p).some(key => !PLAN_FIELDS.includes(key))
      || !["genre", "country", "person"].every(key => p[key] === null || typeof p[key] === "string" && p[key].trim().length > 0 && p[key].length <= 100)
      || !["all", "watched", "unwatched"].includes(p.view)
      || !["title", "year"].includes(p.sort) || !["asc", "desc"].includes(p.direction)
      || !["any", "director", "actor"].includes(p.person_role)
      || p.person === null && p.person_role !== "any"
      || !(p.decade === null || Number.isInteger(p.decade) && p.decade >= 1880 && p.decade <= 2190 && p.decade % 10 === 0)) return null;
    return p as AskPlan;
  } catch { return null; }
}

export const DISCOVERY_REASONS = new Set(["non_search", "similarity", "recommendation", "negation", "multiple_values",
  "unsupported_filter", "ambiguous_request", "incomplete_request", "long_keywords", "submit_to_interpret",
  "ask_not_configured", "ask_busy", "ask_timeout", "ask_invalid_response", "ask_provider_unavailable",
  "ask_private_input", "projection_unavailable", "invalid_request", "unavailable",
  "search_evaluation_disabled", "search_evaluation_config_invalid", "search_not_configured", "search_budget_blocked",
  "search_provider_unavailable", "search_preflight_unavailable", "search_preflight_required", "search_price_changed",
  "search_privacy_unverified", "search_public_logging_consent_required", "search_provider_evaluation_only",
  "search_route_uncertain", "search_reference_choice", "reference_missing_content", "search_cancelled",
  "search_snapshot_invalid", "search_snapshot_expired", "search_snapshot_stale", "search_snapshot_requires_submit",
  "search_index_stale", "search_index_invalid", "search_source_changed", "search_input_not_approved", "search_input_outside_scope",
  "unsupported_content_negation", "unknown_film", "ambiguous_film", "ambiguous_reference"]);
export function discoveryReason(value: unknown) {
  return typeof value === "string" && DISCOVERY_REASONS.has(value) ? value : "unavailable";
}
export function discoveryFailure(reason: string): DiscoveryResolution {
  return { version: "discovery.v1", status: "unavailable", source: "local", reason: discoveryReason(reason),
    plan: null, person_id: null, constraints: [], issues: [], results: null };
}
