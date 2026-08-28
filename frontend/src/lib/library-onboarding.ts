import type { MediaDirectoryStatus } from "@/hooks/useSettings";

export type LibraryEmptyState = "onboarding" | "filtered-empty" | "content";

export const FIRST_RUN_INTRO_SESSION_KEY = "5x49:first-run-intro-seen:v1";

export function shouldPlayFirstRunIntro({
  hasPlayed,
  reducedMotion,
}: {
  hasPlayed: boolean;
  reducedMotion: boolean;
}) {
  return !hasPlayed && !reducedMotion;
}

export function getLibraryEmptyState(totalFilms: number, filteredFilms: number): LibraryEmptyState {
  if (totalFilms === 0) return "onboarding";
  if (filteredFilms === 0) return "filtered-empty";
  return "content";
}

export function isMediaDirectoryReady(status?: MediaDirectoryStatus | null) {
  return Boolean(status?.exists && status.readable);
}

export type FirstScanState = "idle" | "queueing" | "queued" | "running" | "success" | "empty" | "error";

export interface FirstScanStatusInput {
  requested: boolean;
  queueing: boolean;
  syncState?: string;
  lastFinishedAt?: string | null;
  baselineFinishedAt?: string | null;
  lastError?: string | null;
  scanned?: number;
}

export function getFirstScanState({
  requested,
  queueing,
  syncState,
  lastFinishedAt,
  baselineFinishedAt,
  lastError,
  scanned,
}: FirstScanStatusInput): FirstScanState {
  if (!requested) return "idle";
  if (queueing) return "queueing";
  if (syncState === "running") return "running";

  const finished = Boolean(lastFinishedAt && lastFinishedAt !== baselineFinishedAt);
  if (!finished) return "queued";
  if (syncState === "error" || lastError) return "error";
  return (scanned ?? 0) > 0 ? "success" : "empty";
}
