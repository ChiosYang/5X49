export function personalStateChanges(
  saved: { rating?: number | null; notes?: string | null },
  draft: { rating: number | null; notes: string },
) {
  const changes: { rating?: number | null; notes?: string | null } = {};
  if ((saved.rating ?? null) !== draft.rating) changes.rating = draft.rating;
  const notes = draft.notes.trim() ? draft.notes : null;
  if ((saved.notes ?? null) !== notes) changes.notes = notes;
  return changes;
}
