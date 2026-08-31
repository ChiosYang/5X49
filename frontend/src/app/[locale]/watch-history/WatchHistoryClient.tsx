"use client";

import Image from "next/image";
import { CalendarDays, Heart, Loader2, Star } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";

import { useWatchHistory } from "@/hooks/useFilm";
import { Link } from "@/i18n/routing";
import { API } from "@/lib/api";
import type { WatchHistoryEntry } from "@/types/movie";

function dateKey(value?: string | null) {
  return value?.slice(0, 10) || "unknown";
}

function formatDate(value: string, locale: string, fallback: string) {
  if (value === "unknown") return fallback;
  if (/^[0-9]{4}$/.test(value)) return value;
  const [year, month, day] = value.slice(0, 10).split("-").map(Number);
  const parsed = new Date(year, month - 1, day);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat(locale, { year: "numeric", month: "long", day: "numeric" }).format(parsed);
}

function groupEntries(entries: WatchHistoryEntry[]) {
  const groups = new Map<string, WatchHistoryEntry[]>();
  entries.forEach((entry) => {
    const key = dateKey(entry.viewing.watched_at);
    groups.set(key, [...(groups.get(key) || []), entry]);
  });
  return Array.from(groups.entries());
}

function WatchHistoryEntryCard({ entry }: { entry: WatchHistoryEntry }) {
  const t = useTranslations("WatchHistory");
  const { film, profile_state: profileState } = entry;
  const artwork = film.primary_item.artwork;
  const backdropPath = artwork.backdrop_thumb_local || artwork.backdrop_local;
  const artworkVersion = film.primary_item.metadata.updated_at
    ? `?v=${encodeURIComponent(film.primary_item.metadata.updated_at)}`
    : "";
  const backdropSrc = backdropPath
    ? `${API.mediaUrl(backdropPath)}${artworkVersion}`
    : artwork.backdrop_provider ? API.providerArtworkUrl(artwork.backdrop_provider) : null;

  return (
    <article className="border border-line bg-surface p-3 transition-colors hover:border-line-strong">
      <div className="grid grid-cols-[112px_minmax(0,1fr)] gap-4">
        <Link href={`/library/${film.id}`} className="group relative aspect-video overflow-hidden rounded-media bg-surface-raised">
          {backdropSrc ? (
            <Image src={backdropSrc} alt={film.title} fill sizes="112px" className="object-cover transition-transform duration-standard group-hover:scale-105" />
          ) : (
            <div className="flex h-full items-center justify-center text-2xl font-serif text-ink-disabled">?</div>
          )}
        </Link>
        <div className="min-w-0 space-y-2">
          <Link href={`/library/${film.id}`} className="focus-ring block">
            <h2 className="truncate text-base font-black text-ink uppercase">{film.title}</h2>
            <p className="type-meta truncate text-ink-subtle">{film.directors?.[0] || film.title} {film.year}</p>
          </Link>
          <div className="flex items-center gap-2 text-ink-muted">
            {profileState.rating ? (
              <span className="inline-flex items-center gap-1 text-xs font-bold"><Star className="h-3.5 w-3.5 fill-current" /> {profileState.rating}/5</span>
            ) : null}
            {profileState.favorite ? <Heart className="h-3.5 w-3.5 fill-current" aria-label={t("favorite")} /> : null}
          </div>
        </div>
      </div>
      <Link
        href={`/diary?film=${film.id}`}
        className="focus-ring duration-fast mt-4 inline-flex min-h-9 items-center border border-line px-3 type-badge text-ink-muted transition-colors hover:border-line-strong hover:text-ink"
      >
        {t("viewAll")}
      </Link>
    </article>
  );
}

export default function WatchHistoryClient() {
  const t = useTranslations("WatchHistory");
  const locale = useLocale();
  const { data, isLoading, error } = useWatchHistory();

  if (isLoading) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center text-ink-subtle">
        <Loader2 className="mr-3 h-5 w-5 animate-spin" />
        <span className="type-label">{t("loading")}</span>
      </div>
    );
  }
  if (error) return <p className="py-24 text-center type-label text-danger">{t("error")}</p>;
  const entries = data || [];
  if (entries.length === 0) return <p className="py-24 text-center font-serif text-xl italic text-ink-subtle">{t("empty")}</p>;

  return (
    <div className="space-y-14">
      {groupEntries(entries).map(([date, group]) => (
        <section key={date} className="grid grid-cols-1 gap-6 border-t border-line pt-6 lg:grid-cols-[220px_minmax(0,1fr)]">
          <div className="flex items-center gap-3 type-label text-ink-subtle lg:items-start">
            <CalendarDays className="h-4 w-4" /> {formatDate(date, locale, t("unknownDate"))}
          </div>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
            {group.map((entry) => <WatchHistoryEntryCard key={entry.film.id} entry={entry} />)}
          </div>
        </section>
      ))}
    </div>
  );
}
