"use client";

import { useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { Check, Heart, Loader2, NotebookText, Save, Star } from "lucide-react";
import { mutate } from "swr";
import { API } from "@/lib/api";
import { useMovieUserState, useUpdateMovieUserState } from "@/hooks/useMovie";
import type { MovieUserState } from "@/types/movie";

interface MovieUserStatePanelProps {
  movieId: string;
}

function dateValue(value?: string | null) {
  return value?.slice(0, 10) || "";
}

function todayDateValue() {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export default function MovieUserStatePanel({ movieId }: MovieUserStatePanelProps) {
  const t = useTranslations("FilmDetail");
  const { data: state, isLoading, error } = useMovieUserState(movieId);

  if (isLoading) {
    return (
      <section className="border-b border-neutral-800 px-8 py-10 md:px-16">
        <div className="flex items-center gap-3 text-sm font-bold uppercase tracking-widest text-neutral-500">
          <Loader2 className="h-4 w-4 animate-spin" />
          {t("watchStateLoading")}
        </div>
      </section>
    );
  }

  if (error) {
    return (
      <section className="border-b border-neutral-800 px-8 py-10 md:px-16">
        <p className="text-sm font-bold uppercase tracking-widest text-red-400">{t("watchStateError")}</p>
      </section>
    );
  }

  if (!state) {
    return null;
  }

  return (
    <MovieUserStateForm key={movieId} movieId={movieId} state={state} />
  );
}

function MovieUserStateForm({ movieId, state }: { movieId: string; state: MovieUserState }) {
  const t = useTranslations("FilmDetail");
  const { trigger, isMutating } = useUpdateMovieUserState(movieId);
  const [watched, setWatched] = useState(state.watched);
  const [watchedAt, setWatchedAt] = useState(dateValue(state.watched_at));
  const [rating, setRating] = useState<number | null>(state.rating ?? null);
  const [favorite, setFavorite] = useState(state.favorite);
  const [notes, setNotes] = useState(state.notes || "");
  const [message, setMessage] = useState<string | null>(null);

  const dirty = useMemo(() => (
    watched !== state.watched ||
    watchedAt !== dateValue(state.watched_at) ||
    rating !== (state.rating ?? null) ||
    favorite !== state.favorite ||
    notes !== (state.notes || "")
  ), [favorite, notes, rating, state, watched, watchedAt]);

  const save = async () => {
    setMessage(null);
    const saved = await trigger({
      watched,
      watched_at: watchedAt || null,
      rating,
      favorite,
      notes: notes.trim() || null,
    });
    setMessage(t("watchStateSaved"));
    await Promise.all([
      mutate(API.libraryMovieUserState(movieId), saved, false),
      mutate(API.libraryUserStates()),
      mutate(API.watchHistory()),
    ]);
  };

  const toggleWatched = () => {
    const next = !watched;
    setWatched(next);
    if (next && !watchedAt) {
      setWatchedAt(todayDateValue());
    }
    if (!next) {
      setWatchedAt("");
    }
  };

  return (
    <section className="border-b border-neutral-800 px-8 py-10 md:px-16">
      <div className="grid grid-cols-1 gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(280px,420px)]">
        <div className="space-y-6">
          <div>
            <span className="block text-xs font-bold uppercase tracking-widest text-neutral-500">
              {t("personalState")}
            </span>
            <div className="mt-4 flex flex-wrap items-center gap-3">
              <button
                type="button"
                onClick={toggleWatched}
                className={`inline-flex h-10 items-center gap-2 rounded-md border px-4 text-sm font-black uppercase transition-colors ${
                  watched
                    ? "border-white bg-white text-black"
                    : "border-neutral-700 bg-neutral-950 text-neutral-300 hover:border-white hover:text-white"
                }`}
              >
                <Check className="h-4 w-4" />
                {watched ? t("watched") : t("unwatched")}
              </button>
              <button
                type="button"
                onClick={() => setFavorite((value) => !value)}
                className={`inline-flex h-10 items-center gap-2 rounded-md border px-4 text-sm font-black uppercase transition-colors ${
                  favorite
                    ? "border-white bg-white text-black"
                    : "border-neutral-700 bg-neutral-950 text-neutral-300 hover:border-white hover:text-white"
                }`}
              >
                <Heart className={`h-4 w-4 ${favorite ? "fill-current" : ""}`} />
                {t("favorite")}
              </button>
            </div>
          </div>

          <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
            <label className="space-y-2">
              <span className="block text-xs font-bold uppercase tracking-widest text-neutral-500">
                {t("watchedAt")}
              </span>
              <input
                type="date"
                value={watchedAt}
                onChange={(event) => {
                  setWatchedAt(event.target.value);
                  if (event.target.value) setWatched(true);
                }}
                className="h-11 w-full rounded-md border border-neutral-800 bg-neutral-950 px-3 text-sm text-white outline-none transition-colors focus:border-white"
              />
            </label>
            <div className="space-y-2">
              <span className="block text-xs font-bold uppercase tracking-widest text-neutral-500">
                {t("rating")}
              </span>
              <div className="flex h-11 items-center gap-1">
                {[1, 2, 3, 4, 5].map((value) => (
                  <button
                    key={value}
                    type="button"
                    onClick={() => setRating((current) => current === value ? null : value)}
                    aria-label={t("setRating", { rating: value })}
                    title={t("setRating", { rating: value })}
                    className="flex h-9 w-9 items-center justify-center rounded-md text-neutral-500 transition-colors hover:bg-neutral-900 hover:text-white"
                  >
                    <Star className={`h-5 w-5 ${rating && value <= rating ? "fill-white text-white" : ""}`} />
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>

        <div className="space-y-3">
          <label className="space-y-2">
            <span className="flex items-center gap-2 text-xs font-bold uppercase tracking-widest text-neutral-500">
              <NotebookText className="h-4 w-4" />
              {t("notes")}
            </span>
            <textarea
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
              rows={5}
              className="w-full resize-none rounded-md border border-neutral-800 bg-neutral-950 p-3 text-sm leading-6 text-white outline-none transition-colors placeholder:text-neutral-700 focus:border-white"
              placeholder={t("notesPlaceholder")}
            />
          </label>
          <div className="flex items-center justify-between gap-4">
            <p className="min-h-5 text-xs font-bold uppercase tracking-widest text-neutral-500">
              {message}
            </p>
            <button
              type="button"
              onClick={save}
              disabled={!dirty || isMutating}
              className="inline-flex h-10 items-center gap-2 rounded-md bg-white px-4 text-sm font-black uppercase text-black transition-colors hover:bg-neutral-200 disabled:cursor-not-allowed disabled:bg-neutral-800 disabled:text-neutral-500"
            >
              {isMutating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
              {t("saveState")}
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}
