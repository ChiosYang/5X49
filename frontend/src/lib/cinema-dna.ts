import type { DnaDimension, DnaMetric } from "@/types/cinema-dna";

export const DNA_DIMENSIONS = ["genre", "person", "country", "decade"] as const;

export interface DnaQuery {
  dimension: DnaDimension;
  metric: DnaMetric;
  facet: string | null;
  offset: number;
  contributorsOffset: number;
}

const offset = (value: string | null) => {
  const number = value && /^\d+$/.test(value) ? Number(value) : 0;
  return Number.isSafeInteger(number) && number >= 0 ? number : 0;
};

export function parseDnaQuery(params: Pick<URLSearchParams, "get">): DnaQuery {
  const dimension = params.get("dimension");
  return {
    dimension: DNA_DIMENSIONS.includes(dimension as DnaDimension) ? dimension as DnaDimension : "genre",
    metric: params.get("metric") === "preference" ? "preference" : "exposure",
    facet: params.get("facet")?.replace(/^concept_/, "con_") || null,
    offset: offset(params.get("offset")),
    contributorsOffset: offset(params.get("contributors_offset")),
  };
}

export function dnaHref(query: DnaQuery) {
  const params = new URLSearchParams({ view: "dna" });
  if (query.dimension !== "genre") params.set("dimension", query.dimension);
  if (query.metric !== "exposure") params.set("metric", query.metric);
  if (query.facet) params.set("facet", query.facet);
  if (query.offset) params.set("offset", String(query.offset));
  if (query.facet && query.contributorsOffset) params.set("contributors_offset", String(query.contributorsOffset));
  return `/diary?${params}`;
}

export function changeDnaQuery(query: DnaQuery, patch: Partial<DnaQuery>): DnaQuery {
  if (patch.dimension !== undefined && patch.dimension !== query.dimension) {
    return { ...query, ...patch, facet: null, offset: 0, contributorsOffset: 0 };
  }
  if (patch.metric !== undefined && patch.metric !== query.metric) {
    return { ...query, ...patch, offset: 0, contributorsOffset: 0 };
  }
  if (patch.facet !== undefined || patch.offset !== undefined) {
    return { ...query, ...patch, contributorsOffset: 0, ...(patch.offset !== undefined ? { facet: null } : {}) };
  }
  return { ...query, ...patch };
}

export function isDnaCacheKey(key: unknown, base: string): boolean {
  return typeof key === "string" && (key === base || key.startsWith(`${base}/`) || key.startsWith(`${base}?`));
}
