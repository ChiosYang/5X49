import type { MetadataSearchResult } from "@/types/movie";

export function parseTmdbId(value: string) {
  const trimmed = value.trim();
  const directId = trimmed.match(/^\d+$/);
  if (directId) return Number(directId[0]);

  const movieUrl = trimmed.match(/^https?:\/\/(?:www\.)?themoviedb\.org\/movie\/(\d+)(?:[-/?#].*)?$/i);
  return movieUrl ? Number(movieUrl[1]) : null;
}

export function parseMetadataSearchInput(value: string) {
  const yearMatch = value.match(/\b(19\d{2}|20\d{2})\b/);
  return {
    query: value.replace(/\b(19\d{2}|20\d{2})\b/, "").trim() || value.trim(),
    year: yearMatch ? Number(yearMatch[1]) : null,
  };
}

export function prependMetadataCandidate(
  candidates: MetadataSearchResult[],
  candidate: MetadataSearchResult,
) {
  return [candidate, ...candidates.filter((item) => item.tmdb_id !== candidate.tmdb_id)];
}
