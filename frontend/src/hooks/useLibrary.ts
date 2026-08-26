import useSWR from "swr";
import { API } from "@/lib/api";
import type { LibraryFilmSummary } from "@/types/movie";

export function useLibrary() {
  return useSWR<LibraryFilmSummary[]>(API.libraryFilms());
}
