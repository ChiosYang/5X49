"use client";

import { createContext, type ReactNode, useContext, useMemo, useState } from "react";
import { API } from "@/lib/api";
import type { MovieDetail } from "@/types/movie";
import MovieBackdrop from "./MovieBackdrop";
import MoviePoster from "./MoviePoster";

type MovieArtworkState = Pick<
  MovieDetail,
  "poster_local" | "backdrop_local" | "poster_path" | "backdrop_path" | "metadata_updated_at"
>;

interface MovieArtworkContextValue {
  posterSrc: string | null;
  backdropSrc: string | null;
  updateFromMovie: (movie: MovieDetail) => void;
}

const MovieArtworkContext = createContext<MovieArtworkContextValue | null>(null);

function movieToArtwork(movie: MovieDetail): MovieArtworkState {
  return {
    poster_local: movie.poster_local,
    backdrop_local: movie.backdrop_local,
    poster_path: movie.poster_path,
    backdrop_path: movie.backdrop_path,
    metadata_updated_at: movie.metadata_updated_at,
  };
}

function artworkSrc(path?: string | null, version?: string | null) {
  if (!path) return null;

  const cacheVersion = version ? `?v=${encodeURIComponent(version)}` : "";
  return `${API.mediaUrl(path)}${cacheVersion}`;
}

export function MovieArtworkProvider({
  initialMovie,
  children,
}: {
  initialMovie: MovieDetail;
  children: ReactNode;
}) {
  const [artwork, setArtwork] = useState<MovieArtworkState>(() => movieToArtwork(initialMovie));

  const value = useMemo<MovieArtworkContextValue>(
    () => ({
      posterSrc: artworkSrc(artwork.poster_local, artwork.metadata_updated_at),
      backdropSrc: artworkSrc(artwork.backdrop_local, artwork.metadata_updated_at),
      updateFromMovie: (movie) => setArtwork(movieToArtwork(movie)),
    }),
    [artwork]
  );

  return (
    <MovieArtworkContext.Provider value={value}>
      {children}
    </MovieArtworkContext.Provider>
  );
}

export function useMovieArtwork() {
  const context = useContext(MovieArtworkContext);
  if (!context) {
    throw new Error("useMovieArtwork must be used within MovieArtworkProvider");
  }
  return context;
}

export function MovieArtworkBackdrop({ title }: { title: string }) {
  const { backdropSrc } = useMovieArtwork();
  return <MovieBackdrop src={backdropSrc} title={title} />;
}

export function MovieArtworkPoster({ title }: { title: string }) {
  const { posterSrc } = useMovieArtwork();
  return posterSrc ? <MoviePoster src={posterSrc} title={title} /> : null;
}
