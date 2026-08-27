const FILM_RESOURCE_ID_PATTERN = /^film_[0-9a-f]{32}$/;

export function isFilmResourceId(value: unknown): value is string {
  return typeof value === "string" && FILM_RESOURCE_ID_PATTERN.test(value);
}
