import useSWR from "swr";
import { API } from "@/lib/api";
import type { LibraryMovie } from "@/types/movie";

export function useLibrary() {
  return useSWR<LibraryMovie[]>(API.library());
}
