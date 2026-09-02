import type {
  ExploreDimension,
  ExploreDirection,
  ExploreSort,
  ExploreView,
  GraphNode,
} from "@/types/movie";

export const EXPLORE_DIMENSIONS = ["genre", "person", "country", "decade"] as const;

export interface ExploreQueryState {
  genre: string[];
  person: string[];
  country: string[];
  decade: string[];
  view: ExploreView;
  sort: ExploreSort;
  dir: ExploreDirection;
  offset: number;
}

type SearchValues = Record<string, string | string[] | undefined>;

const RESOURCE_PATTERNS = {
  genre: /^(?:con|concept)_[0-9a-f]{32}$/,
  person: /^person_[0-9a-f]{32}$/,
  country: /^[A-Z]{2}$/,
  decade: /^[0-9]{3}0$/,
} satisfies Record<ExploreDimension, RegExp>;

const values = (value?: string | string[]) => Array.isArray(value) ? value : value ? [value] : [];
const first = (value?: string | string[]) => values(value)[0];

export function parseExploreQuery(input: SearchValues): ExploreQueryState {
  const normalized = Object.fromEntries(
    EXPLORE_DIMENSIONS.map((dimension) => [
      dimension,
      [...new Set(
        values(input[dimension])
          .filter((value) => RESOURCE_PATTERNS[dimension].test(value))
          .map((value) => dimension === "genre" ? value.replace(/^concept_/, "con_") : value),
      )].sort(),
    ]),
  ) as Pick<ExploreQueryState, ExploreDimension>;
  const view = first(input.view);
  const sort = first(input.sort);
  const direction = first(input.dir);
  const offset = Number.parseInt(first(input.offset) || "0", 10);
  const safeSort: ExploreSort = sort === "year" ? "year" : "title";
  return {
    ...normalized,
    view: view === "watched" || view === "unwatched" ? view : "all",
    sort: safeSort,
    dir: direction === "asc" || direction === "desc"
      ? direction
      : safeSort === "year" ? "desc" : "asc",
    offset: Number.isFinite(offset) && offset >= 0 ? offset : 0,
  };
}

export function buildExploreSearchParams(query: ExploreQueryState) {
  const params = new URLSearchParams();
  EXPLORE_DIMENSIONS.forEach((dimension) => {
    [...new Set(query[dimension])].sort().forEach((value) => params.append(dimension, value));
  });
  if (query.view !== "all") params.set("view", query.view);
  if (query.sort !== "title") params.set("sort", query.sort);
  const defaultDirection = query.sort === "year" ? "desc" : "asc";
  if (query.dir !== defaultDirection) params.set("dir", query.dir);
  if (query.offset > 0) params.set("offset", String(query.offset));
  return params;
}

export function buildExploreContextSearchParams(query: ExploreQueryState, limit = 6) {
  const params = new URLSearchParams();
  EXPLORE_DIMENSIONS.forEach((dimension) => {
    [...new Set(query[dimension])].sort().forEach((value) => params.append(dimension, value));
  });
  if (query.view !== "all") params.set("view", query.view);
  params.set("limit", String(limit));
  return params;
}

export function exploreHref(query: ExploreQueryState) {
  const params = buildExploreSearchParams(query);
  return `/explore${params.size ? `?${params}` : ""}`;
}

export function hasExploreFilters(query: ExploreQueryState) {
  return EXPLORE_DIMENSIONS.some((dimension) => query[dimension].length > 0);
}

export function initialExploreLens(query: ExploreQueryState): ExploreDimension | null {
  return EXPLORE_DIMENSIONS.find((dimension) => query[dimension].length > 0) ?? null;
}

export function exploreNavigation(query: ExploreQueryState, intent: "filter" | "page") {
  return {
    href: exploreHref(query),
    scroll: false as const,
    focusResults: intent === "page",
  };
}

export function withExploreFacet(
  query: ExploreQueryState,
  dimension: ExploreDimension,
  key: string,
) {
  const selected = new Set(query[dimension]);
  if (selected.has(key)) selected.delete(key);
  else selected.add(key);
  return { ...query, [dimension]: [...selected].sort(), offset: 0 };
}

export function withoutExploreFacet(
  query: ExploreQueryState,
  dimension: ExploreDimension,
  key: string,
) {
  return {
    ...query,
    [dimension]: query[dimension].filter((value) => value !== key),
    offset: 0,
  };
}

export function clearExploreFilters(query: ExploreQueryState) {
  return { ...query, genre: [], person: [], country: [], decade: [], offset: 0 };
}

export function formatExploreFacetLabel(
  dimension: ExploreDimension,
  key: string,
  fallbackLabel: string,
  locale: string,
  localizeCountry = true,
) {
  if (dimension === "country") {
    if (!localizeCountry) return key;
    return typeof Intl.DisplayNames !== "undefined"
      ? new Intl.DisplayNames([locale], { type: "region" }).of(key) || key
      : key;
  }
  if (dimension === "decade") return locale === "zh" ? `${key}年代` : `${key}s`;
  return fallbackLabel;
}

export function graphNodeHref(node: Pick<GraphNode, "id" | "entity_type" | "concept_kind" | "in_library">, rootFilmId: string) {
  if (node.entity_type === "film" && node.in_library && node.id !== rootFilmId) {
    return `/library/${node.id}`;
  }
  if (node.entity_type === "person") {
    return `/explore?person=${encodeURIComponent(node.id)}`;
  }
  if (node.entity_type === "concept" && node.concept_kind === "genre") {
    return `/explore?genre=${encodeURIComponent(node.id)}`;
  }
  return null;
}
