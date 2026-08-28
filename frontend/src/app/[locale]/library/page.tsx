import { getTranslations } from "next-intl/server";
import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  CalendarPlus,
  CheckCircle2,
  Clock3,
  Circle,
  FolderClock,
  ListFilter,
  Star,
  TriangleAlert,
  Type,
} from "lucide-react";
import { Link } from "@/i18n/routing";
import { getLibraryFilms, getRootVideos } from "@/lib/server-api";
import type { LibraryFilmSummary } from "@/types/movie";
import { getLibraryAttentionCounts } from "@/lib/library-attention";
import { getLibraryEmptyState } from "@/lib/library-onboarding";
import LibraryMovieCard from "./LibraryMovieCard";
import LibraryOnboarding from "./LibraryOnboarding";

type LibrarySortKey = "title" | "added" | "duration";
type SortDirection = "asc" | "desc";
type LibraryFilterKey = "all" | "watched" | "unwatched" | "favorite";

interface LibraryPageProps {
  params: Promise<{
    locale: string;
  }>;
  searchParams?: Promise<{
    sort?: string | string[];
    dir?: string | string[];
    filter?: string | string[];
  }>;
}

const SORT_OPTIONS: Array<{
  key: LibrarySortKey;
  defaultDirection: SortDirection;
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

function firstParam(value?: string | string[]) {
  return Array.isArray(value) ? value[0] : value;
}

function normalizeSort(value?: string): LibrarySortKey {
  return SORT_OPTIONS.some((option) => option.key === value) ? (value as LibrarySortKey) : "title";
}

function normalizeDirection(value: string | undefined, sort: LibrarySortKey): SortDirection {
  if (value === "asc" || value === "desc") {
    return value;
  }

  return SORT_OPTIONS.find((option) => option.key === sort)?.defaultDirection || "asc";
}

function normalizeFilter(value?: string): LibraryFilterKey {
  return FILTER_OPTIONS.some((option) => option.key === value) ? (value as LibraryFilterKey) : "all";
}

function libraryHref(sort: LibrarySortKey, direction: SortDirection, filter: LibraryFilterKey) {
  const params = new URLSearchParams();
  params.set("sort", sort);
  params.set("dir", direction);
  if (filter !== "all") {
    params.set("filter", filter);
  }
  return `/library?${params.toString()}`;
}

function getDurationSeconds(film: LibraryFilmSummary) {
  return film.primary_item.video?.duration_seconds ?? (film.runtime_minutes ? film.runtime_minutes * 60 : null);
}

function getTimestamp(value?: string | null) {
  if (!value) {
    return null;
  }

  const timestamp = Date.parse(value);
  return Number.isNaN(timestamp) ? null : timestamp;
}

function sortMovies(
  movies: LibraryFilmSummary[],
  sort: LibrarySortKey,
  direction: SortDirection,
  locale: string
) {
  const collator = new Intl.Collator(locale, { numeric: true, sensitivity: "base" });
  const multiplier = direction === "asc" ? 1 : -1;

  return [...movies].sort((a, b) => {
    if (sort === "title") {
      const titleCompare = collator.compare(a.title, b.title);
      return (
        titleCompare * multiplier ||
        ((a.year || 0) - (b.year || 0)) * multiplier ||
        collator.compare(a.id, b.id) * multiplier
      );
    }

    const aValue = sort === "added" ? getTimestamp(a.primary_item.added_at) : getDurationSeconds(a);
    const bValue = sort === "added" ? getTimestamp(b.primary_item.added_at) : getDurationSeconds(b);

    if (aValue == null && bValue == null) {
      return collator.compare(a.title, b.title);
    }
    if (aValue == null) {
      return 1;
    }
    if (bValue == null) {
      return -1;
    }

    const valueCompare = (aValue - bValue) * multiplier;
    return valueCompare || collator.compare(a.title, b.title);
  });
}

export default async function LibraryPage({ params, searchParams }: LibraryPageProps) {
  const t = await getTranslations("Library");
  const { locale } = await params;
  const resolvedSearchParams = searchParams ? await searchParams : {};
  const sort = normalizeSort(firstParam(resolvedSearchParams.sort));
  const direction = normalizeDirection(firstParam(resolvedSearchParams.dir), sort);
  const filter = normalizeFilter(firstParam(resolvedSearchParams.filter));
  const [films, rootVideos] = await Promise.all([getLibraryFilms(), getRootVideos()]);
  const attention = getLibraryAttentionCounts(films, rootVideos.length);
  const filteredMovies = films.filter((movie) => {
    const state = movie.profile_state;
    if (filter === "watched") return Boolean(state?.watched);
    if (filter === "unwatched") return !state?.watched;
    if (filter === "favorite") return Boolean(state?.favorite);
    return true;
  });
  const sortedMovies = sortMovies(filteredMovies, sort, direction, locale);
  const emptyState = getLibraryEmptyState(films.length, filteredMovies.length);

  return (
    <div className="page-x min-h-screen bg-canvas py-6 text-ink selection:bg-inverse selection:text-inverse-ink md:py-12">
      <div className="w-full pt-32">
        <header className="flex flex-col gap-6 border-b border-line pb-8 md:flex-row md:items-end md:justify-between">
          <div>
            <h1 className="type-display-editorial">
              {t("title")}
            </h1>
          </div>
          <div className="flex flex-wrap items-center gap-4 md:justify-end md:gap-6">
            <span className="hidden text-xs font-bold tracking-widest text-ink-subtle uppercase md:inline-block">
              {filteredMovies.length} FILMS
            </span>
            {attention.metadataReviews > 0 ? (
              <Link
                href="/library/manage#metadata-reviews"
                className="focus-ring duration-fast inline-flex min-h-10 items-center gap-2 rounded-pill border border-warning/45 bg-warning/10 px-3 type-badge text-warning transition-colors hover:border-warning/75 hover:bg-warning/15"
              >
                <TriangleAlert className="h-3.5 w-3.5 shrink-0" />
                {t("metadataReviewsPending", { count: attention.metadataReviews })}
              </Link>
            ) : null}
            {attention.rootVideos > 0 ? (
              <Link
                href="/library/manage#root-video-reviews"
                className="focus-ring duration-fast inline-flex min-h-10 items-center gap-2 rounded-pill border border-line-strong bg-surface/70 px-3 type-badge text-ink-muted transition-colors hover:border-ink-disabled hover:bg-surface-hover hover:text-ink"
              >
                <FolderClock className="h-3.5 w-3.5 shrink-0" />
                {t("rootVideosPending", { count: attention.rootVideos })}
              </Link>
            ) : null}
            {films.length > 0 ? (
              <>
            <div className="group/filter relative">
              <button
                type="button"
                aria-label={t("filter")}
                title={t("filter")}
                className={`focus-ring duration-standard inline-flex h-10 w-10 items-center justify-center rounded-media border transition-colors ${
                  filter === "all"
                    ? "border-line-strong bg-surface/70 text-ink-muted hover:bg-inverse hover:text-inverse-ink"
                    : "border-inverse bg-inverse text-inverse-ink"
                }`}
              >
                <ListFilter className="h-4 w-4" />
              </button>
              <div className="z-popover pointer-events-none absolute top-full right-0 w-48 pt-3 opacity-0 transition-opacity duration-standard group-hover/filter:pointer-events-auto group-hover/filter:opacity-100 group-focus-within/filter:pointer-events-auto group-focus-within/filter:opacity-100">
                <div className="liquid-glass-popover relative rounded-media border border-line/80 p-1">
                  {FILTER_OPTIONS.map((option) => {
                    const Icon = option.icon;
                    const isActive = filter === option.key;
                    return (
                      <Link
                        key={option.key}
                        href={libraryHref(sort, direction, option.key)}
                        aria-label={t(option.labelKey)}
                        className={`focus-ring duration-standard flex h-10 items-center justify-between rounded-control px-3 text-sm transition-colors ${
                          isActive
                            ? "bg-inverse text-inverse-ink"
                            : "text-ink-muted hover:bg-surface-raised hover:text-ink"
                        }`}
                      >
                        <span className="flex min-w-0 items-center gap-2">
                          <Icon className={`h-4 w-4 shrink-0 ${option.key === "favorite" && isActive ? "fill-current" : ""}`} />
                          <span className="truncate">{t(option.labelKey)}</span>
                        </span>
                        {isActive && <CheckCircle2 className="h-3.5 w-3.5 shrink-0" />}
                      </Link>
                    );
                  })}
                </div>
              </div>
            </div>
            <div className="group/sort relative">
              <button
                type="button"
                aria-label={t("sort")}
                title={t("sort")}
                className="focus-ring duration-standard inline-flex h-10 w-10 items-center justify-center rounded-media border border-line-strong bg-surface/70 text-ink-muted transition-colors hover:bg-inverse hover:text-inverse-ink"
              >
                <ArrowUpDown className="h-4 w-4" />
              </button>
              <div className="z-popover pointer-events-none absolute top-full right-0 w-48 pt-3 opacity-0 transition-opacity duration-standard group-hover/sort:pointer-events-auto group-hover/sort:opacity-100 group-focus-within/sort:pointer-events-auto group-focus-within/sort:opacity-100">
                <div className="liquid-glass-popover relative rounded-media border border-line/80 p-1">
                  {SORT_OPTIONS.map((option) => {
                    const Icon = option.icon;
                    const isActive = sort === option.key;
                    const nextDirection = isActive && direction === option.defaultDirection
                      ? option.defaultDirection === "asc" ? "desc" : "asc"
                      : option.defaultDirection;
                    const DirectionIcon = direction === "asc" ? ArrowUp : ArrowDown;

                    return (
                      <Link
                        key={option.key}
                        href={libraryHref(option.key, nextDirection, filter)}
                        aria-label={t("sortBy", { field: t(option.labelKey) })}
                        className={`focus-ring duration-standard flex h-10 items-center justify-between rounded-control px-3 text-sm transition-colors ${
                          isActive
                            ? "bg-inverse text-inverse-ink"
                            : "text-ink-muted hover:bg-surface-raised hover:text-ink"
                        }`}
                      >
                        <span className="flex min-w-0 items-center gap-2">
                          <Icon className="h-4 w-4 shrink-0" />
                          <span className="truncate">{t(option.labelKey)}</span>
                        </span>
                        {isActive && <DirectionIcon className="h-3.5 w-3.5 shrink-0" />}
                      </Link>
                    );
                  })}
                </div>
              </div>
            </div>
              </>
            ) : null}
          </div>
        </header>

        {emptyState === "onboarding" ? (
          <LibraryOnboarding rootVideoCount={rootVideos.length} />
        ) : emptyState === "filtered-empty" ? (
          <div className="mt-20 space-y-4 py-24 text-center">
            <p className="font-serif text-xl text-ink-subtle italic">{t("emptyFiltered")}</p>
            <Link
              href={libraryHref(sort, direction, "all")}
              className="focus-ring inline-flex min-h-10 items-center border border-line-strong px-4 text-xs font-medium tracking-widest text-ink-muted uppercase hover:border-ink-disabled hover:text-ink"
            >
              {t("resetFilter")}
            </Link>
          </div>
        ) : (
          <div className="mt-20 grid grid-cols-1 gap-x-5 gap-y-12 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 xl:gap-x-6 xl:gap-y-14 2xl:grid-cols-5">
            {sortedMovies.map((movie, i) => (
              <LibraryMovieCard
                key={movie.id}
                movie={movie}
                priority={i === 0}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
