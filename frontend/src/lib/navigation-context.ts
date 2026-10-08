export const RETURN_CONTEXT_KEY = "5x49:return-context:v1";
export interface ReturnContext { href: string; filmId: string; scrollY: number; savedAt: number; focusId?: string }
export function safeReturnHref(value: unknown): string | null {
  if (typeof value !== "string" || value.length > 2000 || /[\\\r\n]/.test(value)) return null;
  if (!/^\/(?:en\/|zh\/)?(?:library|search|explore|diary|ask)(?:\?|$)/.test(value)) return null;
  return value;
}
export function parseReturnContext(value: string | null, now = Date.now()): ReturnContext | null {
  try {
    const data = JSON.parse(value || "null");
    if (!data || !safeReturnHref(data.href) || !/^film_[a-f0-9]{32}$/.test(data.filmId)
      || !Number.isFinite(data.scrollY) || data.scrollY < 0 || !Number.isFinite(data.savedAt)
      || now - data.savedAt > 30 * 60_000 || data.savedAt > now) return null;
    return { href: data.href, filmId: data.filmId, scrollY: data.scrollY, savedAt: data.savedAt,
      ...(typeof data.focusId === "string" && /^viewing-link-view_[a-f0-9]{32}$/.test(data.focusId) ? { focusId: data.focusId } : {}) };
  } catch { return null; }
}
export function rememberFilmReturn(filmId: string, focusId?: string) {
  const href = `${window.location.pathname}${window.location.search}`;
  if (!safeReturnHref(href)) return;
  try { sessionStorage.setItem(RETURN_CONTEXT_KEY, JSON.stringify({ href, filmId, ...(focusId ? { focusId } : {}), scrollY: window.scrollY, savedAt: Date.now() })); } catch { /* Storage can be unavailable. */ }
}
export function readFilmReturn() {
  try { return parseReturnContext(sessionStorage.getItem(RETURN_CONTEXT_KEY)); } catch { return null; }
}
