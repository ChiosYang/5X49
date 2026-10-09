export function metadataActionError(error: unknown, fallback: string, noMatches: string): string {
  if (!(error instanceof Error) || !error.message) return fallback;
  return error.message === "No TMDB matches found" ? noMatches : error.message;
}

/** A skip is local to one review pass; only successful confirmations reduce pending work. */
export function reviewSession<T extends { id: string }>(
  films: readonly T[],
  skippedIds: readonly string[],
  confirmedIds: readonly string[],
) {
  const confirmed = new Set(confirmedIds);
  const skipped = new Set(skippedIds);
  const pending = films.filter((film) => !confirmed.has(film.id));
  return {
    pending,
    available: pending.filter((film) => !skipped.has(film.id)),
    skippedCount: pending.filter((film) => skipped.has(film.id)).length,
  };
}
