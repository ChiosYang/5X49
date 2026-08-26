"use client";

import { createContext, type ReactNode, useContext, useMemo, useState } from "react";

import { API } from "@/lib/api";
import type { LibraryFilmDetail } from "@/types/movie";
import MovieBackdrop from "./MovieBackdrop";
import MoviePoster from "./MoviePoster";

interface FilmArtworkState {
  posterLocal?: string | null;
  backdropLocal?: string | null;
  posterProvider?: string | null;
  backdropProvider?: string | null;
  updatedAt?: string | null;
}

interface MovieArtworkContextValue {
  posterSrc: string | null;
  backdropSrc: string | null;
  updateFromFilm: (film: LibraryFilmDetail) => void;
}

const MovieArtworkContext = createContext<MovieArtworkContextValue | null>(null);

function filmToArtwork(film: LibraryFilmDetail): FilmArtworkState {
  const artwork = film.primary_item.artwork;
  return {
    posterLocal: artwork.poster_local,
    backdropLocal: artwork.backdrop_local,
    posterProvider: artwork.poster_provider,
    backdropProvider: artwork.backdrop_provider,
    updatedAt: film.primary_item.metadata.updated_at,
  };
}

function artworkSrc(localPath?: string | null, providerPath?: string | null, version?: string | null) {
  if (localPath) {
    const cacheVersion = version ? `?v=${encodeURIComponent(version)}` : "";
    return `${API.mediaUrl(localPath)}${cacheVersion}`;
  }
  return providerPath ? API.providerArtworkUrl(providerPath) : null;
}

export function MovieArtworkProvider({
  initialFilm,
  children,
}: {
  initialFilm: LibraryFilmDetail;
  children: ReactNode;
}) {
  const [artwork, setArtwork] = useState<FilmArtworkState>(() => filmToArtwork(initialFilm));

  const value = useMemo<MovieArtworkContextValue>(
    () => ({
      posterSrc: artworkSrc(artwork.posterLocal, artwork.posterProvider, artwork.updatedAt),
      backdropSrc: artworkSrc(artwork.backdropLocal, artwork.backdropProvider, artwork.updatedAt),
      updateFromFilm: (film) => setArtwork(filmToArtwork(film)),
    }),
    [artwork],
  );

  return <MovieArtworkContext.Provider value={value}>{children}</MovieArtworkContext.Provider>;
}

export function useMovieArtwork() {
  const context = useContext(MovieArtworkContext);
  if (!context) throw new Error("useMovieArtwork must be used within MovieArtworkProvider");
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
