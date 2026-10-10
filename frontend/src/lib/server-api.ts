import "server-only";

import type {
  ExploreContext,
  ExploreFilmPage,
  ExploreOverview,
  LibraryFilmDetail,
  LibraryFilmSummary,
  LibraryFilmPage,
  MissingLibraryItemsResponse,
  OrganizationCandidate,
  RootVideo,
} from "@/types/movie";
import { buildExploreContextSearchParams, buildExploreSearchParams, type ExploreQueryState } from "@/lib/explore";

import { getBackendUrl as backendUrl } from "@/lib/backend-proxy";

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

export async function getExploreFilms(query: ExploreQueryState): Promise<ExploreFilmPage> {
  const params = buildExploreSearchParams(query);
  params.set("limit", "40");
  const response = await fetch(`${backendUrl()}/explore/films?${params}`, { cache: "no-store" });
  if (!response.ok) throw new Error(`Failed to fetch Explore Films: ${response.status}`);
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
