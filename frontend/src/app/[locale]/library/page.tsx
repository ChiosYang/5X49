import { getTranslations } from "next-intl/server";
import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  CalendarPlus,
  CheckCircle2,
  Circle,
  Clock3,
  FolderClock,
  ListFilter,
  Star,
  TriangleAlert,
  Type,
} from "lucide-react";

import { Link } from "@/i18n/routing";
import {
  buildLibraryCareState,
  buildLibraryHref,
  normalizeLibraryView,
  type LibraryFilterKey,
  type LibraryQueryState,
  type LibrarySortDirection,
  type LibrarySortKey,
  type LibraryView,
} from "@/lib/library-care";
import { getLibraryEmptyState } from "@/lib/library-onboarding";
import {
  getLibraryFilms,
  getLibraryOrganizationCandidates,
  getMissingLibraryItems,
} from "@/lib/server-api";
import type { LibraryFilmSummary, MissingLibraryItemsResponse } from "@/types/movie";
import LibraryActions from "./LibraryActions";
import LibraryInboxCare from "./LibraryInboxCare";
import LibraryMetadataCare from "./LibraryMetadataCare";
import LibraryMovieCard from "./LibraryMovieCard";
import LibraryOfflineCare from "./LibraryOfflineCare";
import LibraryOnboarding from "./LibraryOnboarding";

interface LibraryPageProps {
  params: Promise<{ locale: string }>;
  searchParams?: Promise<{
    view?: string | string[];
    sort?: string | string[];
    dir?: string | string[];
    filter?: string | string[];
  }>;
}
const SORT_OPTIONS: Array<{
  key: LibrarySortKey;
  defaultDirection: LibrarySortDirection;
  icon: typeof Type;
  labelKey: "sortTitle" | "sortAdded" | "sortDuration";
}> = [
  { key: "title", defaultDirection: "asc", icon: Type, labelKey: "sortTitle" },
  { key: "added", defaultDirection: "desc", icon: CalendarPlus, labelKey: "sortAdded" },
  { key: "duration", defaultDirection: "desc", icon: Clock3, labelKey: "sortDuration" },
];

const FILTER_OPTIONS: Array<{
  key: LibraryFilterKey;
  icon: typeof Circle;
  labelKey: "filterAll" | "filterWatched" | "filterUnwatched" | "filterFavorite";
}> = [
  { key: "all", icon: Circle, labelKey: "filterAll" },
  { key: "watched", icon: CheckCircle2, labelKey: "filterWatched" },
  { key: "unwatched", icon: Circle, labelKey: "filterUnwatched" },
  { key: "favorite", icon: Star, labelKey: "filterFavorite" },
];

const VIEW_LABELS: Record<LibraryView, "allFilms" | "metadataTab" | "inboxTab" | "offlineTab"> = {
  all: "allFilms",
  metadata: "metadataTab",
  inbox: "inboxTab",
  offline: "offlineTab",
};

function firstParam(value?: string | string[]) {
  return Array.isArray(value) ? value[0] : value;
}

function normalizeSort(value?: string): LibrarySortKey {
  return SORT_OPTIONS.some((option) => option.key === value) ? value as LibrarySortKey : "title";
}

function normalizeDirection(value: string | undefined, sort: LibrarySortKey): LibrarySortDirection {
  if (value === "asc" || value === "desc") return value;
  return SORT_OPTIONS.find((option) => option.key === sort)?.defaultDirection ?? "asc";
}

function normalizeFilter(value?: string): LibraryFilterKey {
  return FILTER_OPTIONS.some((option) => option.key === value) ? value as LibraryFilterKey : "all";
}

function getDurationSeconds(film: LibraryFilmSummary) {
  return film.primary_item.video?.duration_seconds ?? (film.runtime_minutes ? film.runtime_minutes * 60 : null);
}

function getTimestamp(value?: string | null) {
  if (!value) return null;
  const timestamp = Date.parse(value);
  return Number.isNaN(timestamp) ? null : timestamp;
}

function sortMovies(movies: LibraryFilmSummary[], sort: LibrarySortKey, direction: LibrarySortDirection, locale: string) {
  const collator = new Intl.Collator(locale, { numeric: true, sensitivity: "base" });
  const multiplier = direction === "asc" ? 1 : -1;
  return [...movies].sort((a, b) => {
    if (sort === "title") {
      return collator.compare(a.title, b.title) * multiplier
        || ((a.year || 0) - (b.year || 0)) * multiplier
        || collator.compare(a.id, b.id) * multiplier;
    }
    const aValue = sort === "added" ? getTimestamp(a.primary_item.added_at) : getDurationSeconds(a);
    const bValue = sort === "added" ? getTimestamp(b.primary_item.added_at) : getDurationSeconds(b);
    if (aValue == null && bValue == null) return collator.compare(a.title, b.title);
    if (aValue == null) return 1;
    if (bValue == null) return -1;
    return (aValue - bValue) * multiplier || collator.compare(a.title, b.title);
  });
}

