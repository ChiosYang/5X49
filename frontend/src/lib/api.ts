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

    // === Media / Static Resources ===
    mediaUrl: (path: string) => `${API_BASE_URL}${encodeMediaPath(path)}`,

    // === Metadata ===
    metadataSearch: () => `${API_BASE_URL}/metadata/search`,

    // === Library ===
    library: () => `${API_BASE_URL}/library`,
    libraryMovie: (id: string) => `${API_BASE_URL}/library/${encodeURIComponent(id)}`,
    libraryAnalyze: (id: string) => `${API_BASE_URL}/library/analyze/${encodeURIComponent(id)}`,
    libraryRefresh: (id: string) => `${API_BASE_URL}/library/${encodeURIComponent(id)}/refresh`,
    libraryScrape: (id: string) => `${API_BASE_URL}/library/${encodeURIComponent(id)}/scrape`,
    libraryScrapeConfirm: (id: string) => `${API_BASE_URL}/library/${encodeURIComponent(id)}/scrape/confirm`,
    libraryIgnore: (id: string) => `${API_BASE_URL}/library/${encodeURIComponent(id)}/ignore`,
    libraryScrapeBatch: () => `${API_BASE_URL}/library/scrape`,
    libraryScrapeStatus: () => `${API_BASE_URL}/library/scrape/status`,
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
    settingsLibraryWatch: () => `${API_BASE_URL}/settings/library-watch`,

    // System
    systemListDirs: () => `${API_BASE_URL}/sys/list-dirs`,
    systemScanLibrary: () => `${API_BASE_URL}/sys/scan-library`,
    settingsTestApiKey: () => `${API_BASE_URL}/settings/test-api-key`,
    settingsModelsRefresh: () => `${API_BASE_URL}/settings/models/refresh`,

    // === Analysis ===
    analyze: (name: string) => `${API_BASE_URL}/analyze/${encodeURIComponent(name)}`,
};

export default API;
