import "server-only";

import type { MovieDetail } from "@/types/movie";

const getBackendUrl = () => {
  if (process.env.NODE_ENV === "development") {
    return "http://127.0.0.1:8000";
  }

  return process.env.BACKEND_URL || "http://backend:8000";
};

export async function getLibraryMovie(id: string): Promise<MovieDetail | null> {
  const res = await fetch(`${getBackendUrl()}/library/${encodeURIComponent(id)}`, {
    cache: "no-store",
  });

  if (res.status === 404) {
    return null;
  }

  if (!res.ok) {
    throw new Error(`Failed to fetch movie detail: ${res.status}`);
  }

  return res.json();
}
