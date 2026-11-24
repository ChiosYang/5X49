"use client";
import ViewingReview from "@/components/viewings/ViewingReview";

import { CalendarDays, Edit3, Heart, Info, Star } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";

import ViewingInlineEditor, { ViewingQuickAdd } from "@/components/viewings/ViewingInlineEditor";
import { Button } from "@/components/ui/Button";
import { StateMessage } from "@/components/ui/Feedback";
import { useProfileViewings } from "@/hooks/useFilm";
import { Link } from "@/i18n/routing";
import { rememberFilmReturn } from "@/lib/navigation-context";
import { API } from "@/lib/api";
import { diaryEditorFilmId, diaryViewFromQuery, groupViewingEntries } from "@/lib/diary";
import { isFilmResourceId } from "@/lib/resource-id";
import type { ViewingPage, ViewingTimelineEntry, ViewingView } from "@/types/movie";

import CinemaDnaClient from "./CinemaDnaClient";

const PAGE_SIZE = 30;

function formatViewingDate(entry: ViewingTimelineEntry, locale: string, unknown: string) {
  const { watched_at: value, watched_at_precision: precision } = entry.viewing;
  if (!value || precision === "unknown") return unknown;
  if (precision === "year") return value;
  const parts = value.slice(0, 10).split("-").map(Number);
  const date = new Date(parts[0], parts[1] - 1, parts[2]);
  return new Intl.DateTimeFormat(locale, {
    year: "numeric",
    month: "long",
    day: "numeric",
  }).format(date);
}

function formatDayStamp(entry: ViewingTimelineEntry) {
  const { watched_at: value, watched_at_precision: precision } = entry.viewing;
  if (!value || precision === "unknown") return "—";
  if (precision === "year") return value.slice(0, 4);
  return value.slice(8, 10) || "—";
}

