import type { AskPlan, AskResolution } from "./ask";
const PLAN_FIELDS = ["genre", "person", "person_role", "country", "decade", "view", "sort", "direction"];

export type DiscoveryStatus = "keyword" | "ready" | "needs_clarification" | "clarify" | "unsupported" | "unavailable" | "needs_ai";
export interface DiscoveryResolution extends Omit<AskResolution, "version" | "status"> {
  version: "discovery.v1";
  status: DiscoveryStatus;
  source: "local" | "ai";
  reason: string | null;
}
export interface DiscoveryState {
  plan?: AskPlan | null;
  personId?: string | null;
  edited?: boolean;
  source?: "local" | "ai";
  status?: DiscoveryStatus;
  reason?: string | null;
  offset?: number;
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
  // Keep both path patterns aligned with the provider-boundary guard in ask.py.
  const credentialOrRoot = /(?:\bsk-[A-Za-z0-9_-]{8,}|\bgh[pousr]_[A-Za-z0-9]{10,}|\b(?:api[_ -]?key|authorization|password|secret|token)\s*[:=]|\bbearer\s+\S+|[A-Za-z]:[\\/]|\\\\[^\s\\]+\\|file:\/\/|(?:^|[\s"'(\[{=，。！？；：])(?:~[^\\/\s]*[\\/]|\.{1,2}[\\/]|[\\/])[^\s"'<>)}\]]+)/i.test(value);
  const relativeMediaPath = /(?:^|[\s"'(\[{=，。！？；：\u0060])(?:[^\s\\/"'<>:|?*\u0060]+[\\/])+[^\\/\r\n]*\.(?:mkv|mp4|m4v|avi|mov|webm|wmv|mpg|mpeg|m2ts|ts|vob|iso|nfo|srt|ass|ssa|vtt|sub|idx|jpe?g|png|gif|webp|txt|json|xml|db|sqlite3?|env|pem|key)(?=$|[\s"')\]}>,.;:!?，。！？；：\u0060])/i.test(value);
  return credentialOrRoot || relativeMediaPath;
}
export function discoveryHref(query: string, state: DiscoveryState = {}) {
  const q = normalizeDiscoverySearch(query);
  if (!q) return "/explore";
  const params = new URLSearchParams({ q });
  if (state.plan) {
    params.set("p", JSON.stringify(state.plan));
    if (state.personId) params.set("person_id", state.personId);
    if (state.edited) params.set("edited", "1");
    if (state.source === "ai") params.set("source", "ai");
    if (state.offset && state.offset > 0) params.set("offset", String(state.offset));
  } else if (state.status && state.status !== "keyword") {
    params.set("state", state.status);
    if (state.reason) params.set("reason", state.reason);
  }
  return `/explore/search?${params}`;
}
export function resolutionHref(query: string, result: DiscoveryResolution) {
  return discoveryHref(query, { plan: result.plan, personId: result.person_id, source: result.source,
    status: result.status, reason: result.reason });
}
export function parseDiscoveryPlan(raw: string | undefined): AskPlan | null {
  try {
    if (!raw || raw.length > 2000) return null;
    const p = JSON.parse(raw);
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
  "ask_private_input", "projection_unavailable", "invalid_request", "unavailable"]);
export function discoveryReason(value: unknown) {
  return typeof value === "string" && DISCOVERY_REASONS.has(value) ? value : "unavailable";
}
export function discoveryFailure(reason: string): DiscoveryResolution {
  return { version: "discovery.v1", status: "unavailable", source: "local", reason: discoveryReason(reason),
    plan: null, person_id: null, constraints: [], issues: [], results: null };
}
