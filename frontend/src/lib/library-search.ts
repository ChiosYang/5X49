export function normalizeLibrarySearch(value?: string | string[]) {
  return (Array.isArray(value) ? value[0] : value)?.trim().slice(0, 200) ?? "";
}

// Global searches start from the whole collection; only legacy links retain a page.
export function librarySearchHref(value?: string | string[], page = 1) {
  const query = normalizeLibrarySearch(value);
  const params = new URLSearchParams();
  if (query) params.set("q", query);
  if (query && page > 1) params.set("page", String(page));
  return `/library${params.size ? `?${params}` : ""}`;
}
