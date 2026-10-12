import type {
  LibraryFilmSummary,
  MissingLibraryItemSummary,
  OrganizationCandidate,
} from "@/types/movie";
import type { LibraryRanges } from "./library-filters.ts";

export type LibraryView = "all" | "metadata" | "inbox" | "offline";
export type LibrarySortKey = "title" | "added" | "duration";
export type LibrarySortDirection = "asc" | "desc";
export type LibraryFilterKey = "all" | "watched" | "unwatched" | "favorite";

export interface LibraryQueryState extends LibraryRanges {
  view: LibraryView;
  sort: LibrarySortKey;
  direction: LibrarySortDirection;
  filter: LibraryFilterKey;
  page?: number;
  query?: string;
  favorite?: boolean;
}

export interface LibraryCareState {
  metadataReviews: number;
  actionableInbox: number;
  waitingInbox: number;
  offline: number;
  totalActionable: number;
  recommendedView: Exclude<LibraryView, "all"> | null;
  visibleViews: LibraryView[];
  partialUnavailable: boolean;
  showStatus: boolean;
}

export function normalizeLibraryView(value?: string): LibraryView {
  return value === "metadata" || value === "inbox" || value === "offline"
    ? value
    : "all";
}

export function buildLibraryHref(state: LibraryQueryState, nextView = state.view) {
  const params = new URLSearchParams();
  if (nextView !== "all") params.set("view", nextView);
  params.set("sort", state.sort);
  params.set("dir", state.direction);
  if (state.filter !== "all") params.set("filter", state.filter);
  appendLibraryFilters(params, state);
  if (nextView === state.view && (state.page || 1) > 1) params.set("page", String(state.page));
  return `/library?${params.toString()}`;
}

export function appendLibraryFilters(params: URLSearchParams, state: LibraryQueryState) {
  if (state.query) params.set("q", state.query);
  if (state.favorite) params.set("favorite", "true");
  for (const field of ["duration_min", "duration_max", "rating_min", "rating_max", "year_min", "year_max"] as const) {
    if (state[field]) params.set(field, state[field]);
  }
  return params;
}

export function buildLibraryCareState({
  films,
  organizationCandidates,
  missingItems,
  activeView,
  organizationUnavailable = false,
  missingUnavailable = false,
  metadataReviewCount,
}: {
  films: LibraryFilmSummary[];
  organizationCandidates: OrganizationCandidate[];
  missingItems: MissingLibraryItemSummary[];
  activeView: LibraryView;
  organizationUnavailable?: boolean;
  missingUnavailable?: boolean;
  metadataReviewCount?: number;
}): LibraryCareState {
  const metadataReviews = metadataReviewCount ?? films.filter(
    (film) => film.primary_item.metadata.scrape_status === "needs_review",
  ).length;
  const actionableInbox = organizationCandidates.filter((item) => item.stable).length;
  const waitingInbox = organizationCandidates.length - actionableInbox;
  const offline = missingItems.length;
  const totalActionable = metadataReviews + actionableInbox + offline;
  const recommendedView = metadataReviews > 0
    ? "metadata"
    : actionableInbox > 0
      ? "inbox"
      : offline > 0
        ? "offline"
        : null;
  const hasCareNavigation = activeView !== "all"
    || metadataReviews > 0
    || organizationCandidates.length > 0
    || offline > 0;
  const visibleViews: LibraryView[] = hasCareNavigation ? ["all"] : [];

  if (metadataReviews > 0 || activeView === "metadata") visibleViews.push("metadata");
  if (organizationCandidates.length > 0 || activeView === "inbox") visibleViews.push("inbox");
  if (offline > 0 || activeView === "offline") visibleViews.push("offline");

  const partialUnavailable = organizationUnavailable || missingUnavailable;
  return {
    metadataReviews,
    actionableInbox,
    waitingInbox,
    offline,
    totalActionable,
    recommendedView,
    visibleViews,
    partialUnavailable,
    showStatus: activeView !== "all"
      || totalActionable > 0
      || waitingInbox > 0
      || partialUnavailable,
  };
}
