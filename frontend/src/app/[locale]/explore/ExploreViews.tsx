"use client";

import { Fragment, type RefObject } from "react";
import Image from "next/image";
import { motion } from "framer-motion";
import {
  ArrowDown,
  ArrowUp,
  ChevronLeft,
  ChevronRight,
  Compass,
  Film,
  Globe2,
  Search,
  Sparkles,
  UserRound,
  X,
} from "lucide-react";
import { useTranslations } from "next-intl";

import { Link } from "@/i18n/routing";
import { API } from "@/lib/api";
import {
  EXPLORE_DIMENSIONS,
  formatExploreFacetLabel,
  hasExploreFilters,
  type ExploreQueryState,
} from "@/lib/explore";
import type {
  ExploreContext,
  ExploreContextItem,
  ExploreDimension,
  ExploreFilmPage,
  ExploreOverview,
  ExploreView,
} from "@/types/movie";
import { Button } from "@/components/ui/Button";
import LibraryMovieCard from "@/app/[locale]/library/LibraryMovieCard";
import { Spinner } from "@/components/ui/Feedback";

const DIMENSION_ICON = {
  genre: Film,
  person: UserRound,
  country: Globe2,
  decade: Compass,
} satisfies Record<ExploreDimension, typeof Film>;

type FactLabel = {
  label: string;
  roles?: string[];
};

type LensDeckProps = {
  overview: ExploreOverview;
  context: ExploreContext;
  locale: string;
  localizeCountries: boolean;
  onOpenLens: (dimension: ExploreDimension) => void;
};

type QueryRibbonProps = {
  query: ExploreQueryState;
  labels: Map<string, FactLabel>;
  unresolved: Set<string>;
  locale: string;
  localizeCountries: boolean;
  onRemove: (dimension: ExploreDimension, key: string) => void;
  onClear: () => void;
};

type LensPanelProps = {
  activeDimension: ExploreDimension;
  context: ExploreContext;
  locale: string;
  localizeCountries: boolean;
  reducedMotion: boolean;
  onChangeDimension: (dimension: ExploreDimension) => void;
  onSelect: (dimension: ExploreDimension, item: ExploreContextItem) => void;
  onBrowseAll: (dimension: ExploreDimension) => void;
};

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
};

function contextDimension(context: ExploreContext, dimension: ExploreDimension) {
  return context.dimensions.find((entry) => entry.dimension === dimension);
}

function artworkUrl(item?: ExploreContextItem | null) {
  const artwork = item?.preview_film?.artwork;
  if (!artwork) return null;
  const local =
    artwork.backdrop_thumb_local ||
    artwork.poster_thumb_local ||
    artwork.backdrop_local ||
    artwork.poster_local;
  if (local) return API.mediaUrl(local);
  const provider = artwork.backdrop_provider || artwork.poster_provider;
  return provider ? API.providerArtworkUrl(provider) : null;
}

function ExploreArtwork({ item, label }: { item?: ExploreContextItem; label: string }) {
  const src = artworkUrl(item);
  return (
    <div className="absolute inset-0 overflow-hidden bg-[radial-gradient(circle_at_20%_20%,rgba(196,160,92,0.2),transparent_45%),linear-gradient(145deg,#22211f,#0b0b0c)]">
      {src ? (
        <Image
          src={src}
          alt=""
          fill
          sizes="(max-width: 768px) 90vw, 360px"
          className="object-cover transition duration-200 group-hover:scale-[1.03] group-focus-visible:scale-[1.03]"
        />
      ) : (
        <span className="absolute right-5 top-2 font-serif text-8xl text-white/[0.06]">
          {label.slice(0, 1).toUpperCase()}
        </span>
      )}
      <div className="absolute inset-0 bg-gradient-to-t from-black via-black/45 to-black/5" />
    </div>
  );
}

