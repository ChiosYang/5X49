const LIBRARY_SCROLL_KEY = "5x49:library-scroll-position";
const MAX_RESTORE_AGE_MS = 30 * 60 * 1000;

interface SavedLibraryScrollPosition {
  href: string;
  scrollY: number;
  savedAt: number;
}

function currentHref() {
  return `${window.location.pathname}${window.location.search}`;
}

export function saveLibraryScrollPosition() {
  if (typeof window === "undefined") return;

  const position: SavedLibraryScrollPosition = {
    href: currentHref(),
    scrollY: window.scrollY,
    savedAt: Date.now(),
  };

  try {
    window.sessionStorage.setItem(LIBRARY_SCROLL_KEY, JSON.stringify(position));
  } catch {
    // Storage can be unavailable in strict browser privacy modes.
  }
}

export function takeLibraryScrollPosition() {
  if (typeof window === "undefined") return null;

  try {
    const raw = window.sessionStorage.getItem(LIBRARY_SCROLL_KEY);
    if (!raw) return null;

    window.sessionStorage.removeItem(LIBRARY_SCROLL_KEY);

    const position = JSON.parse(raw) as Partial<SavedLibraryScrollPosition>;
    if (
      position.href !== currentHref() ||
      typeof position.scrollY !== "number" ||
      typeof position.savedAt !== "number" ||
      Date.now() - position.savedAt > MAX_RESTORE_AGE_MS
    ) {
      return null;
    }

    return Math.max(0, position.scrollY);
  } catch {
    return null;
  }
}

export function restoreWindowScroll(scrollY: number) {
  if (typeof window === "undefined") return;

  window.scrollTo(0, scrollY);
  window.requestAnimationFrame(() => {
    window.scrollTo(0, scrollY);
    window.requestAnimationFrame(() => window.scrollTo(0, scrollY));
    window.setTimeout(() => window.scrollTo(0, scrollY), 150);
  });
}
