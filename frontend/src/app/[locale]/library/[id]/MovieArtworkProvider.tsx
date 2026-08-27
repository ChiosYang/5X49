"use client";

import { createContext, type ReactNode, useContext, useMemo, useState } from "react";

import { API } from "@/lib/api";
import type { LibraryFilmDetail } from "@/types/movie";
import MovieBackdrop from "./MovieBackdrop";
import MoviePoster from "./MoviePoster";

interface FilmArtworkState {
  posterLocal?: string | null;
  posterThumbLocal?: string | null;
  backdropLocal?: string | null;
  backdropThumbLocal?: string | null;
  posterProvider?: string | null;
  backdropProvider?: string | null;
  updatedAt?: string | null;
}

interface MovieArtworkContextValue {
  posterSources: string[];
  backdropSources: string[];
  updateFromFilm: (film: LibraryFilmDetail) => void;
}

const MovieArtworkContext = createContext<MovieArtworkContextValue | null>(null);

function filmToArtwork(film: LibraryFilmDetail): FilmArtworkState {
  const artwork = film.primary_item.artwork;
  return {
    posterLocal: artwork.poster_local,
    posterThumbLocal: artwork.poster_thumb_local,
    backdropLocal: artwork.backdrop_local,
    backdropThumbLocal: artwork.backdrop_thumb_local,
    posterProvider: artwork.poster_provider,
    backdropProvider: artwork.backdrop_provider,
    updatedAt: film.primary_item.metadata.updated_at,
  };
}

function artworkSources(
  localPath?: string | null,
  thumbnailPath?: string | null,
  providerPath?: string | null,
  version?: string | null,
) {
  const cacheVersion = version ? `?v=${encodeURIComponent(version)}` : "";
  return Array.from(new Set([
    localPath ? `${API.mediaUrl(localPath)}${cacheVersion}` : null,
    thumbnailPath ? `${API.mediaUrl(thumbnailPath)}${cacheVersion}` : null,
    providerPath ? API.providerArtworkUrl(providerPath) : null,
  ].filter((source): source is string => Boolean(source))));
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
      posterSources: artworkSources(
        artwork.posterLocal,
        artwork.posterThumbLocal,
        artwork.posterProvider,
        artwork.updatedAt,
      ),
      backdropSources: artworkSources(
        artwork.backdropLocal,
        artwork.backdropThumbLocal,
        artwork.backdropProvider,
        artwork.updatedAt,
      ),
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
  const { backdropSources } = useMovieArtwork();
  return <MovieBackdrop key={backdropSources.join("\u0000")} sources={backdropSources} title={title} />;
}

export function MovieArtworkPoster({ title }: { title: string }) {
  const { posterSources } = useMovieArtwork();
  return posterSources.length
    ? <MoviePoster key={posterSources.join("\u0000")} sources={posterSources} title={title} />
    : null;
}
