// API Configuration - Centralized endpoint management
// Use relative path '/api' which will be rewritten by Next.js to the backend dynamically

const API_BASE_URL = '/api';

export const API = {
    baseUrl: API_BASE_URL,

    // === Media / Static Resources ===
    mediaUrl: (path: string) => `${API_BASE_URL}${path}`,

    // === Library ===
    library: () => `${API_BASE_URL}/library`,
    libraryMovie: (id: string) => `${API_BASE_URL}/library/${encodeURIComponent(id)}`,
    libraryAnalyze: (id: string) => `${API_BASE_URL}/library/analyze/${encodeURIComponent(id)}`,
    librarySeed: () => `${API_BASE_URL}/library/seed`,
    libraryClear: () => `${API_BASE_URL}/library/clear`,

    // === Settings ===
    settingsModel: () => `${API_BASE_URL}/settings/model`,
    settingsBaseUrl: () => `${API_BASE_URL}/settings/base-url`,
    settingsMediaDir: () => `${API_BASE_URL}/settings/media-dir`,
    settingsLanguage: () => `${API_BASE_URL}/settings/language`,

    // System
    systemListDirs: () => `${API_BASE_URL}/sys/list-dirs`,
    systemScanLibrary: () => `${API_BASE_URL}/sys/scan-library`,
    settingsTestApiKey: () => `${API_BASE_URL}/settings/test-api-key`,
    settingsModelsRefresh: () => `${API_BASE_URL}/settings/models/refresh`,

    // === Analysis ===
    analyze: (name: string) => `${API_BASE_URL}/analyze/${encodeURIComponent(name)}`,
};

export default API;