function ViewingDiaryClient() {
  const t = useTranslations("Diary");
  const locale = useLocale();
  const searchParams = useSearchParams();
  const requestedFilmId = searchParams.get("film");
  const validFilmFilter = !requestedFilmId || isFilmResourceId(requestedFilmId);
  const filmId = requestedFilmId && validFilmFilter ? requestedFilmId : undefined;
  const view = diaryViewFromQuery(searchParams.get("view"), filmId) === "recent" ? "recent" : "timeline";
  const { data, error, isLoading } = useProfileViewings(
    PAGE_SIZE,
    0,
    filmId,
    validFilmFilter,
    view,
  );
  const scopeKey = `${filmId || "all"}:${view}`;
  const [continuation, setContinuation] = useState<{
    scopeKey: string;
    items: ViewingTimelineEntry[];
    nextOffset: number | null;
  } | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [loadMoreError, setLoadMoreError] = useState("");
  const [editorBusy, setEditorBusy] = useState(false);
  const [selectedViewing, setSelectedViewing] = useState<ViewingView | null>(null);

  const entries = useMemo(() => {
    const baseEntries = data?.items || [];
    const extraEntries = continuation?.scopeKey === scopeKey ? continuation.items : [];
    return [
      ...baseEntries,
      ...extraEntries.filter((item) => !baseEntries.some((entry) => entry.viewing.id === item.viewing.id)),
    ];
  }, [continuation, data, scopeKey]);
  const nextOffset = continuation?.scopeKey === scopeKey
    ? continuation.nextOffset
    : data?.next_offset ?? null;
  const groups = useMemo(() => groupViewingEntries(entries), [entries]);
  const filteredFilm = entries[0]?.film;
  const editorFilmId = diaryEditorFilmId(filmId, selectedViewing);

  const loadMore = async () => {
    if (nextOffset === null) return;
    setLoadingMore(true);
    setLoadMoreError("");
    try {
      const response = await fetch(API.profileViewings({
        limit: PAGE_SIZE,
        offset: nextOffset,
        filmId,
        view,
      }));
      if (!response.ok) throw new Error(t("loadMoreFailed"));
      const page = await response.json() as ViewingPage;
      setContinuation((current) => {
        const currentItems = current?.scopeKey === scopeKey ? current.items : [];
        return {
          scopeKey,
          items: [
            ...currentItems,
            ...page.items.filter((item) => !currentItems.some((entry) => entry.viewing.id === item.viewing.id)),
          ],
          nextOffset: page.next_offset ?? null,
        };
      });
    } catch (loadError) {
      setLoadMoreError(loadError instanceof Error ? loadError.message : t("loadMoreFailed"));
    } finally {
      setLoadingMore(false);
    }
  };

  if (!validFilmFilter) {
    return <StateMessage state="error">{t("invalidFilm")}</StateMessage>;
  }
  if (isLoading) return <StateMessage state="loading">{t("loading")}</StateMessage>;
  if (error && !data) return <StateMessage state="error">{t("error")}</StateMessage>;

  return (
    <div className="space-y-10">
      {error ? <StateMessage state="error">{t("error")}</StateMessage> : null}

      {filmId ? (
        <div className="flex flex-col gap-4 border-y border-line py-5 sm:flex-row sm:items-center sm:justify-between">
          <div className="min-w-0">
            <p className="type-label text-ink-subtle">{t("filtered")}</p>
            <p className="mt-1 truncate text-lg font-bold text-ink">{filteredFilm?.title || t("filmFallback")}</p>
          </div>
          <ViewingQuickAdd
            filmId={filmId}
            onSaved={() => setContinuation(null)}
          />
        </div>
      ) : null}

      {selectedViewing && editorFilmId ? <div id="viewing-editor" className="max-w-2xl rounded-media border border-line bg-surface/60 p-5">
        <p className="font-semibold text-ink">{entries.find(entry => entry.film.id === editorFilmId)?.film.title || t("filmFallback")}</p>
        <p className="mt-1 font-mono text-xs tabular-nums text-ink-subtle">{selectedViewing.watched_at || t("unknownDate")}</p>
        <ViewingInlineEditor key={selectedViewing.id} filmId={editorFilmId} viewing={selectedViewing}
          onBusyChange={setEditorBusy} onCancel={() => setSelectedViewing(null)} onSaved={() => setContinuation(null)} />
      </div> : null}
      {entries.length === 0 ? (
        <StateMessage>{filmId ? t("emptyFilm") : t("empty")}</StateMessage>
      ) : (
        groups.map((group) => (
          <section key={group.key} className="grid gap-5 border-t border-line pt-7 lg:grid-cols-[200px_minmax(0,1fr)] lg:gap-10">
            <div className="flex items-start gap-2.5 pt-0.5 text-sm font-medium tracking-wide text-ink-muted">
              <CalendarDays className="mt-0.5 h-4 w-4 shrink-0 text-ink-subtle" />
              <span>
                {group.kind === "month"
                  ? new Intl.DateTimeFormat(locale, { year: "numeric", month: "long" }).format(
                      new Date(Number(group.year), Number(group.month) - 1, 1),
                    )
                  : group.kind === "year"
                    ? t("yearUnknownDate", { year: group.year || "" })
                    : t("unknownDate")}
              </span>
            </div>
            <div className="divide-y divide-line border-t border-line lg:border-t-0">
              {group.entries.map((entry) => (
                <article key={entry.viewing.id} className="min-w-0 py-4 first:pt-4 lg:first:pt-0">
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex min-w-0 flex-1 items-start gap-4 sm:gap-6">
                      <span aria-hidden="true" className="w-10 shrink-0 pt-0.5 font-mono text-xl font-light leading-none tabular-nums text-ink-subtle">
                        {formatDayStamp(entry)}
                      </span>
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-baseline gap-x-2.5 gap-y-1">
                          {entry.film.in_library ? (
                            <Link href={`/library/${entry.film.id}`} id={`viewing-link-${entry.viewing.id}`} onClick={() => rememberFilmReturn(entry.film.id, `viewing-link-${entry.viewing.id}`)} className="focus-ring max-w-full truncate text-base font-semibold tracking-tight text-ink transition-colors hover:text-ink-muted sm:text-lg">
                              {entry.film.title}
                            </Link>
                          ) : (
                            <p className="max-w-full truncate text-base font-semibold tracking-tight text-ink sm:text-lg">{entry.film.title}</p>
                          )}
                          <span className="shrink-0 font-serif text-sm italic text-ink-subtle">
                            {entry.film.year || t("yearUnknown")}
                          </span>
                        </div>
                        <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 type-meta text-ink-subtle">
                          <span className="tabular-nums">{formatViewingDate(entry, locale, t("unknownDate"))}</span>
                          <span>·</span>
                          <span>{t("sourceLabel", {
                            source: entry.viewing.source === "manual"
                              ? t("sources.manual")
                              : entry.viewing.source === "diary"
                                ? t("sources.diary")
                                : t("sources.external", { source: entry.viewing.source }),
                          })}</span>
                          {!entry.viewing.editable ? <span className="text-warning">{t("readOnly")}</span> : null}
                          {entry.profile_state.favorite ? <Heart className="h-3.5 w-3.5 fill-current text-ink" aria-label={t("favorite")} /> : null}
                          {entry.profile_state.rating ? (
                            <span className="inline-flex items-center gap-1 tabular-nums text-ink">
                              <Star className="h-3.5 w-3.5 fill-current" /> {t("filmRating")}: {entry.profile_state.rating}/5
                            </span>
                          ) : null}
                        </div>
                        <ViewingReview viewing={entry.viewing} />
                        {view === "recent" ? (
                          <Link
                            href={`/diary?film=${entry.film.id}`}
                            className="focus-ring duration-fast mt-3 inline-flex min-h-9 items-center rounded-pill border border-line px-3.5 type-badge text-ink-muted transition-colors hover:border-line-strong hover:text-ink"
                          >
                            {t("viewAll")}
                          </Link>
                        ) : null}
                      </div>
                    </div>
                    <button
                      type="button"
                      disabled={editorBusy}
                      className="focus-ring duration-fast flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-line text-ink-muted transition-colors hover:border-line-strong hover:text-ink"
                      aria-label={entry.viewing.editable ? t("editViewing") : t("viewViewing")}
                      title={entry.viewing.editable ? t("editViewing") : t("viewViewing")}
                      aria-expanded={selectedViewing?.id === entry.viewing.id}
                      onClick={() => {
                        setSelectedViewing((current) => current?.id === entry.viewing.id ? null : entry.viewing);
                        requestAnimationFrame(() => document.getElementById("viewing-editor")?.scrollIntoView({ block: "center" }));
                      }}
                    >
                      {entry.viewing.editable ? <Edit3 className="h-3.5 w-3.5" /> : <Info className="h-3.5 w-3.5" />}
                    </button>
                  </div>
                </article>
              ))}
            </div>
          </section>
        ))
      )}

      {nextOffset !== null ? (
        <div className="flex flex-col items-center gap-3 border-t border-line pt-8">
          <Button size="sm" className="rounded-pill px-6" busy={loadingMore} onClick={loadMore}>{t("loadMore")}</Button>
          <div aria-live="polite" className="min-h-5 text-sm text-danger">{loadMoreError}</div>
        </div>
      ) : null}
    </div>
  );
}

