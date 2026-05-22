import { getTranslations } from "next-intl/server";
import { ArrowDown, ArrowUp, ArrowUpDown, CalendarPlus, Clock3, Type } from "lucide-react";
import { Link } from "@/i18n/routing";
import { getLibrary, getRootVideos } from "@/lib/server-api";
import type { LibraryMovie } from "@/types/movie";
import LibraryMovieCard from "./LibraryMovieCard";
import LibraryOrganizeRootButton from "./LibraryOrganizeRootButton";
import LibraryRefreshButton from "./LibraryRefreshButton";

type LibrarySortKey = "title" | "added" | "duration";
type SortDirection = "asc" | "desc";

interface LibraryPageProps {
  params: Promise<{
    locale: string;
  }>;
  searchParams?: Promise<{
    sort?: string | string[];
    dir?: string | string[];
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

function getDurationSeconds(movie: LibraryMovie) {
  return movie.video_duration ?? (movie.runtime ? movie.runtime * 60 : null);
}

function getTimestamp(value?: string | null) {
  if (!value) {
    return null;
  }

  const timestamp = Date.parse(value);
  return Number.isNaN(timestamp) ? null : timestamp;
}

function sortMovies(
  movies: LibraryMovie[],
  sort: LibrarySortKey,
  direction: SortDirection,
  locale: string
) {
  const collator = new Intl.Collator(locale, { numeric: true, sensitivity: "base" });
  const multiplier = direction === "asc" ? 1 : -1;

  return [...movies].sort((a, b) => {
    if (sort === "title") {
      const titleCompare = collator.compare(a.title_cn || a.title, b.title_cn || b.title);
      return (
        titleCompare * multiplier ||
        (a.year - b.year) * multiplier ||
        collator.compare(a.id, b.id) * multiplier
      );
    }

    const aValue = sort === "added" ? getTimestamp(a.added_at) : getDurationSeconds(a);
    const bValue = sort === "added" ? getTimestamp(b.added_at) : getDurationSeconds(b);

    if (aValue == null && bValue == null) {
      return collator.compare(a.title_cn || a.title, b.title_cn || b.title);
    }
    if (aValue == null) {
      return 1;
    }
    if (bValue == null) {
      return -1;
    }

    const valueCompare = (aValue - bValue) * multiplier;
    return valueCompare || collator.compare(a.title_cn || a.title, b.title_cn || b.title);
  });
}

export default async function LibraryPage({ params, searchParams }: LibraryPageProps) {
  const t = await getTranslations("Library");
  const { locale } = await params;
  const resolvedSearchParams = searchParams ? await searchParams : {};
  const sort = normalizeSort(firstParam(resolvedSearchParams.sort));
  const direction = normalizeDirection(firstParam(resolvedSearchParams.dir), sort);
  const [movies, rootVideos] = await Promise.all([getLibrary(), getRootVideos()]);
  const visibleMovies = movies.filter(
    (movie) => !["missing", "ignored", "reverted"].includes(movie.library_status || "")
  );
  const sortedMovies = sortMovies(visibleMovies, sort, direction, locale);

  return (
    <div className="min-h-screen bg-black text-white px-8 py-6 md:px-12 md:py-12 selection:bg-white selection:text-black">
      <div className="w-full space-y-20 pt-32">
        <header className="flex flex-col gap-6 border-b border-neutral-900 pb-8 md:flex-row md:items-end md:justify-between">
          <div>
            <h1 className="text-6xl md:text-9xl font-serif tracking-tighter leading-none">
              {t("title")}
            </h1>
          </div>
          <div className="flex flex-wrap items-center gap-4 md:justify-end md:gap-6">
            <span className="text-neutral-500 text-xs font-bold uppercase tracking-widest hidden md:inline-block">
              {visibleMovies.length} FILMS
            </span>
            <div className="group/sort relative">
              <button
                type="button"
                aria-label={t("sort")}
                title={t("sort")}
                className="inline-flex h-10 w-10 items-center justify-center rounded-md border border-neutral-800 bg-neutral-950/70 text-neutral-400 transition-colors hover:bg-white hover:text-black focus:bg-white focus:text-black focus:outline-none"
              >
                <ArrowUpDown className="h-4 w-4" />
              </button>
              <div className="pointer-events-none absolute right-0 top-full z-40 w-48 pt-3 opacity-0 transition-opacity duration-150 group-hover/sort:pointer-events-auto group-hover/sort:opacity-100 group-focus-within/sort:pointer-events-auto group-focus-within/sort:opacity-100">
                <div className="rounded-md border border-white/10 bg-neutral-950 p-1 shadow-2xl shadow-black/40">
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
                        href={`/library?sort=${option.key}&dir=${nextDirection}`}
                        aria-label={t("sortBy", { field: t(option.labelKey) })}
                        className={`flex h-10 items-center justify-between rounded px-3 text-sm transition-colors ${
                          isActive
                            ? "bg-white text-black"
                            : "text-neutral-400 hover:bg-neutral-900 hover:text-white"
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
            <div className="flex items-center gap-2">
              <LibraryOrganizeRootButton rootVideos={rootVideos} />
              <LibraryRefreshButton />
            </div>
          </div>
        </header>

        {visibleMovies.length === 0 ? (
          <div className="py-24 text-center space-y-4">
            <p className="text-neutral-500 font-serif italic text-xl">{t("empty")}</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5 gap-x-5 xl:gap-x-6 gap-y-12 xl:gap-y-14">
            {sortedMovies.map((movie, i) => (
              <LibraryMovieCard key={movie.id} movie={movie} priority={i === 0} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
