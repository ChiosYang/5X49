const API_BASE_URL = "/api";

const segment = (value: string) => encodeURIComponent(value);
const mediaPath = (path: string) => {
  const normalized = path.startsWith("/") ? path : `/${path}`;
  return normalized.split("/").map(segment).join("/");
};

export const API = {
  baseUrl: API_BASE_URL,

  workflows: () => `${API_BASE_URL}/workflows`,
  workflow: (id: string) => `${API_BASE_URL}/workflows/${segment(id)}`,
  workflowCancel: (id: string) => `${API_BASE_URL}/workflows/${segment(id)}/cancel`,
  workflowRetry: (id: string) => `${API_BASE_URL}/workflows/${segment(id)}/retry`,

  mediaUrl: (path: string) => `${API_BASE_URL}${mediaPath(path)}`,
  providerArtworkUrl: (path: string) => path.startsWith("http://") || path.startsWith("https://")
    ? path
    : `https://image.tmdb.org/t/p/original${path.startsWith("/") ? path : `/${path}`}`,
  metadataSearch: () => `${API_BASE_URL}/metadata/search`,
  metadataMovie: (tmdbId: number) => `${API_BASE_URL}/metadata/movie/${tmdbId}`,

  libraryFilms: () => `${API_BASE_URL}/library/films`,
  libraryFilm: (filmId: string) => `${API_BASE_URL}/library/films/${segment(filmId)}`,
  filmProfileState: (filmId: string) => `${API_BASE_URL}/films/${segment(filmId)}/profile-state`,
  filmAnalysis: (filmId: string) => `${API_BASE_URL}/films/${segment(filmId)}/analysis`,
  filmGraph: (filmId: string) => `${API_BASE_URL}/films/${segment(filmId)}/graph`,
  filmAnalysisRuns: (filmId: string) => `${API_BASE_URL}/films/${segment(filmId)}/analysis-runs`,
  filmArtwork: (filmId: string) => `${API_BASE_URL}/films/${segment(filmId)}/artwork`,
  filmExternalScores: (filmId: string) => `${API_BASE_URL}/films/${segment(filmId)}/external-scores/refresh`,
  filmScrape: (filmId: string) => `${API_BASE_URL}/films/${segment(filmId)}/scrape`,
  filmScrapeCandidates: (filmId: string) => `${API_BASE_URL}/films/${segment(filmId)}/scrape/candidates`,
  filmScrapeConfirm: (filmId: string) => `${API_BASE_URL}/films/${segment(filmId)}/scrape/confirm`,
  libraryItemRefresh: (itemId: string) => `${API_BASE_URL}/library/items/${segment(itemId)}/refresh`,
  libraryItemIgnore: (itemId: string) => `${API_BASE_URL}/library/items/${segment(itemId)}/ignore`,
  watchHistory: () => `${API_BASE_URL}/profile/watch-history`,
  activityEvents: (params: {
    aggregate_type?: string;
    aggregate_id?: string;
    type?: string;
    command_id?: string;
    correlation_id?: string;
    limit?: number;
  } = {}) => {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") query.set(key, String(value));
    });
    return `${API_BASE_URL}/activity/events${query.size ? `?${query}` : ""}`;
  },
  operationPreview: (snapshotId: string) => `${API_BASE_URL}/operations/${segment(snapshotId)}/preview`,
  operationRestore: (snapshotId: string) => `${API_BASE_URL}/operations/${segment(snapshotId)}/restore`,

  libraryExternalScoresBatch: () => `${API_BASE_URL}/library/external-scores/refresh`,
  libraryExternalScoresStatus: () => `${API_BASE_URL}/library/external-scores/status`,
  libraryScrapeBatch: () => `${API_BASE_URL}/library/scrape`,
  libraryScrapeStatus: () => `${API_BASE_URL}/library/scrape/status`,
  libraryOrganizeRoot: () => `${API_BASE_URL}/library/organize-root`,
  libraryOrganizeRootConfirm: () => `${API_BASE_URL}/library/organize-root/confirm`,
  libraryOrganizeStatus: () => `${API_BASE_URL}/library/organize/status`,
  libraryRootVideos: () => `${API_BASE_URL}/library/root-videos`,
  libraryReconcile: () => `${API_BASE_URL}/library/reconcile`,
  libraryCleanupMissing: () => `${API_BASE_URL}/library/missing`,
  librarySyncStatus: () => `${API_BASE_URL}/library/sync/status`,
  librarySeed: () => `${API_BASE_URL}/library/seed`,
  libraryClear: () => `${API_BASE_URL}/library/data`,

  settingsModel: () => `${API_BASE_URL}/settings/model`,
  settingsBaseUrl: () => `${API_BASE_URL}/settings/base-url`,
  settingsMediaDir: () => `${API_BASE_URL}/settings/media-dir`,
  settingsLanguage: () => `${API_BASE_URL}/settings/language`,
  settingsArtworkLanguage: () => `${API_BASE_URL}/settings/artwork-language`,
  settingsLibraryWatch: () => `${API_BASE_URL}/settings/library-watch`,
  settingsAutoOrganizeRoot: () => `${API_BASE_URL}/settings/auto-organize-root`,
  settingsScrapeConfirmation: () => `${API_BASE_URL}/settings/scrape-confirmation`,
  settingsTmdb: () => `${API_BASE_URL}/settings/tmdb`,
  settingsTmdbTest: () => `${API_BASE_URL}/settings/tmdb/test`,
  settingsTestApiKey: () => `${API_BASE_URL}/settings/test-api-key`,
  settingsModelsRefresh: () => `${API_BASE_URL}/settings/models/refresh`,
  systemListDirs: () => `${API_BASE_URL}/sys/list-dirs`,
  systemScanLibrary: () => `${API_BASE_URL}/sys/scan-library`,
};

export default API;