export default function DiaryClient() {
  const t = useTranslations("Diary");
  const dna = useTranslations("CinemaDna");
  const params = useSearchParams();
  const film = params.get("film") || undefined;
  const view = diaryViewFromQuery(params.get("view"), film);
  return <div className="space-y-10">
    <header>
      <h1 className="type-display-editorial text-ink">{view === "dna" ? dna("title") : t("title")}</h1>
    </header>
    {!film ? <nav aria-label={t("viewMode")} className="scrollbar-minimal flex items-center gap-7 overflow-x-auto border-b border-line">
      {(["timeline", "recent", "dna"] as const).map((mode) => <Link
        key={mode}
        href={mode === "timeline" ? "/diary" : `/diary?view=${mode}`}
        aria-current={view === mode ? "page" : undefined}
        scroll={false}
        className={`focus-ring duration-fast -mb-px inline-flex min-h-11 shrink-0 items-center border-b-2 pb-3 type-label transition-colors ${view === mode ? "border-ink text-ink" : "border-transparent text-ink-subtle hover:text-ink"}`}
      >{mode === "dna" ? dna("title") : t(mode === "recent" ? "recentView" : "timelineView")}</Link>)}
    </nav> : null}
    {view === "dna" ? <CinemaDnaClient /> : <ViewingDiaryClient />}
  </div>;
}
