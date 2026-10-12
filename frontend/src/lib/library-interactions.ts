import type { FilmProfileState } from "../types/movie.ts";
import type { LibraryFilterKey } from "./library-care.ts";

export function matchesLibraryFilter(
  state: Pick<FilmProfileState, "watched" | "favorite"> & Partial<Pick<FilmProfileState, "rating">>,
  filter: LibraryFilterKey, favorite = false, ratingMin?: number, ratingMax?: number,
) {
  if ((ratingMin !== undefined || ratingMax !== undefined) && state.rating == null) return false;
  if (ratingMin !== undefined && state.rating! < ratingMin) return false;
  if (ratingMax !== undefined && state.rating! > ratingMax) return false;
  return (!favorite || Boolean(state.favorite)) && (filter === "watched" ? Boolean(state.watched) : filter === "unwatched" ? !state.watched : filter === "favorite" ? Boolean(state.favorite) : true);
}

export function shouldRefreshLibraryEvent(reason: unknown) {
  return typeof reason === "string" && reason.length > 0;
}
