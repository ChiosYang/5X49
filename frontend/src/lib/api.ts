// API Configuration - Centralized endpoint management
// Use relative path '/api' which will be rewritten by Next.js to the backend dynamically

const API_BASE_URL = '/api';

const encodePathSegment = (segment: string) => {
    try {
        return encodeURIComponent(decodeURIComponent(segment));
    } catch {
        return encodeURIComponent(segment);
    }
};

const encodeMediaPath = (path: string) => {
    const normalizedPath = path.startsWith('/') ? path : `/${path}`;
    return normalizedPath.split('/').map(encodePathSegment).join('/');
};

export const API = {
    baseUrl: API_BASE_URL,

    // === Jobs ===
    jobs: () => `${API_BASE_URL}/jobs`,
    job: (id: string) => `${API_BASE_URL}/jobs/${encodeURIComponent(id)}`,
    jobCancel: (id: string) => `${API_BASE_URL}/jobs/${encodeURIComponent(id)}/cancel`,
    jobRetry: (id: string) => `${API_BASE_URL}/jobs/${encodeURIComponent(id)}/retry`,

    // === Media / Static Resources ===
    mediaUrl: (path: string) => `${API_BASE_URL}${encodeMediaPath(path)}`,

    // === Metadata ===
    metadataSearch: () => `${API_BASE_URL}/metadata/search`,
    metadataMovie: (tmdbId: number) => `${API_BASE_URL}/metadata/movie/${tmdbId}`,

    // === Library ===
    library: () => `${API_BASE_URL}/library`,
    libraryMovie: (id: string) => `${API_BASE_URL}/library/${encodeURIComponent(id)}`,
    libraryMovieAuditEvents: (id: string) => `${API_BASE_URL}/library/${encodeURIComponent(id)}/audit-events`,
    libraryMovieTimelineStateUrl: (id: string, params: {
        before_event_id?: string | null;
        at?: string | null;
    }) => {
        const searchParams = new URLSearchParams();
        if (params.before_event_id) searchParams.set('before_event_id', params.before_event_id);
        if (params.at) searchParams.set('at', params.at);
        const query = searchParams.toString();
        return `${API_BASE_URL}/library/${encodeURIComponent(id)}/timeline/state${query ? `?${query}` : ''}`;
    },
    libraryMovieTimelineRestorePreviewUrl: (id: string, params: {
        before_event_id?: string | null;
        at?: string | null;
    }) => {
        const searchParams = new URLSearchParams();
        if (params.before_event_id) searchParams.set('before_event_id', params.before_event_id);
        if (params.at) searchParams.set('at', params.at);
        const query = searchParams.toString();
        return `${API_BASE_URL}/library/${encodeURIComponent(id)}/timeline/restore-preview${query ? `?${query}` : ''}`;
    },
    libraryMovieTimelineRestore: (id: string) => `${API_BASE_URL}/library/${encodeURIComponent(id)}/timeline/restore`,
    libraryAuditEvents: () => `${API_BASE_URL}/library/audit-events`,
    libraryOperationDryRunUrl: (params: {
        command_id?: string | null;
        correlation_id?: string | null;
        limit?: number;
    }) => {
        const searchParams = new URLSearchParams();
        if (params.command_id) searchParams.set('command_id', params.command_id);
        if (params.correlation_id) searchParams.set('correlation_id', params.correlation_id);
        if (params.limit) searchParams.set('limit', String(params.limit));
        const query = searchParams.toString();
        return `${API_BASE_URL}/library/operations/dry-run${query ? `?${query}` : ''}`;
    },
    libraryOperationRestore: () => `${API_BASE_URL}/library/operations/restore`,
    libraryMovieProjectionRebuildUrl: (params: {
        dry_run?: boolean;
        movie_id?: string | null;
        limit?: number;
        since?: string | null;
        base?: "current" | "empty" | string;
        confirmation_token?: string | null;
    } = {}) => {
        const searchParams = new URLSearchParams();
        searchParams.set('dry_run', String(params.dry_run ?? true));
        if (params.movie_id) searchParams.set('movie_id', params.movie_id);
        if (params.limit) searchParams.set('limit', String(params.limit));
        if (params.since) searchParams.set('since', params.since);
        if (params.base) searchParams.set('base', params.base);
        if (params.confirmation_token) searchParams.set('confirmation_token', params.confirmation_token);
        return `${API_BASE_URL}/library/projections/movie/rebuild?${searchParams.toString()}`;
    },
    libraryMovieReplayBackfillUrl: (params: {
        dry_run?: boolean;
        movie_id?: string | null;
        sample_limit?: number;
    } = {}) => {
        const searchParams = new URLSearchParams();
        searchParams.set('dry_run', String(params.dry_run ?? true));
        if (params.movie_id) searchParams.set('movie_id', params.movie_id);
        if (params.sample_limit !== undefined) searchParams.set('sample_limit', String(params.sample_limit));
        return `${API_BASE_URL}/library/events/backfill/movie-replay?${searchParams.toString()}`;
    },
    libraryAuditEventsUrl: (params: {
        aggregate_type?: string;
        aggregate_id?: string;
        type?: string;
        command_id?: string;
        correlation_id?: string;
        limit?: number;
    } = {}) => {
        const searchParams = new URLSearchParams();
        if (params.aggregate_type) searchParams.set('aggregate_type', params.aggregate_type);
        if (params.aggregate_id) searchParams.set('aggregate_id', params.aggregate_id);
        if (params.type) searchParams.set('type', params.type);
        if (params.command_id) searchParams.set('command_id', params.command_id);
        if (params.correlation_id) searchParams.set('correlation_id', params.correlation_id);
        if (params.limit) searchParams.set('limit', String(params.limit));
        const query = searchParams.toString();
        return `${API_BASE_URL}/library/audit-events${query ? `?${query}` : ''}`;
    },
    libraryAnalyze: (id: string) => `${API_BASE_URL}/library/analyze/${encodeURIComponent(id)}`,
    libraryRefresh: (id: string) => `${API_BASE_URL}/library/${encodeURIComponent(id)}/refresh`,
    libraryArtwork: (id: string) => `${API_BASE_URL}/library/${encodeURIComponent(id)}/artwork`,
    libraryExternalScores: (id: string) => `${API_BASE_URL}/library/${encodeURIComponent(id)}/external-scores/refresh`,
    libraryExternalScoresBatch: () => `${API_BASE_URL}/library/external-scores/refresh`,
    libraryExternalScoresStatus: () => `${API_BASE_URL}/library/external-scores/status`,
    libraryScrape: (id: string) => `${API_BASE_URL}/library/${encodeURIComponent(id)}/scrape`,
    libraryScrapeConfirm: (id: string) => `${API_BASE_URL}/library/${encodeURIComponent(id)}/scrape/confirm`,
    libraryIgnore: (id: string) => `${API_BASE_URL}/library/${encodeURIComponent(id)}/ignore`,
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
    libraryClear: () => `${API_BASE_URL}/library/clear`,

    // === Settings ===
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

    // System
    systemListDirs: () => `${API_BASE_URL}/sys/list-dirs`,
    systemScanLibrary: () => `${API_BASE_URL}/sys/scan-library`,
    settingsTestApiKey: () => `${API_BASE_URL}/settings/test-api-key`,
    settingsModelsRefresh: () => `${API_BASE_URL}/settings/models/refresh`,

    // === Analysis ===
    analyze: (name: string) => `${API_BASE_URL}/analyze/${encodeURIComponent(name)}`,
};

export default API;
