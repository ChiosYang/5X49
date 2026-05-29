const LIBRARY_RETURN_ANCHOR_KEY = "5x49:library-return-anchor";
const MAX_RESTORE_AGE_MS = 30 * 60 * 1000;

interface LibraryReturnAnchor {
  href: string;
  movieId: string;
  viewportTop: number;
  savedAt: number;
}

function currentHref() {
  return `${window.location.pathname}${window.location.search}`;
}

export function saveLibraryReturnAnchor(movieId: string, element: HTMLElement) {
  if (typeof window === "undefined") return;

  const anchor: LibraryReturnAnchor = {
    href: currentHref(),
    movieId,
    viewportTop: element.getBoundingClientRect().top,
    savedAt: Date.now(),
  };

  try {
    window.sessionStorage.setItem(LIBRARY_RETURN_ANCHOR_KEY, JSON.stringify(anchor));
  } catch {
    // Storage can be unavailable in strict browser privacy modes.
  }
}

export function getLibraryReturnAnchor() {
  if (typeof window === "undefined") return null;

  try {
    const raw = window.sessionStorage.getItem(LIBRARY_RETURN_ANCHOR_KEY);
    if (!raw) return null;

    const anchor = JSON.parse(raw) as Partial<LibraryReturnAnchor>;
    if (
      anchor.href !== currentHref() ||
      typeof anchor.movieId !== "string" ||
      typeof anchor.viewportTop !== "number" ||
      typeof anchor.savedAt !== "number" ||
      Date.now() - anchor.savedAt > MAX_RESTORE_AGE_MS
    ) {
      return null;
    }

    return anchor as LibraryReturnAnchor;
  } catch {
    return null;
  }
}

export function clearLibraryReturnAnchor() {
  if (typeof window === "undefined") return;

  try {
    window.sessionStorage.removeItem(LIBRARY_RETURN_ANCHOR_KEY);
  } catch {
    // Storage can be unavailable in strict browser privacy modes.
  }
}