export function LensDeck({
  overview,
  context,
  locale,
  localizeCountries,
  onOpenLens,
}: LensDeckProps) {
  const t = useTranslations("Explore");
  const conflicted = overview.dimensions.reduce(
    (sum, dimension) => sum + dimension.coverage.conflicted_films,
    0,
  );
  const missing = overview.dimensions.reduce(
    (sum, dimension) => sum + dimension.coverage.missing_films,
    0,
  );

  return (
    <section aria-labelledby="lens-deck-title">
      <div className="mb-6">
        <div>
          <p className="eyebrow">{t("lensDeckEyebrow")}</p>
          <h2 id="lens-deck-title" className="mt-2 font-serif text-3xl text-white md:text-4xl">
            {t("lensDeckTitle")}
          </h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-white/55">
            {t("lensDeckDescription")}
          </p>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        {EXPLORE_DIMENSIONS.map((dimension) => {
          const overviewDimension = overview.dimensions.find((item) => item.dimension === dimension);
          const dimensionContext = contextDimension(context, dimension);
          const clue = dimensionContext?.items[0];
          const label = clue
            ? formatExploreFacetLabel(dimension, clue.key, clue.label, locale, localizeCountries)
            : t(`dimensions.${dimension}`);
          const Icon = DIMENSION_ICON[dimension];
          const coverage = overviewDimension?.coverage.covered_films ?? 0;
          const total = overviewDimension?.coverage.total_films ?? overview.total_films;

          return (
            <button
              key={dimension}
              type="button"
              onClick={() => onOpenLens(dimension)}
              className="group relative min-h-64 overflow-hidden rounded-[1.75rem] border border-white/10 text-left outline-none transition duration-200 hover:-translate-y-0.5 hover:border-gold/40 focus-visible:ring-2 focus-visible:ring-gold/70 motion-reduce:transform-none"
              aria-label={t("openLens", { dimension: t(`dimensions.${dimension}`) })}
            >
              <ExploreArtwork item={clue} label={label} />
              <div className="relative flex min-h-64 flex-col justify-between p-6">
                <div className="flex items-center justify-between gap-3">
                  <span className="inline-flex h-10 w-10 items-center justify-center rounded-full border border-white/15 bg-black/30 text-gold backdrop-blur">
                    <Icon className="h-4 w-4" />
                  </span>
                  <span className="rounded-full border border-white/10 bg-black/35 px-3 py-1 text-[11px] uppercase tracking-[0.15em] text-white/60 backdrop-blur">
                    {t("coverage", { covered: coverage, total })}
                  </span>
                </div>
                <div>
                  <p className="text-xs uppercase tracking-[0.2em] text-white/50">
                    {t(`dimensions.${dimension}`)}
                  </p>
                  <p className="mt-2 font-serif text-3xl text-white">{label}</p>
                  <p className="mt-2 line-clamp-1 text-sm text-white/50">
                    {clue?.preview_film?.title || t("lensFallback")}
                  </p>
                </div>
              </div>
            </button>
          );
        })}
      </div>

      <details className="mt-5 rounded-2xl border border-white/8 bg-white/[0.025] px-5 py-4 text-sm text-white/55">
        <summary className="cursor-pointer list-none font-medium text-white/70 outline-none focus-visible:text-gold">
          <span className="inline-flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-gold/70" />
            {t("dataHealth")}
            <span className="text-white/35">·</span>
            <span className="font-normal text-white/40">
              {t("dataHealthSummary", { conflicted, missing })}
            </span>
          </span>
        </summary>
        <div className="mt-3 flex flex-wrap items-center justify-between gap-3 border-t border-white/8 pt-3">
          <p>{t("dataHealthDetail")}</p>
          <Link href="/library?view=metadata" className="text-gold hover:text-gold-light">
            {t("review")}
          </Link>
        </div>
      </details>
    </section>
  );
}

