import useSWR from "swr";
import { API } from "@/lib/api";
import type { LibraryFilmSummary, LibraryFilmPage } from "@/types/movie";

export function useLibrary() {
  return useSWR<LibraryFilmSummary[]>(API.libraryFilms());
}

export function useLibraryPage(params: URLSearchParams) {
  return useSWR<LibraryFilmPage>(API.libraryFilmPage(params));
}
