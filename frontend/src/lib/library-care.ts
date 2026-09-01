import type {
  LibraryFilmSummary,
  MissingLibraryItemSummary,
  OrganizationCandidate,
} from "@/types/movie";

export type LibraryView = "all" | "metadata" | "inbox" | "offline";
export type LibrarySortKey = "title" | "added" | "duration";
export type LibrarySortDirection = "asc" | "desc";
export type LibraryFilterKey = "all" | "watched" | "unwatched" | "favorite";

export interface LibraryQueryState {
  view: LibraryView;
  sort: LibrarySortKey;
  direction: LibrarySortDirection;
  filter: LibraryFilterKey;
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
  return `/library?${params.toString()}`;
}

export function buildLibraryCareState({
  films,
  organizationCandidates,
  missingItems,
  activeView,
  organizationUnavailable = false,
  missingUnavailable = false,
}: {
  films: LibraryFilmSummary[];
  organizationCandidates: OrganizationCandidate[];
  missingItems: MissingLibraryItemSummary[];
  activeView: LibraryView;
  organizationUnavailable?: boolean;
  missingUnavailable?: boolean;
}): LibraryCareState {
  const metadataReviews = films.filter(
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