export function QueryRibbon({
  query,
  labels,
  unresolved,
  locale,
  localizeCountries,
  onRemove,
  onClear,
}: QueryRibbonProps) {
  const t = useTranslations("Explore");
  const selectedDimensions = EXPLORE_DIMENSIONS.filter((dimension) => query[dimension].length > 0);
  if (!hasExploreFilters(query)) return null;

  return (
    <section
      aria-labelledby="query-ribbon-title"
      className="rounded-[1.5rem] border border-white/10 bg-white/[0.035] px-4 py-4 md:px-5"
    >
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <p id="query-ribbon-title" className="text-[10px] uppercase tracking-[0.22em] text-white/40">
            {t("journeyTitle")}
          </p>
          <p className="mt-1 font-serif text-lg text-white/80">{t("showFilmsWhere")}</p>
        </div>
        <button
          type="button"
          onClick={onClear}
          className="shrink-0 rounded-full px-3 py-1.5 text-xs text-white/45 transition hover:bg-white/5 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold/60"
        >
          {t("clearAll")}
        </button>
      </div>

      <div className="mt-4 flex flex-col gap-3">
        {selectedDimensions.map((dimension, dimensionIndex) => (
          <Fragment key={dimension}>
            {dimensionIndex > 0 ? (
              <span className="ml-2 text-[10px] uppercase tracking-[0.2em] text-gold/60">{t("and")}</span>
            ) : null}
            <div className="flex min-w-0 flex-wrap items-center gap-2">
              <span className="shrink-0 text-xs font-medium text-white/45">
                {t(`dimensions.${dimension}`)}
              </span>
              <span className="text-white/20">:</span>
              {query[dimension].map((key, keyIndex) => {
                const fact = labels.get(`${dimension}:${key}`);
                const label = formatExploreFacetLabel(
                  dimension,
                  key,
                  fact?.label ?? key,
                  locale,
                  localizeCountries,
                );
                const warning = unresolved.has(`${dimension}:${key}`);
                return (
                  <Fragment key={key}>
                    {keyIndex > 0 ? (
                      <span className="text-[10px] uppercase tracking-[0.16em] text-white/30">{t("or")}</span>
                    ) : null}
                    <button
                      type="button"
                      onClick={() => onRemove(dimension, key)}
                      className={`inline-flex max-w-full items-center gap-2 rounded-full border px-3 py-1.5 text-sm outline-none transition focus-visible:ring-2 focus-visible:ring-gold/60 ${
                        warning
                          ? "border-amber-400/40 bg-amber-400/10 text-amber-100"
                          : "border-gold/25 bg-gold/8 text-gold-light hover:bg-gold/15"
                      }`}
                      title={warning ? t("unresolvedShort") : t("removeFact", { fact: label })}
                    >
                      <span className="truncate">{label}</span>
                      {warning ? <span className="text-[10px] uppercase">{t("unresolvedShort")}</span> : null}
                      <X className="h-3.5 w-3.5 shrink-0" />
                    </button>
                  </Fragment>
                );
              })}
              {query[dimension].length > 1 ? (
                <span className="text-[10px] text-white/35">{t("anyOf")}</span>
              ) : null}
            </div>
          </Fragment>
        ))}
      </div>
    </section>
  );
}

