import "server-only";

import type {
  LibraryFilmDetail,
  LibraryFilmSummary,
  MissingLibraryItemsResponse,
  OrganizationCandidate,
  RootVideo,
} from "@/types/movie";

const backendUrl = () =>
  process.env.BACKEND_URL || (
    process.env.NODE_ENV === "development"
      ? "http://127.0.0.1:8000"
      : "http://backend:8000"
  );

export async function getLibraryFilm(filmId: string): Promise<LibraryFilmDetail | null> {
  const response = await fetch(`${backendUrl()}/library/films/${encodeURIComponent(filmId)}`, {
    cache: "no-store",
  });
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(`Failed to fetch Film detail: ${response.status}`);
  return response.json();
}

export async function getLibraryFilms(): Promise<LibraryFilmSummary[]> {
  const response = await fetch(`${backendUrl()}/library/films`, { cache: "no-store" });
  if (!response.ok) throw new Error(`Failed to fetch library: ${response.status}`);
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
