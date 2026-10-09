export const FILM_PAGE_SIZE = 40;

export function normalizeFilmPage(value?: string | string[]) {
  const input = Array.isArray(value) ? value[0] : value;
  return input && /^[1-9][0-9]*$/.test(input) ? Math.min(Number(input), 25_001) : 1;
}

export function filmPageHref(href: string, page: number) {
  const [path, search] = href.split("?");
  const params = new URLSearchParams(search);
  if (page > 1) params.set("page", String(page)); else params.delete("page");
  return `${path}${params.size ? `?${params}` : ""}`;
}
