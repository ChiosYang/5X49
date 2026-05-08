import useSWR from "swr";
import { API } from "@/lib/api";

interface Movie {
  id: string;
  title: string;
  title_cn?: string;
  year: number;
  backdrop_path?: string;
  backdrop_local?: string;
  poster_local?: string;
  micro_genre?: string;
  genres?: string[];
  director?: string;
}

export function useLibrary() {
  return useSWR<Movie[]>(API.library());
}
