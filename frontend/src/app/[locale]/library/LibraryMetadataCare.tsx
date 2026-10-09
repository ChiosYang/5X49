"use client";

import { CheckCircle2, ChevronRight, Film } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useMemo, useState } from "react";

import { Button } from "@/components/ui/Button";
import { reviewSession } from "@/lib/metadata-review";
import { InlineFeedback, StateMessage } from "@/components/ui/Feedback";
import { useLibraryPage } from "@/hooks/useLibrary";
import { Link } from "@/i18n/routing";
import type { LibraryFilmSummary } from "@/types/movie";
import { MetadataReviewInspector } from "./manage/MetadataReviewQueue";

function reviewFilms(films: LibraryFilmSummary[], locale: string) {
  return films
    .filter((film) => film.primary_item.metadata.scrape_status === "needs_review")
    .sort((left, right) => (
      left.title.localeCompare(right.title, locale)
      || (left.year ?? 0) - (right.year ?? 0)
      || left.id.localeCompare(right.id)
    ));
}

export default function LibraryMetadataCare({page}: {page:number}) {
  const t = useTranslations("LibraryCare");
  const locale = useLocale();
  const reviewT = useTranslations("LibraryManagement");
  const library = useLibraryPage(new URLSearchParams({metadata_status:"needs_review",limit:"40",offset:String((page-1)*40)}));
  const films = useMemo(() => reviewFilms(library.data?.items ?? [], locale), [library.data, locale]);
  const [activeFilmId, setActiveFilmId] = useState<string | null>(null);
  const [completed, setCompleted] = useState(false);
  const [skippedIds, setSkippedIds] = useState<string[]>([]);
  const [confirmedIds, setConfirmedIds] = useState<string[]>([]);
  const [reviewBusy, setReviewBusy] = useState(false);
  const { pending, available, skippedCount } = reviewSession(films, skippedIds, confirmedIds);
  const activeFilm = available.find((film) => film.id === activeFilmId) ?? available[0] ?? null;

  const handleConfirmed = async (filmId: string) => {
    const nextConfirmed = [...confirmedIds, filmId];
    const refreshed = await library.mutate().catch(() => undefined);
    setConfirmedIds(nextConfirmed);
    const remaining = reviewSession(refreshed ? reviewFilms(refreshed.items, locale) : films, skippedIds, nextConfirmed);
    setCompleted(refreshed ? refreshed.total === 0 : false);
    setActiveFilmId(remaining.available[0]?.id ?? null);
  };

  const handleSkip = () => {
    if (!activeFilm) return;
    const nextSkipped = [...skippedIds, activeFilm.id];
    setSkippedIds(nextSkipped);
    setActiveFilmId(reviewSession(films, nextSkipped, confirmedIds).available[0]?.id ?? null);
  };

  if (library.error && !library.data) {
    return <StateMessage state="error">{t("metadataLoadFailed")}</StateMessage>;
  }

  if (library.isLoading) {
    return <StateMessage state="loading">{t("metadataLoading")}</StateMessage>;
  }

  if (pending.length === 0) {
    return (
      <div className="border-y border-line py-16 text-center">
        <CheckCircle2 className="mx-auto h-8 w-8 text-success" />
        <h2 className="mt-5 type-section-title text-ink">{completed ? t("metadataComplete") : t("metadataEmpty")}</h2>
        <p className="mx-auto mt-3 max-w-xl text-sm leading-6 text-ink-subtle">{t("metadataEmptyDesc")}</p>
        <Link href="/library" className="focus-ring mt-7 inline-flex min-h-10 items-center border border-line-strong px-4 type-label text-ink-muted hover:border-ink-disabled hover:text-ink">
          {t("backToFilms")}
        </Link>
      </div>
    );
  }

  return (
    <section className="grid min-w-0 gap-8 lg:grid-cols-[minmax(15rem,0.72fr)_minmax(0,1.5fr)]">
      <aside className="min-w-0 border-y border-line lg:border-r lg:border-y-0 lg:pr-8">
        <div className="flex items-center justify-between gap-4 border-b border-line py-4 lg:pt-0">
          <div>
            <p className="type-label text-ink-muted">{t("metadataTitle")}</p>
            <p className="mt-1 text-xs text-ink-disabled">{t("itemsCount", { count: library.data?.total ?? pending.length })}</p>
          </div>
          <Film className="h-4 w-4 text-ink-disabled" />
        </div>
        <ul className="scrollbar-minimal max-h-[34rem] overflow-y-auto">
          {pending.map((film) => {
            const active = film.id === activeFilm?.id;
            return (
              <li key={film.id} className="border-b border-line">
                <button
                  type="button"
                  aria-current={active ? "true" : undefined}
                  disabled={reviewBusy}
                  onClick={() => {
                    setSkippedIds((current) => current.filter((id) => id !== film.id));
                    setActiveFilmId(film.id);
                  }}
                  className={`focus-ring flex min-h-16 w-full items-center justify-between gap-4 px-3 py-3 text-left transition-colors ${active ? "bg-inverse text-inverse-ink" : "text-ink-muted hover:bg-surface-raised hover:text-ink"}`}
                >
                  <span className="min-w-0">
                    <span className="block truncate text-sm font-medium">{film.title}</span>
                    <span className={`mt-1 block text-[11px] ${active ? "text-inverse-ink/60" : "text-ink-disabled"}`}>
                      {t("awaitingConfirmation")} · {film.year ?? t("unknownYear")}
                    </span>
                  </span>
                  <ChevronRight className="h-4 w-4 shrink-0" />
                </button>
              </li>
            );
          })}
        </ul>
        {library.data && library.data.total > library.data.limit && <nav aria-label={t("reviewPagination")} className="mt-4 flex justify-between gap-4">
          {library.data.offset > 0 ? <Link className="focus-ring min-h-11 py-3 text-sm underline" href={`/library?view=metadata&page=${Math.floor(library.data.offset/40)}`}>{t("previousPage")}</Link> : <span />}
          {library.data.offset+library.data.limit < library.data.total && <Link className="focus-ring min-h-11 py-3 text-sm underline" href={`/library?view=metadata&page=${Math.floor(library.data.offset/40)+2}`}>{t("nextPage")}</Link>}
        </nav>}
      </aside>

      <div className="min-w-0">
        <div className="mb-5">
          <h2 className="type-section-title text-ink">{t("metadataReviewHeading")}</h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-ink-subtle">{t("metadataReviewDesc")}</p>
        </div>
        {library.error ? <InlineFeedback tone="error">{reviewT("reviewRefreshFailed")}</InlineFeedback> : null}
        {skippedCount > 0 ? <p className="mb-3 text-xs text-ink-subtle" role="status">{reviewT("reviewSkippedRemaining", { count: skippedCount })}</p> : null}
        {activeFilm ? (
          <MetadataReviewInspector key={activeFilm.id} film={activeFilm} onConfirmed={handleConfirmed} onSkip={handleSkip} onBusyChange={setReviewBusy} />
        ) : (
          <div className="space-y-3">
            <InlineFeedback>{t("selectFilm")}</InlineFeedback>
            {skippedCount > 0 ? <Button onClick={() => setSkippedIds([])}>{reviewT("reviewRevisitSkipped")}</Button> : null}
          </div>
        )}
      </div>
    </section>
  );
}
