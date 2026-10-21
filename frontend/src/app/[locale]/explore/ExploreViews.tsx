"use client";

import { Fragment, type RefObject } from "react";
import Image from "next/image";
import { motion } from "framer-motion";
import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight, Compass, Film, X } from "lucide-react";
import { useTranslations } from "next-intl";
import { API } from "@/lib/api";
import { EXPLORE_DIMENSIONS, formatExploreFacetLabel, hasExploreFilters, type ExploreQueryState } from "@/lib/explore";
import type { ExploreCollection, ExploreCollections, ExploreDimension, ExploreFilmPage, ExploreView } from "@/types/movie";
import { Button, IconButton } from "@/components/ui/Button";
import LibraryMovieCard from "@/app/[locale]/library/LibraryMovieCard";
import { Spinner } from "@/components/ui/Feedback";

export function CollectionEntries({ collections, emptyView, locale, localizeCountries, onSelect }: {
  collections: ExploreCollections;
  emptyView: boolean;
  locale: string;
  localizeCountries: boolean;
  onSelect: (item: ExploreCollection) => void;
}) {
  const t = useTranslations("Explore");
  return (
    <section aria-labelledby="explore-collections-title">
      <h2 id="explore-collections-title" className="font-serif text-2xl text-ink">{t("collectionsTitle")}</h2>
      {collections.items.length === 0 ? (
        <p className="mt-3 text-sm leading-6 text-ink-muted">{t(collections.total_films === 0 ? "emptyLibrary" : emptyView ? "emptyViewDetail" : "collectionsFallback")}</p>
      ) : (
        <div className="mt-4 grid auto-cols-[85%] grid-flow-col gap-4 overflow-x-auto pb-2 sm:auto-cols-auto sm:grid-flow-row sm:grid-cols-2 sm:gap-x-6 sm:overflow-visible lg:grid-cols-3">
          {collections.items.map(item => {
            const label = formatExploreFacetLabel(item.dimension, item.key, item.label, locale, localizeCountries);
            const title = t(item.dimension === "country" && item.view === "unwatched" ? "collectionUnwatchedCountry" : `collectionTitles.${item.dimension}`, { label });
            const artwork = item.preview_film.artwork;
            const local = artwork?.poster_thumb_local || artwork?.poster_local;
            const src = local ? API.mediaUrl(local) : artwork?.poster_provider ? API.providerArtworkUrl(artwork.poster_provider) : null;
            return (
              <button key={`${item.dimension}:${item.key}:${item.view}`} type="button" onClick={() => onSelect(item)} className="focus-ring duration-standard group flex min-w-0 items-center gap-4 border-b border-line pb-4 text-left transition-colors hover:border-ink-muted">
                <span className="relative block h-24 w-16 shrink-0 overflow-hidden rounded-media bg-surface-raised">
                  {src ? <Image src={src} alt="" fill sizes="64px" className="object-cover" /> : <Film className="m-auto mt-9 h-5 w-5 text-ink-disabled" />}
                </span>
                <span className="min-w-0">
                  <span className="line-clamp-2 text-sm font-medium leading-6 text-ink">{title}</span>
                  <span className="mt-1 block text-xs text-ink-subtle">{t("filmCount", { count: item.count })}{item.view !== "all" ? ` · ${t(`views.${item.view}`)}` : ""}</span>
                  <span className="mt-2 block truncate text-xs text-ink-muted">{item.preview_film.title}</span>
                </span>
              </button>
            );
          })}
        </div>
      )}
    </section>
  );
}

export function QueryRibbon({ query, labels, unresolved, locale, localizeCountries, onRemove, onClear, onPersonMatch }: {
  query: ExploreQueryState;
  labels: Map<string, { label: string; roles?: string[] }>;
  unresolved: Set<string>;
  locale: string;
  localizeCountries: boolean;
  onRemove: (dimension: ExploreDimension, key: string) => void;
  onClear: () => void;
  onPersonMatch: (value: ExploreQueryState["personMatch"]) => void;
}) {
  const t = useTranslations("Explore");
  if (!hasExploreFilters(query)) return null;
  return (
    <section aria-labelledby="query-ribbon-title" className="space-y-3 border-y border-line py-4">
      <div className="flex items-center justify-between gap-3">
        <h2 id="query-ribbon-title" className="text-sm font-medium text-ink">{t("activeFilters")}</h2>
        <Button variant="ghost" size="sm" onClick={onClear}>{t("clearAll")}</Button>
      </div>
      {EXPLORE_DIMENSIONS.filter(dimension => query[dimension].length > 0).map(dimension => (
        <div key={dimension} className="flex min-w-0 flex-wrap items-center gap-2">
          <span className="text-xs text-ink-muted">{t(`dimensions.${dimension}`)}</span>
          {query[dimension].map((key, index) => {
            const label = formatExploreFacetLabel(dimension, key, labels.get(`${dimension}:${key}`)?.label ?? key, locale, localizeCountries);
            const warning = unresolved.has(`${dimension}:${key}`);
            return (
              <Fragment key={key}>
                {index > 0 ? <span className="text-xs text-ink-subtle">{t(dimension === "person" && query.personMatch === "all" ? "and" : "or")}</span> : null}
                <button type="button" aria-label={t("removeFact", { fact: label })} onClick={() => onRemove(dimension, key)} title={warning ? t("unresolvedShort") : label} className={`focus-ring duration-standard inline-flex min-h-11 max-w-full items-center gap-2 rounded-pill border px-3 py-2 text-sm transition-colors ${warning ? "border-warning/40 bg-warning/10 text-warning" : "border-line-strong bg-surface-raised text-ink hover:bg-surface-hover"}`}>
                  <span className="truncate">{label}</span>
                  {warning ? <span className="text-xs">{t("unresolvedShort")}</span> : null}
                  <X className="h-3.5 w-3.5 shrink-0" />
                </button>
              </Fragment>
            );
          })}
        </div>
      ))}
      {query.person.length > 0 ? (
        <div className="space-y-2">
          <div role="group" aria-label={t("personMatchLabel")} className="flex flex-wrap items-center gap-1">
            <span className="mr-2 text-xs text-ink-muted">{t("personMatchLabel")}</span>
            {(["all", "any"] as const).map(mode => <Button key={mode} size="sm" variant={query.personMatch === mode ? "primary" : "ghost"} aria-pressed={query.personMatch === mode} onClick={() => onPersonMatch(mode)}>{t(`personMatch.${mode}`)}</Button>)}
          </div>
          <p className="text-xs leading-5 text-ink-subtle">{t("personMatchHint")}</p>
        </div>
      ) : null}
      <p className="text-xs leading-5 text-ink-subtle">{t("booleanRule")}</p>
    </section>
  );
}

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
  onProfileSaved: () => void;
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
  onProfileSaved,
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
        {!results ? (
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
                <LibraryMovieCard movie={item.film} onProfileSaved={onProfileSaved} />
                {item.matched_facts.length > 0 ? (
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

      {results && (previousOffset !== null || nextOffset !== null) ? (
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
