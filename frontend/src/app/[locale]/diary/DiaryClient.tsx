"use client";

import { CalendarDays, Edit3, Heart, Info, Plus, Star } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";

import ViewingEditorDialog from "@/components/viewings/ViewingEditorDialog";
import { Button } from "@/components/ui/Button";
import { StateMessage } from "@/components/ui/Feedback";
import { useProfileViewings } from "@/hooks/useFilm";
import { Link } from "@/i18n/routing";
import { API } from "@/lib/api";
import { groupViewingEntries } from "@/lib/viewing-diary";
import { isFilmResourceId } from "@/lib/resource-id";
import type { ViewingPage, ViewingTimelineEntry, ViewingView } from "@/types/movie";

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

export default function DiaryClient() {
  const t = useTranslations("Diary");
  const locale = useLocale();
  const searchParams = useSearchParams();
  const requestedFilmId = searchParams.get("film");
  const validFilmFilter = !requestedFilmId || isFilmResourceId(requestedFilmId);
  const filmId = requestedFilmId && validFilmFilter ? requestedFilmId : undefined;
  const { data, error, isLoading, mutate } = useProfileViewings(
    PAGE_SIZE,
    0,
    filmId,
    validFilmFilter,
  );
  const scopeKey = filmId || "all";
  const [continuation, setContinuation] = useState<{
    scopeKey: string;
    items: ViewingTimelineEntry[];
    nextOffset: number | null;
  } | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [loadMoreError, setLoadMoreError] = useState("");
  const [editorOpen, setEditorOpen] = useState(false);
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

  const loadMore = async () => {
    if (nextOffset === null) return;
    setLoadingMore(true);
    setLoadMoreError("");
    try {
      const response = await fetch(API.profileViewings({
        limit: PAGE_SIZE,
        offset: nextOffset,
        filmId,
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
  if (error) return <StateMessage state="error">{t("error")}</StateMessage>;

  return (
    <div className="space-y-10">
      {filmId ? (
        <div className="flex flex-col gap-4 border-y border-line py-5 sm:flex-row sm:items-center sm:justify-between">
          <div className="min-w-0">
            <p className="type-label text-ink-subtle">{t("filtered")}</p>
            <p className="mt-1 truncate text-lg font-bold text-ink">{filteredFilm?.title || t("filmFallback")}</p>
          </div>
          <Button
            variant="primary"
            icon={<Plus className="h-4 w-4" />}
            onClick={() => { setSelectedViewing(null); setEditorOpen(true); }}
          >
            {t("recordViewing")}
          </Button>
        </div>
      ) : null}

      {entries.length === 0 ? (
        <StateMessage>{filmId ? t("emptyFilm") : t("empty")}</StateMessage>
      ) : (
        groups.map((group) => (
          <section key={group.key} className="grid gap-5 border-t border-line pt-6 lg:grid-cols-[220px_minmax(0,1fr)]">
            <div className="flex items-start gap-3 type-label text-ink-subtle">
              <CalendarDays className="mt-0.5 h-4 w-4 shrink-0" />
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
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {group.entries.map((entry) => (
                <article key={entry.viewing.id} className="min-w-0 border border-line bg-surface p-4">
                  <div className="flex items-start justify-between gap-4">
                    <div className="min-w-0">
                      {entry.film.in_library ? (
                        <Link href={`/library/${entry.film.id}`} className="focus-ring block truncate font-bold text-ink hover:text-ink-muted">
                          {entry.film.title}
                        </Link>
                      ) : (
                        <p className="truncate font-bold text-ink">{entry.film.title}</p>
                      )}
                      <p className="type-meta mt-1 text-ink-subtle">
                        {entry.film.year || t("yearUnknown")} · {formatViewingDate(entry, locale, t("unknownDate"))}
                      </p>
                    </div>
                    <button
                      type="button"
                      className="focus-ring duration-fast flex h-9 w-9 shrink-0 items-center justify-center border border-line text-ink-muted transition-colors hover:border-line-strong hover:text-ink"
                      aria-label={entry.viewing.editable ? t("editViewing") : t("viewViewing")}
                      title={entry.viewing.editable ? t("editViewing") : t("viewViewing")}
                      onClick={() => { setSelectedViewing(entry.viewing); setEditorOpen(true); }}
                    >
                      {entry.viewing.editable ? <Edit3 className="h-4 w-4" /> : <Info className="h-4 w-4" />}
                    </button>
                  </div>
                  <div className="mt-5 flex flex-wrap items-center gap-3 border-t border-line pt-3 type-meta text-ink-subtle">
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
                      <span className="inline-flex items-center gap-1 text-ink">
                        <Star className="h-3.5 w-3.5 fill-current" /> {entry.profile_state.rating}/5
                      </span>
                    ) : null}
                  </div>
                </article>
              ))}
            </div>
          </section>
        ))
      )}

      {nextOffset !== null ? (
        <div className="flex flex-col items-center gap-3 border-t border-line pt-8">
          <Button busy={loadingMore} onClick={loadMore}>{t("loadMore")}</Button>
          <div aria-live="polite" className="min-h-5 text-sm text-danger">{loadMoreError}</div>
        </div>
      ) : null}

      {filmId ? (
        <ViewingEditorDialog
          key={`${selectedViewing?.id || "new"}:${editorOpen ? "open" : "closed"}`}
          open={editorOpen}
          onClose={() => setEditorOpen(false)}
          onSaved={async () => { setContinuation(null); await mutate(); }}
          filmId={filmId}
          filmTitle={filteredFilm?.title}
          viewing={selectedViewing}
        />
      ) : null}
    </div>
  );
}
