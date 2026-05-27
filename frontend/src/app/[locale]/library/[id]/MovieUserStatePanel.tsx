"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Check, Heart, Loader2 } from "lucide-react";
import { mutate } from "swr";
import { API } from "@/lib/api";
import { useMovieUserState, useUpdateMovieUserState } from "@/hooks/useMovie";
import type { MovieUserState } from "@/types/movie";

interface MovieUserStatePanelProps {
  movieId: string;
  embedded?: boolean;
}

function todayDateValue() {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export default function MovieUserStatePanel({ movieId, embedded = false }: MovieUserStatePanelProps) {
  const t = useTranslations("FilmDetail");
  const { data: state, isLoading, error } = useMovieUserState(movieId);

  if (isLoading) {
    const content = (
        <div className="flex items-center gap-3 text-sm font-bold uppercase tracking-widest text-neutral-500">
          <Loader2 className="h-4 w-4 animate-spin" />
          {t("watchStateLoading")}
        </div>
    );
    return embedded ? content : (
      <section className="border-b border-neutral-800 px-8 py-10 md:px-16">{content}</section>
    );
  }

  if (error) {
    const content = <p className="text-sm font-bold uppercase tracking-widest text-red-400">{t("watchStateError")}</p>;
    return embedded ? content : (
      <section className="border-b border-neutral-800 px-8 py-10 md:px-16">{content}</section>
    );
  }

  if (!state) {
    return null;
  }

  return (
    <MovieUserStateForm key={movieId} movieId={movieId} state={state} embedded={embedded} />
  );
}

function MovieUserStateForm({
  movieId,
  state,
  embedded,
}: {
  movieId: string;
  state: MovieUserState;
  embedded: boolean;
}) {
  const t = useTranslations("FilmDetail");
  const { trigger, isMutating } = useUpdateMovieUserState(movieId);
  const [watched, setWatched] = useState(state.watched);
  const [favorite, setFavorite] = useState(state.favorite);
  const [message, setMessage] = useState<string | null>(null);

  const saveState = async (next: { watched?: boolean; favorite?: boolean }) => {
    const previousWatched = watched;
    const previousFavorite = favorite;
    const nextWatched = next.watched ?? watched;
    const nextFavorite = next.favorite ?? favorite;
    setMessage(null);
    setWatched(nextWatched);
    setFavorite(nextFavorite);
    try {
      const saved = await trigger({
        watched: nextWatched,
        watched_at: nextWatched ? state.watched_at || todayDateValue() : null,
        favorite: nextFavorite,
      });
      setMessage(t("watchStateSaved"));
      await Promise.all([
        mutate(API.libraryMovieUserState(movieId), saved, false),
        mutate(API.libraryUserStates()),
        mutate(API.watchHistory()),
      ]);
    } catch {
      setWatched(previousWatched);
      setFavorite(previousFavorite);
    }
  };

  return (
    <section className={embedded ? "space-y-6" : "border-b border-neutral-800 px-8 py-10 md:px-16"}>
      <div className="space-y-4">
        <span className="block text-xs font-bold uppercase tracking-widest text-neutral-500">
          {t("personalState")}
        </span>
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={() => saveState({ watched: !watched })}
            disabled={isMutating}
            className={`inline-flex h-10 items-center gap-2 rounded-md border px-4 text-sm font-black uppercase transition-colors ${
              watched
                ? "border-white bg-white text-black"
                : "border-neutral-700 bg-neutral-950 text-neutral-300 hover:border-white hover:text-white"
            } disabled:cursor-not-allowed disabled:opacity-60`}
          >
            {isMutating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
            {watched ? t("watched") : t("unwatched")}
          </button>
          <button
            type="button"
            onClick={() => saveState({ favorite: !favorite })}
            disabled={isMutating}
            className={`inline-flex h-10 items-center gap-2 rounded-md border px-4 text-sm font-black uppercase transition-colors ${
              favorite
                ? "border-white bg-white text-black"
                : "border-neutral-700 bg-neutral-950 text-neutral-300 hover:border-white hover:text-white"
            } disabled:cursor-not-allowed disabled:opacity-60`}
          >
            <Heart className={`h-4 w-4 ${favorite ? "fill-current" : ""}`} />
            {t("favorite")}
          </button>
        </div>
        <p className="min-h-5 text-xs font-bold uppercase tracking-widest text-neutral-500">{message}</p>
      </div>
    </section>
  );
}