export function LensPanel({
  activeDimension,
  context,
  locale,
  localizeCountries,
  reducedMotion,
  onChangeDimension,
  onSelect,
  onBrowseAll,
}: LensPanelProps) {
  const t = useTranslations("Explore");
  const active = contextDimension(context, activeDimension);

  return (
    <section aria-labelledby="current-lens-title" className="min-w-0">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="eyebrow">{t("currentLens")}</p>
          <h2 id="current-lens-title" className="mt-1 font-serif text-2xl text-white">
            {t(`dimensions.${activeDimension}`)}
          </h2>
        </div>
        <span className="rounded-full border border-white/10 px-2.5 py-1 text-[10px] uppercase tracking-[0.14em] text-white/40">
          {active?.operator === "or" ? t("lensOperatorOr") : t("lensOperatorAnd")}
        </span>
      </div>

      <div className="mt-4 grid grid-cols-4 gap-1 rounded-xl border border-white/8 bg-black/25 p-1">
        {EXPLORE_DIMENSIONS.map((dimension) => {
          const Icon = DIMENSION_ICON[dimension];
          const selected = dimension === activeDimension;
          return (
            <button
              key={dimension}
              type="button"
              onClick={() => onChangeDimension(dimension)}
              aria-pressed={selected}
              className={`flex min-w-0 flex-col items-center gap-1 rounded-lg px-1 py-2 text-[10px] outline-none transition focus-visible:ring-2 focus-visible:ring-gold/60 ${
                selected ? "bg-white/10 text-white" : "text-white/35 hover:bg-white/5 hover:text-white/70"
              }`}
            >
              <Icon className="h-3.5 w-3.5" />
              <span className="truncate">{t(`dimensions.${dimension}`)}</span>
            </button>
          );
        })}
      </div>

      <p className="mt-4 text-xs leading-5 text-white/45">
        {active?.operator === "or" ? t("lensOrHint") : t("lensAndHint")}
      </p>

      <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-1">
        {active?.items.map((item, index) => {
          const label = formatExploreFacetLabel(
            activeDimension,
            item.key,
            item.label,
            locale,
            localizeCountries,
          );
          return (
            <motion.button
              key={`${activeDimension}:${item.key}`}
              type="button"
              initial={reducedMotion ? false : { opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: reducedMotion ? 0 : 0.18, delay: reducedMotion ? 0 : index * 0.025 }}
              onClick={() => onSelect(activeDimension, item)}
              className="group relative min-h-36 overflow-hidden rounded-2xl border border-white/10 text-left outline-none transition hover:border-gold/40 focus-visible:ring-2 focus-visible:ring-gold/70"
              title={item.preview_film?.title || label}
            >
              <ExploreArtwork item={item} label={label} />
              <div className="relative flex min-h-36 flex-col justify-end p-4">
                <p className="line-clamp-1 font-serif text-xl text-white">{label}</p>
                {item.roles.length > 0 ? (
                  <p className="mt-1 text-[10px] uppercase tracking-[0.16em] text-white/50">
                    {item.roles.map((role) => t(`roles.${role}`)).join(" · ")}
                  </p>
                ) : null}
                <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs">
                  <span className="text-gold-light">
                    {active.operator === "or"
                      ? t("adds", { count: item.additional_count })
                      : t("remains", { count: item.result_count })}
                  </span>
                  {item.source_kinds.length > 0 ? (
                    <span className="max-w-24 truncate text-white/35">{item.source_kinds.join(" · ")}</span>
                  ) : null}
                </div>
                {item.preview_film ? (
                  <p className="mt-2 translate-y-2 truncate text-[11px] text-white/0 transition group-hover:translate-y-0 group-hover:text-white/45 group-focus-visible:translate-y-0 group-focus-visible:text-white/45 motion-reduce:transform-none">
                    {item.preview_film.title}
                  </p>
                ) : null}
              </div>
            </motion.button>
          );
        })}
      </div>

      {active?.items.length === 0 ? (
        <div className="mt-4 rounded-2xl border border-dashed border-white/10 px-4 py-8 text-center text-sm text-white/40">
          {t("lensEmpty")}
        </div>
      ) : null}

      <Button className="mt-4 w-full" variant="secondary" onClick={() => onBrowseAll(activeDimension)}>
        <Search className="h-4 w-4" />
        {t("browseAll")}
        {active?.has_more ? <span className="text-white/35">+</span> : null}
      </Button>
    </section>
  );
}

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
      <div className="flex flex-col gap-3 border-b border-white/8 pb-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="eyebrow">{t("strictResults")}</p>
          <h2
            id="explore-results-title"
            ref={headingRef}
            tabIndex={-1}
            className="mt-1 font-serif text-3xl text-white outline-none"
          >
            {t("resultCount", { count: total })}
          </h2>
        </div>
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <div role="group" className="inline-flex rounded-full border border-white/10 bg-black/20 p-1" aria-label={t("viewLabel")}>
            {(["all", "watched", "unwatched"] as const).map((view) => (
              <button
                key={view}
                type="button"
                aria-pressed={query.view === view}
                onClick={() => onView(view)}
                className={`rounded-full px-3 py-1.5 text-xs outline-none transition focus-visible:ring-2 focus-visible:ring-gold/60 ${
                  query.view === view ? "bg-white/10 text-white" : "text-white/40 hover:text-white/70"
                }`}
              >
                {t(`views.${view}`)}
              </button>
            ))}
          </div>
          <div role="group" className="inline-flex rounded-full border border-white/10 bg-black/20 p-1" aria-label={t("sortLabel")}>
            {(["title", "year"] as const).map((sort) => (
              <button
                key={sort}
                type="button"
                aria-pressed={query.sort === sort}
                onClick={() => onSort(sort)}
                className={`rounded-full px-3 py-1.5 text-xs outline-none transition focus-visible:ring-2 focus-visible:ring-gold/60 ${
                  query.sort === sort ? "bg-white/10 text-white" : "text-white/40 hover:text-white/70"
                }`}
              >
                {t(`sorts.${sort}`)}
              </button>
            ))}
            <button
              type="button"
              onClick={onDirection}
              className="rounded-full p-1.5 text-white/45 outline-none transition hover:bg-white/5 hover:text-white focus-visible:ring-2 focus-visible:ring-gold/60"
              aria-label={query.dir === "asc" ? t("ascending") : t("descending")}
            >
              {query.dir === "asc" ? <ArrowUp className="h-3.5 w-3.5" /> : <ArrowDown className="h-3.5 w-3.5" />}
            </button>
          </div>
        </div>
      </div>

      <p className="sr-only" aria-live="polite">
        {pending ? t("loadingResults") : t("resultsUpdated", { count: total })}
      </p>

      <div className="relative min-h-[32rem] pt-6">
        {pending ? (
          <div className="pointer-events-none absolute inset-x-0 top-0 z-10 h-0.5 overflow-hidden bg-white/5">
            <span className="block h-full w-1/3 animate-pulse bg-gold/70" />
          </div>
        ) : null}
        {!results ? (
          <div className="flex min-h-80 items-center justify-center">
            <Spinner className="text-gold" />
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
                {item.matched_facts.length > 0 ? (
                  <p className="mt-2 line-clamp-2 text-[10px] leading-4 text-white/35">
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
          <div className="flex min-h-80 flex-col items-center justify-center rounded-[1.5rem] border border-dashed border-white/10 px-6 text-center">
            <Compass className="h-8 w-8 text-white/25" />
            <h3 className="mt-4 font-serif text-2xl text-white">{t("zeroTitle")}</h3>
            <p className="mt-2 max-w-lg text-sm leading-6 text-white/45">{t("zeroDetail")}</p>
            <Button className="mt-5" variant="secondary" onClick={onClear}>
              {t("clearAll")}
            </Button>
          </div>
        )}
      </div>

      {results && (previousOffset !== null || nextOffset !== null) ? (
        <nav className="mt-8 flex items-center justify-between border-t border-white/8 pt-5" aria-label={t("paginationLabel")}>
          <Button
            variant="ghost"
            disabled={previousOffset === null || pending}
            onClick={() => previousOffset !== null && onPage(previousOffset)}
          >
            <ChevronLeft className="h-4 w-4" />
            {t("previous")}
          </Button>
          <span className="text-xs text-white/35">
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

export function ExploreHeader({
  total,
  onFind,
}: {
  total: number;
  onFind: () => void;
}) {
  const t = useTranslations("Explore");
  return (
    <header className="flex flex-col gap-5 border-b border-white/8 pb-7 md:flex-row md:items-end md:justify-between">
      <div>
        <p className="eyebrow">{t("eyebrow")}</p>
        <h1 className="mt-2 font-serif text-5xl text-white md:text-6xl">{t("title")}</h1>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-white/55">{t("description")}</p>
        <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-white/40">
          <span>{t("filmCount", { count: total })}</span>
          <span aria-hidden="true">·</span>
          <span>{t("policy")}</span>
        </div>
      </div>
      <Button variant="secondary" onClick={onFind}>
        <Search className="h-4 w-4" />
        {t("findFact")}
        <kbd className="ml-1 rounded border border-white/15 px-1.5 py-0.5 text-[10px] text-white/45">/</kbd>
      </Button>
    </header>
  );
}
