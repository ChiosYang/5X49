"use client";

import type { RefObject } from "react";
import { motion } from "framer-motion";
import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight, Compass } from "lucide-react";
import { useTranslations } from "next-intl";
import { formatExploreFacetLabel, hasExploreFilters, type ExploreQueryState } from "@/lib/explore";
import type { ExploreFilmPage, ExploreView } from "@/types/movie";
import { Button, IconButton } from "@/components/ui/Button";
import LibraryMovieCard from "@/app/[locale]/library/LibraryMovieCard";
import { Spinner } from "@/components/ui/Feedback";

type ResultStageProps = {
  query: ExploreQueryState;
  results: ExploreFilmPage | null;
  pending: boolean;
  locale: string;
  localizeCountries: boolean;
  sectionRef: RefObject<HTMLElement | null>;
  headingRef: RefObject<HTMLHeadingElement | null>;
  onView: (view: ExploreView) => void;
  onSort: (sort: ExploreQueryState["sort"]) => void;
  onDirection: () => void;
  onPage: (offset: number) => void;
  onClear: () => void;
  showMatchedFacts?: boolean;
};

export function ResultStage({
  query,
  results,
  pending,
  locale,
  localizeCountries,
  sectionRef,
  headingRef,
  onView,
  onSort,
  onDirection,
  onPage,
  onClear,
  showMatchedFacts = true,
}: ResultStageProps) {
  const t = useTranslations("Explore");
  const total = results?.total ?? 0;
  const nextOffset = results ? results.next_offset : null;
  const previousOffset = results && query.offset > 0
    ? Math.max(0, query.offset - results.limit)
    : null;
  const pageStart = total === 0 ? 0 : Math.min(query.offset + 1, total);
  const pageEnd = results ? Math.min(query.offset + results.items.length, total) : 0;

  return (
    <section ref={sectionRef} aria-labelledby="explore-results-title" className="min-w-0 scroll-mt-28">
      <div className="flex flex-col gap-3 border-b border-line pb-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="type-label text-ink-muted">{t("strictResults")}</p>
          <h2
            id="explore-results-title"
            ref={headingRef}
            tabIndex={-1}
            className="mt-1 font-serif text-3xl text-ink outline-none"
          >
            {t("resultCount", { count: total })}
          </h2>
        </div>
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <div role="group" className="inline-flex flex-wrap gap-1 border border-line-strong bg-canvas p-1" aria-label={t("viewLabel")}>
            {(["all", "watched", "unwatched"] as const).map((view) => (
              <Button
                key={view}
                type="button"
                aria-pressed={query.view === view}
                onClick={() => onView(view)}
                size="sm"
                variant={query.view === view ? "primary" : "ghost"}
              >
                {t(`views.${view}`)}
              </Button>
            ))}
          </div>
          <div role="group" className="inline-flex flex-wrap gap-1 border border-line-strong bg-canvas p-1" aria-label={t("sortLabel")}>
            {(["title", "year"] as const).map((sort) => (
              <Button
                key={sort}
                type="button"
                aria-pressed={query.sort === sort}
                onClick={() => onSort(sort)}
                size="sm"
                variant={query.sort === sort ? "primary" : "ghost"}
              >
                {t(`sorts.${sort}`)}
              </Button>
            ))}
            <IconButton
              variant="ghost"
              onClick={onDirection}
              aria-label={query.dir === "asc" ? t("ascending") : t("descending")}
              icon={query.dir === "asc" ? <ArrowUp className="h-3.5 w-3.5" /> : <ArrowDown className="h-3.5 w-3.5" />}
            />
          </div>
        </div>
      </div>

      <p className="sr-only" aria-live="polite">
        {pending ? t("loadingResults") : t("resultsUpdated", { count: total })}
      </p>

      <div className="relative min-h-[32rem] pt-6">
        {pending ? (
          <div className="pointer-events-none absolute inset-x-0 top-0 z-10 h-0.5 overflow-hidden bg-surface-hover">
            <span className="block h-full w-1/3 animate-pulse bg-ink/70" />
          </div>
        ) : null}
        {!results || (results.total > 0 && results.items.length === 0) ? (
          <div className="flex min-h-80 items-center justify-center">
            <Spinner className="text-ink" />
          </div>
        ) : results.items.length > 0 ? (
          <motion.div
            initial={{ opacity: 0.82 }}
            animate={{ opacity: pending ? 0.58 : 1 }}
            transition={{ duration: 0.18 }}
            className="grid grid-cols-2 gap-x-3 gap-y-6 sm:grid-cols-3 lg:grid-cols-4"
            aria-busy={pending}
          >
            {results.items.map((item) => (
              <div key={item.film.id} className="min-w-0">
                <LibraryMovieCard movie={item.film} />
                {showMatchedFacts && item.matched_facts.length > 0 ? (
                  <p className="mt-2 line-clamp-2 text-[10px] leading-4 text-ink-subtle">
                    {item.matched_facts
                      .map((fact) =>
                        formatExploreFacetLabel(
                          fact.dimension,
                          fact.key,
                          fact.label,
                          locale,
                          localizeCountries,
                        ),
                      )
                      .join(" · ")}
                  </p>
                ) : null}
              </div>
            ))}
          </motion.div>
        ) : (
          <div className="flex min-h-80 flex-col items-center justify-center rounded-structural border border-dashed border-line-strong px-6 text-center">
            <Compass className="h-8 w-8 text-ink/25" />
            <h3 className="mt-4 font-serif text-2xl text-ink">{t(hasExploreFilters(query) ? "zeroTitle" : "emptyViewTitle")}</h3>
            <p className="mt-2 max-w-lg text-sm leading-6 text-ink-muted">{t(hasExploreFilters(query) ? "zeroDetail" : "emptyViewDetail")}</p>
            {hasExploreFilters(query) ? <Button className="mt-5" variant="secondary" onClick={onClear}>{t("clearAll")}</Button> : null}
          </div>
        )}
      </div>

      {results && results.items.length > 0 && (previousOffset !== null || nextOffset !== null) ? (
        <nav className="mt-8 flex items-center justify-between border-t border-line pt-5" aria-label={t("paginationLabel")}>
          <Button
            variant="ghost"
            disabled={previousOffset === null || pending}
            onClick={() => previousOffset !== null && onPage(previousOffset)}
          >
            <ChevronLeft className="h-4 w-4" />
            {t("previous")}
          </Button>
          <span className="text-xs text-ink-subtle">
            {pageStart}–{pageEnd} / {total}
          </span>
          <Button
            variant="ghost"
            disabled={nextOffset === null || pending}
            onClick={() => nextOffset !== null && onPage(nextOffset)}
          >
            {t("next")}
            <ChevronRight className="h-4 w-4" />
          </Button>
        </nav>
      ) : null}
    </section>
  );
}
