// API Configuration - Centralized endpoint management
// Use NEXT_PUBLIC_API_URL environment variable in production

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export const API = {
    baseUrl: API_BASE_URL,

    // Endpoints
    analyze: (movieName: string) => `${API_BASE_URL}/analyze/${encodeURIComponent(movieName)}`,
    library: () => `${API_BASE_URL}/library`,
    libraryMovie: (id: string) => `${API_BASE_URL}/library/${encodeURIComponent(id)}`,
    librarySeed: () => `${API_BASE_URL}/library/seed`,
};

export default API;
