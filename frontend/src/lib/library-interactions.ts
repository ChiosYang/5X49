import type { FilmProfileState } from "../types/movie.ts";
import type { LibraryFilterKey } from "./library-care.ts";

export function matchesLibraryFilter(state: Pick<FilmProfileState, "watched" | "favorite">, filter: LibraryFilterKey) {
  return filter === "watched" ? Boolean(state.watched) : filter === "unwatched" ? !state.watched : filter === "favorite" ? Boolean(state.favorite) : true;
}

export function shouldRefreshLibraryEvent(reason: unknown) {
  return typeof reason === "string" && reason.length > 0;
}
