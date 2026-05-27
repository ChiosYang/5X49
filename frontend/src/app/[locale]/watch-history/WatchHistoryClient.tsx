"use client";

import Image from "next/image";
import { useMemo, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { CalendarDays, Heart, Loader2, NotebookText, Save, Star } from "lucide-react";
import { mutate } from "swr";
import { Link } from "@/i18n/routing";
import { API } from "@/lib/api";
import { useUpdateMovieUserState, useWatchHistory } from "@/hooks/useMovie";
import type { WatchHistoryEntry } from "@/types/movie";

function dateKey(value?: string | null) {
  return value?.slice(0, 10) || "unknown";
}

function inputDateValue(value?: string | null) {
  return value?.slice(0, 10) || "";
}

function formatDate(value: string, locale: string, fallback: string) {
  if (value === "unknown") return fallback;
  const dateOnly = value.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  const date = dateOnly
    ? new Date(Number(dateOnly[1]), Number(dateOnly[2]) - 1, Number(dateOnly[3]))
    : new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(locale, {
    year: "numeric",
    month: "long",
    day: "numeric",
  }).format(date);
}

function groupEntries(entries: WatchHistoryEntry[]) {
  const groups = new Map<string, WatchHistoryEntry[]>();
  entries.forEach((entry) => {
    const key = dateKey(entry.user_state.watched_at);
    groups.set(key, [...(groups.get(key) || []), entry]);
  });
  return Array.from(groups.entries());
}

function WatchHistoryEntryCard({ entry }: { entry: WatchHistoryEntry }) {
  const t = useTranslations("WatchHistory");
  const detailT = useTranslations("FilmDetail");
  const { movie, user_state } = entry;
  const { trigger, isMutating } = useUpdateMovieUserState(movie.id);
  const [watchedAt, setWatchedAt] = useState(inputDateValue(user_state.watched_at));
  const [rating, setRating] = useState<number | null>(user_state.rating ?? null);
  const [notes, setNotes] = useState(user_state.notes || "");
  const [message, setMessage] = useState<string | null>(null);
  const backdropPath = movie.backdrop_thumb_local || movie.backdrop_local;
  const artworkVersion = movie.metadata_updated_at ? `?v=${encodeURIComponent(movie.metadata_updated_at)}` : "";
  const backdropSrc = backdropPath ? `${API.mediaUrl(backdropPath)}${artworkVersion}` : null;
  const title = movie.title_cn || movie.title;
  const dirty = useMemo(() => (
    watchedAt !== inputDateValue(user_state.watched_at) ||
    rating !== (user_state.rating ?? null) ||
    notes !== (user_state.notes || "")
  ), [notes, rating, user_state, watchedAt]);

  const save = async () => {
    setMessage(null);
    const saved = await trigger({
      watched: true,
      watched_at: watchedAt || null,
      rating,
      favorite: user_state.favorite,
      notes: notes.trim() || null,
    });
    setMessage(detailT("watchStateSaved"));
    await Promise.all([
      mutate(API.libraryMovieUserState(movie.id), saved, false),
      mutate(API.libraryUserStates()),
      mutate(API.watchHistory()),
    ]);
  };

  return (
    <article className="rounded-md border border-neutral-900 bg-neutral-950/40 p-3 transition-colors hover:border-neutral-700">
      <div className="grid grid-cols-[112px_minmax(0,1fr)] gap-4">
        <Link href={`/library/${movie.id}`} className="group relative aspect-video overflow-hidden rounded bg-neutral-900">
          {backdropSrc ? (
            <Image
              src={backdropSrc}
              alt={movie.title}
              fill
              sizes="112px"
              className="object-cover transition-transform duration-200 group-hover:scale-105"
            />
          ) : (
            <div className="flex h-full items-center justify-center text-2xl font-serif text-neutral-800">?</div>
          )}
        </Link>
        <div className="min-w-0 space-y-2">
          <Link href={`/library/${movie.id}`} className="block">
            <h2 className="truncate text-base font-black uppercase text-white">{title}</h2>
            <p className="text-xs font-bold uppercase tracking-widest text-neutral-500">
              {movie.director || movie.title} {movie.year}
            </p>
          </Link>
          <div className="flex items-center gap-2 text-neutral-300">
            {rating ? (
              <span className="inline-flex items-center gap-1 text-xs font-bold">
                <Star className="h-3.5 w-3.5 fill-white text-white" />
                {rating}/5
              </span>
            ) : null}
            {user_state.favorite ? (
              <Heart className="h-3.5 w-3.5 fill-white text-white" aria-label={t("favorite")} />
            ) : null}
          </div>
        </div>
      </div>

      <div className="mt-4 space-y-4">
        <label className="space-y-2">
          <span className="block text-xs font-bold uppercase tracking-widest text-neutral-500">
            {detailT("watchedAt")}
          </span>
          <input
            type="date"
            value={watchedAt}
            onChange={(event) => setWatchedAt(event.target.value)}
            className="h-10 w-full rounded-md border border-neutral-800 bg-black px-3 text-sm text-white outline-none transition-colors focus:border-white"
          />
        </label>
        <div className="space-y-2">
          <span className="block text-xs font-bold uppercase tracking-widest text-neutral-500">
            {detailT("rating")}
          </span>
          <div className="flex h-10 items-center gap-1">
            {[1, 2, 3, 4, 5].map((value) => (
              <button
                key={value}
                type="button"
                onClick={() => setRating((current) => current === value ? null : value)}
                aria-label={detailT("setRating", { rating: value })}
                title={detailT("setRating", { rating: value })}
                className="flex h-9 w-9 items-center justify-center rounded-md text-neutral-500 transition-colors hover:bg-neutral-900 hover:text-white"
              >
                <Star className={`h-5 w-5 ${rating && value <= rating ? "fill-white text-white" : ""}`} />
              </button>
            ))}
          </div>
        </div>
        <label className="space-y-2">
          <span className="flex items-center gap-2 text-xs font-bold uppercase tracking-widest text-neutral-500">
            <NotebookText className="h-4 w-4" />
            {detailT("notes")}
          </span>
          <textarea
            value={notes}
            onChange={(event) => setNotes(event.target.value)}
            rows={4}
            className="w-full resize-none rounded-md border border-neutral-800 bg-black p-3 text-sm leading-6 text-white outline-none transition-colors placeholder:text-neutral-700 focus:border-white"
            placeholder={detailT("notesPlaceholder")}
          />
        </label>
        <div className="flex items-center justify-between gap-4">
          <p className="min-h-5 text-xs font-bold uppercase tracking-widest text-neutral-500">{message}</p>
          <button
            type="button"
            onClick={save}
            disabled={!dirty || isMutating}
            className="inline-flex h-10 items-center gap-2 rounded-md bg-white px-4 text-sm font-black uppercase text-black transition-colors hover:bg-neutral-200 disabled:cursor-not-allowed disabled:bg-neutral-800 disabled:text-neutral-500"
          >
            {isMutating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
            {detailT("saveState")}
          </button>
        </div>
      </div>
    </article>
  );
}

export default function WatchHistoryClient() {
  const t = useTranslations("WatchHistory");
  const locale = useLocale();
  const { data, isLoading, error } = useWatchHistory();

  if (isLoading) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center text-neutral-500">
        <Loader2 className="mr-3 h-5 w-5 animate-spin" />
        <span className="text-sm font-bold uppercase tracking-widest">{t("loading")}</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="py-24 text-center">
        <p className="text-sm font-bold uppercase tracking-widest text-red-400">{t("error")}</p>
      </div>
    );
  }

  const entries = data || [];
  if (entries.length === 0) {
    return (
      <div className="py-24 text-center">
        <p className="font-serif text-xl italic text-neutral-500">{t("empty")}</p>
      </div>
    );
  }

  return (
    <div className="space-y-14">
      {groupEntries(entries).map(([date, group]) => (
        <section key={date} className="grid grid-cols-1 gap-6 border-t border-neutral-900 pt-6 lg:grid-cols-[220px_minmax(0,1fr)]">
          <div className="flex items-center gap-3 text-sm font-black uppercase tracking-widest text-neutral-500 lg:items-start">
            <CalendarDays className="h-4 w-4" />
            {formatDate(date, locale, t("unknownDate"))}
          </div>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
            {group.map((entry) => (
              <WatchHistoryEntryCard key={entry.movie.id} entry={entry} />
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
