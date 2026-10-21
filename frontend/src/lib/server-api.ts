import "server-only";

import type {
  ExploreContext,
  ExploreCollections,
  ExploreFilmPage,
  ExploreOverview,
  CollectionCatalog,
  CollectionCategory,
  LocalCollectionPage,
  ExploreFacetPage,
  LibraryFilmDetail,
  LibraryFilmSummary,
  LibraryFilmPage,
  MissingLibraryItemsResponse,
  OrganizationCandidate,
  RootVideo,
} from "@/types/movie";
import { buildExploreContextSearchParams, buildExploreSearchParams, type ExploreQueryState } from "@/lib/explore";

import { getBackendUrl as backendUrl } from "@/lib/backend-proxy";
import { discoveryFailure, discoveryReason, type DiscoveryResolution } from "@/lib/discovery-search";

export async function getDiscoveryResolution(question: string, locale: string, restored?: object): Promise<DiscoveryResolution> {
  try {
    const response = await fetch(`${backendUrl()}/explore/search/${restored ? "query" : "interpret"}`, {
      method: "POST", cache: "no-store", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(restored ? { question, ...restored } : { question, locale, allow_ai: false }),
    });
    const result = await response.json().catch(() => null);
    return response.ok ? result as DiscoveryResolution : discoveryFailure(discoveryReason(result?.detail?.code));
  } catch { return discoveryFailure("unavailable"); }
}

export async function getLibraryFilm(filmId: string): Promise<LibraryFilmDetail | null> {
  const response = await fetch(`${backendUrl()}/library/films/${encodeURIComponent(filmId)}`, {
    cache: "no-store",
  });
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(`Failed to fetch Film detail: ${response.status}`);
  return response.json();
}

export async function getLibraryFilms(query = ""): Promise<LibraryFilmSummary[]> {
  const params = new URLSearchParams();
  if (query.trim()) params.set("q", query.trim());
  const response = await fetch(`${backendUrl()}/library/films${params.size ? `?${params}` : ""}`, { cache: "no-store" });
  if (!response.ok) throw new Error(`Failed to fetch library: ${response.status}`);
  return response.json();
}

export async function getLibraryFilmPage(params: URLSearchParams): Promise<LibraryFilmPage> {
  const response = await fetch(`${backendUrl()}/library/films/page?${params}`, { cache: "no-store" });
  if (!response.ok) throw new Error(`Failed to fetch library page: ${response.status}`);
  return response.json();
}

export async function getExploreOverview(): Promise<ExploreOverview> {
  const response = await fetch(`${backendUrl()}/explore`, { cache: "no-store" });
  if (!response.ok) throw new Error(`Failed to fetch Explore overview: ${response.status}`);
  return response.json();
}

export async function getExploreCollections(view: ExploreQueryState["view"]): Promise<ExploreCollections> {
  const response = await fetch(`${backendUrl()}/explore/collections?view=${view}`, { cache: "no-store" });
  if (!response.ok) throw new Error(`Failed to fetch Explore collections: ${response.status}`);
  return response.json();
}

export async function getExploreFilms(query: ExploreQueryState): Promise<ExploreFilmPage> {
  const params = buildExploreSearchParams(query);
  params.set("limit", "40");
  const response = await fetch(`${backendUrl()}/explore/films?${params}`, { cache: "no-store" });
  if (!response.ok) throw new Error(`Failed to fetch Explore Films: ${response.status}`);
  return response.json();
}

export async function getCollectionCatalog({ category = "all", query = "", featured = false, offset = 0, limit = 24 }: {
  category?: CollectionCategory; query?: string; featured?: boolean; offset?: number; limit?: number;
} = {}): Promise<CollectionCatalog> {
  const params = new URLSearchParams({ category, q: query, featured: String(featured), offset: String(offset), limit: String(limit) });
  const response = await fetch(`${backendUrl()}/explore/catalog?${params}`, { cache: "no-store" });
  if (!response.ok) throw new Error(`Failed to fetch collection directory: ${response.status}`);
  return response.json();
}

export async function getLocalCollection(kind: string, key: string, query: ExploreQueryState): Promise<LocalCollectionPage | null> {
  const response = await fetch(`${backendUrl()}/explore/collections/${encodeURIComponent(kind)}/${encodeURIComponent(key)}?${buildExploreSearchParams(query)}`, { cache: "no-store" });
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(`Failed to fetch local collection: ${response.status}`);
  return response.json();
}

export async function getLocalPeople(query: string, offset = 0): Promise<ExploreFacetPage> {
  const params = new URLSearchParams({ q: query.slice(0, 100), limit: "12", offset: String(offset) });
  const response = await fetch(`${backendUrl()}/explore/facets/person?${params}`, { cache: "no-store" });
  if (!response.ok) throw new Error(`Failed to fetch local people: ${response.status}`);
  return response.json();
}

export async function getExploreContext(query: ExploreQueryState): Promise<ExploreContext> {
  const params = buildExploreContextSearchParams(query);
  const response = await fetch(`${backendUrl()}/explore/context?${params}`, { cache: "no-store" });
  if (!response.ok) throw new Error(`Failed to fetch Explore context: ${response.status}`);
  return response.json();
}

export async function getRootVideos(): Promise<RootVideo[]> {
  const response = await fetch(`${backendUrl()}/library/root-videos`, { cache: "no-store" });
  if (!response.ok) throw new Error(`Failed to fetch root videos: ${response.status}`);
  return response.json();
}

export async function getLibraryOrganizationCandidates(): Promise<OrganizationCandidate[]> {
  const response = await fetch(`${backendUrl()}/library/organization/candidates`, {
    cache: "no-store",
  });
  if (!response.ok) throw new Error(`Failed to fetch organization candidates: ${response.status}`);
  return response.json();
}

export async function getMissingLibraryItems(): Promise<MissingLibraryItemsResponse> {
  const response = await fetch(`${backendUrl()}/library/missing`, { cache: "no-store" });
  if (!response.ok) throw new Error(`Failed to fetch missing Library items: ${response.status}`);
  return response.json();
}