function viewCount(view: LibraryView, care: ReturnType<typeof buildLibraryCareState>) {
  if (view === "metadata") return care.metadataReviews;
  if (view === "inbox") return care.actionableInbox + care.waitingInbox;
  if (view === "offline") return care.offline;
  return null;
}

export default async function LibraryPage({ params, searchParams }: LibraryPageProps) {
  const t = await getTranslations("Library");
  const careT = await getTranslations("LibraryCare");
  const { locale } = await params;
  const resolvedSearchParams = searchParams ? await searchParams : {};
  const view = normalizeLibraryView(firstParam(resolvedSearchParams.view));
  const sort = normalizeSort(firstParam(resolvedSearchParams.sort));
  const direction = normalizeDirection(firstParam(resolvedSearchParams.dir), sort);
  const filter = normalizeFilter(firstParam(resolvedSearchParams.filter));
  const queryState: LibraryQueryState = { view, sort, direction, filter };

  const filmsPromise = getLibraryFilms();
  const auxiliaryPromise = Promise.allSettled([
    getLibraryOrganizationCandidates(),
    getMissingLibraryItems(),
  ]);
  const films = await filmsPromise;
  const [organizationResult, missingResult] = await auxiliaryPromise;
  const organizationCandidates = organizationResult.status === "fulfilled" ? organizationResult.value : [];
  const missingData: MissingLibraryItemsResponse = missingResult.status === "fulfilled"
    ? missingResult.value
    : { count: 0, items: [] };
  const care = buildLibraryCareState({
    films,
    organizationCandidates,
    missingItems: missingData.items,
    activeView: view,
    organizationUnavailable: organizationResult.status === "rejected",
    missingUnavailable: missingResult.status === "rejected",
  });

  const filteredMovies = films.filter((movie) => {
    const state = movie.profile_state;
    if (filter === "watched") return Boolean(state?.watched);
    if (filter === "unwatched") return !state?.watched;
    if (filter === "favorite") return Boolean(state?.favorite);
    return true;
  });
  const sortedMovies = sortMovies(filteredMovies, sort, direction, locale);
  const emptyState = getLibraryEmptyState(films.length, filteredMovies.length);
  const recommendedHref = care.recommendedView ? buildLibraryHref(queryState, care.recommendedView) : null;

  return (
    <main className="page-x min-h-screen overflow-x-hidden bg-canvas py-6 text-ink selection:bg-inverse selection:text-inverse-ink md:py-12">
      <div className="w-full pt-32">
        <header className="flex flex-col gap-7 border-b border-line pb-8 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <h1 className="type-display-editorial">{t("title")}</h1>
            {view !== "all" ? <p className="mt-3 type-label text-ink-subtle">{careT(VIEW_LABELS[view])}</p> : null}
          </div>
          <div className="flex flex-wrap items-center gap-3 lg:justify-end">
            {view === "all" && films.length > 0 ? (
              <>
                <span className="mr-1 hidden text-xs font-bold tracking-widest text-ink-subtle uppercase md:inline-block">{filteredMovies.length} FILMS</span>
                <div className="group/filter relative">
                  <button type="button" aria-label={t("filter")} title={t("filter")} className={`focus-ring duration-standard inline-flex h-11 w-11 items-center justify-center rounded-media border transition-colors ${filter === "all" ? "border-line-strong bg-surface/70 text-ink-muted hover:bg-inverse hover:text-inverse-ink" : "border-inverse bg-inverse text-inverse-ink"}`}>
                    <ListFilter className="h-4 w-4" />
                  </button>
                  <div className="z-popover pointer-events-none absolute top-full right-0 w-48 pt-3 opacity-0 transition-opacity duration-standard group-hover/filter:pointer-events-auto group-hover/filter:opacity-100 group-focus-within/filter:pointer-events-auto group-focus-within/filter:opacity-100">
                    <div className="liquid-glass-popover rounded-media border border-line/80 p-1">
                      {FILTER_OPTIONS.map((option) => {
                        const Icon = option.icon;
                        const active = filter === option.key;
                        return (
                          <Link key={option.key} href={buildLibraryHref({ ...queryState, filter: option.key }, "all")} className={`focus-ring duration-standard flex h-10 items-center justify-between rounded-control px-3 text-sm transition-colors ${active ? "bg-inverse text-inverse-ink" : "text-ink-muted hover:bg-surface-raised hover:text-ink"}`}>
                            <span className="flex min-w-0 items-center gap-2"><Icon className={`h-4 w-4 shrink-0 ${option.key === "favorite" && active ? "fill-current" : ""}`} /><span className="truncate">{t(option.labelKey)}</span></span>
                            {active ? <CheckCircle2 className="h-3.5 w-3.5" /> : null}
                          </Link>
                        );
                      })}
                    </div>
                  </div>
                </div>
                <div className="group/sort relative">
                  <button type="button" aria-label={t("sort")} title={t("sort")} className="focus-ring duration-standard inline-flex h-11 w-11 items-center justify-center rounded-media border border-line-strong bg-surface/70 text-ink-muted transition-colors hover:bg-inverse hover:text-inverse-ink">
                    <ArrowUpDown className="h-4 w-4" />
                  </button>
                  <div className="z-popover pointer-events-none absolute top-full right-0 w-48 pt-3 opacity-0 transition-opacity duration-standard group-hover/sort:pointer-events-auto group-hover/sort:opacity-100 group-focus-within/sort:pointer-events-auto group-focus-within/sort:opacity-100">
                    <div className="liquid-glass-popover rounded-media border border-line/80 p-1">
                      {SORT_OPTIONS.map((option) => {
                        const Icon = option.icon;
                        const active = sort === option.key;
                        const nextDirection = active && direction === option.defaultDirection ? option.defaultDirection === "asc" ? "desc" : "asc" : option.defaultDirection;
                        const DirectionIcon = direction === "asc" ? ArrowUp : ArrowDown;
                        return (
                          <Link key={option.key} href={buildLibraryHref({ ...queryState, sort: option.key, direction: nextDirection }, "all")} className={`focus-ring duration-standard flex h-10 items-center justify-between rounded-control px-3 text-sm transition-colors ${active ? "bg-inverse text-inverse-ink" : "text-ink-muted hover:bg-surface-raised hover:text-ink"}`}>
                            <span className="flex min-w-0 items-center gap-2"><Icon className="h-4 w-4" /><span className="truncate">{t(option.labelKey)}</span></span>
                            {active ? <DirectionIcon className="h-3.5 w-3.5" /> : null}
                          </Link>
                        );
                      })}
                    </div>
                  </div>
                </div>
              </>
            ) : null}
            {view !== "all" || emptyState !== "onboarding" ? <LibraryActions /> : null}
          </div>
        </header>

        {care.visibleViews.length > 0 ? (
          <nav aria-label={careT("careNavigation")} className="scrollbar-minimal flex max-w-full gap-1 overflow-x-auto border-b border-line py-3">
            {care.visibleViews.map((item) => {
              const count = viewCount(item, care);
              const active = view === item;
              return (
                <Link key={item} href={buildLibraryHref(queryState, item)} aria-current={active ? "page" : undefined} className={`focus-ring inline-flex min-h-10 min-w-max items-center gap-2 px-4 type-label transition-colors ${active ? "bg-inverse text-inverse-ink" : "text-ink-subtle hover:bg-surface-raised hover:text-ink"}`}>
                  {careT(VIEW_LABELS[item])}
                  {count !== null ? <span className={`rounded-pill px-2 py-0.5 text-[10px] ${active ? "bg-inverse-ink/15" : "bg-surface-raised text-ink-disabled"}`}>{count}</span> : null}
                </Link>
              );
            })}
          </nav>
        ) : null}

        {care.showStatus ? (
          <section className="mt-7 flex flex-col gap-4 border-l border-line-strong bg-surface/35 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex min-w-0 items-start gap-3">
              {care.totalActionable > 0 ? <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0 text-warning" /> : <FolderClock className="mt-0.5 h-4 w-4 shrink-0 text-ink-subtle" />}
              <div>
                <p className="text-sm font-medium text-ink">
                  {care.totalActionable > 0 ? careT("attentionSummary", { count: care.totalActionable }) : care.waitingInbox > 0 ? careT("waitingSummary", { count: care.waitingInbox }) : careT("careContext")}
                </p>
                {care.partialUnavailable ? <p className="mt-1 text-xs text-warning">{careT("partialUnavailable")}</p> : null}
              </div>
            </div>
            {recommendedHref && view === "all" ? (
              <Link href={recommendedHref} className="focus-ring inline-flex min-h-10 shrink-0 items-center justify-center bg-inverse px-4 type-label text-inverse-ink hover:bg-neutral-200">{careT("handleRecommended")}</Link>
            ) : null}
          </section>
        ) : null}

        {view === "metadata" ? (
          <div className="mt-12"><LibraryMetadataCare /></div>
        ) : view === "inbox" ? (
          <div className="mt-12"><LibraryInboxCare actionableCount={care.actionableInbox} waitingCount={care.waitingInbox} /></div>
        ) : view === "offline" ? (
          <div className="mt-12"><LibraryOfflineCare initialData={missingData} /></div>
        ) : emptyState === "onboarding" ? (
          <LibraryOnboarding rootVideoCount={organizationCandidates.length} />
        ) : emptyState === "filtered-empty" ? (
          <div className="mt-20 space-y-4 py-24 text-center">
            <p className="font-serif text-xl text-ink-subtle italic">{t("emptyFiltered")}</p>
            <Link href={buildLibraryHref({ ...queryState, filter: "all" }, "all")} className="focus-ring inline-flex min-h-10 items-center border border-line-strong px-4 text-xs font-medium tracking-widest text-ink-muted uppercase hover:border-ink-disabled hover:text-ink">{t("resetFilter")}</Link>
          </div>
        ) : (
          <div className="mt-20 grid grid-cols-1 gap-x-5 gap-y-12 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 xl:gap-x-6 xl:gap-y-14 2xl:grid-cols-5">
            {sortedMovies.map((movie, index) => <LibraryMovieCard key={`${movie.id}:${movie.profile_state.updated_at || "initial"}`} movie={movie} priority={index === 0} />)}
          </div>
        )}
      </div>
    </main>
  );
}
