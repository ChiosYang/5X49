"use client";

import Image from "next/image";
import { useLocale, useTranslations } from "next-intl";
import { CalendarDays, Heart, Loader2, Star } from "lucide-react";
import { Link } from "@/i18n/routing";
import { API } from "@/lib/api";
import { useWatchHistory } from "@/hooks/useMovie";
import type { WatchHistoryEntry } from "@/types/movie";

function dateKey(value?: string | null) {
  return value?.slice(0, 10) || "unknown";
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
            {group.map(({ movie, user_state }) => {
              const backdropPath = movie.backdrop_thumb_local || movie.backdrop_local;
              const artworkVersion = movie.metadata_updated_at ? `?v=${encodeURIComponent(movie.metadata_updated_at)}` : "";
              const backdropSrc = backdropPath ? `${API.mediaUrl(backdropPath)}${artworkVersion}` : null;
              const title = movie.title_cn || movie.title;

              return (
                <Link
                  key={movie.id}
                  href={`/library/${movie.id}`}
                  className="group grid grid-cols-[112px_minmax(0,1fr)] gap-4 rounded-md border border-neutral-900 bg-neutral-950/40 p-3 transition-colors hover:border-neutral-700"
                >
                  <div className="relative aspect-video overflow-hidden rounded bg-neutral-900">
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
                  </div>
                  <div className="min-w-0 space-y-2">
                    <div>
                      <h2 className="truncate text-base font-black uppercase text-white">{title}</h2>
                      <p className="text-xs font-bold uppercase tracking-widest text-neutral-500">
                        {movie.director || movie.title} {movie.year}
                      </p>
                    </div>
                    <div className="flex items-center gap-2 text-neutral-300">
                      {user_state.rating ? (
                        <span className="inline-flex items-center gap-1 text-xs font-bold">
                          <Star className="h-3.5 w-3.5 fill-white text-white" />
                          {user_state.rating}/5
                        </span>
                      ) : null}
                      {user_state.favorite ? (
                        <Heart className="h-3.5 w-3.5 fill-white text-white" aria-label={t("favorite")} />
                      ) : null}
                    </div>
                    {user_state.notes ? (
                      <p className="line-clamp-2 text-sm leading-5 text-neutral-400">{user_state.notes}</p>
                    ) : null}
                  </div>
                </Link>
              );
            })}
          </div>
        </section>
      ))}
    </div>
  );
}
