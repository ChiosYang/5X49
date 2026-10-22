import type { CollectionCategory, CollectionKind, LocalCollection } from "@/types/movie";

export const COLLECTION_CATEGORIES = ["all", "director", "country", "decade"] as const;

export function collectionCategory(value?: string | string[]): CollectionCategory {
  const first = Array.isArray(value) ? value[0] : value;
  return COLLECTION_CATEGORIES.find(item => item === first) ?? "all";
}

export function validCollection(kind: string, key: string): kind is CollectionKind {
  if (kind === "director" || kind === "person") return /^person_[a-f0-9]{32}$/.test(key);
  if (kind === "country") return /^[A-Z]{2}$/.test(key);
  return kind === "decade" && /^[0-9]{3}0$/.test(key);
}

export function collectionHref(item: Pick<LocalCollection, "kind" | "key">) {
  return `/explore/collections/${item.kind}/${encodeURIComponent(item.key)}`;
}

export function catalogHref(category: CollectionCategory = "all", offset = 0) {
  const params = new URLSearchParams();
  if (category !== "all") params.set("category", category);
  if (offset > 0) params.set("offset", String(offset));
  return `/explore${params.size ? `?${params}` : ""}`;
}

export function hasLegacyExploreQuery(params: Record<string, unknown>) {
  return ["genre", "person", "person_match", "country", "decade", "view", "sort", "dir"]
    .some(key => params[key] !== undefined);
}

export function discoverySearchHref(query: string, page = 1, peopleOffset = 0, collectionOffset = 0) {
  const params = new URLSearchParams();
  if (query) params.set("q", query);
  if (page > 1) params.set("page", String(page));
  if (peopleOffset > 0) params.set("people_offset", String(peopleOffset));
  if (collectionOffset > 0) params.set("collection_offset", String(collectionOffset));
  return `/explore/search${params.size ? `?${params}` : ""}`;
}
