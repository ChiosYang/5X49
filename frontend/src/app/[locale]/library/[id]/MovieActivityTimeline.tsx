"use client";

import { useEffect } from "react";
import { Activity, AlertCircle, CheckCircle2, Clock, Image, Loader2, Search, Sparkles, Video, X } from "lucide-react";
import { useMovieAuditEvents } from "@/hooks/useMovie";
import type { EventRecord } from "@/types/movie";

const EVENT_LABELS: Record<string, string> = {
  MovieDiscovered: "Discovered",
  MovieFileObserved: "File observed",
  MovieFolderScanned: "Folder scanned",
  MovieMetadataParsedFromNfo: "NFO parsed",
  MovieMarkedMissing: "Marked missing",
  MovieRestored: "Restored",
  MovieIgnored: "Ignored",
  MetadataMatchSuggested: "Match suggested",
  MetadataMatched: "Metadata matched",
  MetadataScrapeFailed: "Scrape failed",
  ArtworkSelected: "Artwork selected",
  RootVideoOrganized: "Root video organized",
  RootVideoOrganizationNeedsReview: "Needs review",
  AnalysisStarted: "Analysis started",
  AnalysisCompleted: "Analysis completed",
  AnalysisFailed: "Analysis failed",
  ExternalScoresRefreshed: "Scores refreshed",
  ExternalScoresRefreshFailed: "Scores failed",
};

function eventIcon(type: string) {
  if (type.includes("Failed") || type.includes("Missing")) return AlertCircle;
  if (type.includes("Analysis")) return Sparkles;
  if (type.includes("Artwork")) return Image;
  if (type.includes("Metadata") || type.includes("Match")) return Search;
  if (type.includes("Video") || type.includes("File") || type.includes("Folder") || type.includes("Discovered")) return Video;
  if (type.includes("Completed") || type.includes("Refreshed") || type.includes("Restored")) return CheckCircle2;
  return Activity;
}

function formatEventTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function stringPayload(event: EventRecord, key: string) {
  const value = event.payload?.[key];
  return typeof value === "string" && value.trim() ? value : null;
}

function numberPayload(event: EventRecord, key: string) {
  const value = event.payload?.[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function eventSummary(event: EventRecord) {
  const reason = stringPayload(event, "reason");
  const message = stringPayload(event, "message");
  const title = stringPayload(event, "title");
  const sourcePath = stringPayload(event, "source_path");
  const targetPath = stringPayload(event, "target_path");
  const folderPath = stringPayload(event, "folder_path");
  const mediaPath = stringPayload(event, "media_path");
  const tmdbId = numberPayload(event, "tmdb_id") ?? stringPayload(event, "tmdb_id");
  const confidence = numberPayload(event, "confidence") ?? numberPayload(event, "score");

  if (event.type === "MetadataMatched") {
    return [
      title,
      tmdbId ? `TMDB ${tmdbId}` : null,
      confidence !== null ? `${Math.round(confidence)}% confidence` : null,
    ].filter(Boolean).join(" · ");
  }
  if (event.type === "MetadataMatchSuggested") return reason || "Review required before writing metadata";
  if (event.type === "ArtworkSelected") return "Poster or backdrop was updated";
  if (event.type === "RootVideoOrganized") return targetPath || sourcePath || "Root video moved into the library";
  if (event.type === "MovieFileObserved") {
    const changedFields = event.payload?.changed_fields;
    return Array.isArray(changedFields) && changedFields.length
      ? `Changed ${changedFields.join(", ")}`
      : mediaPath || "Local file details changed";
  }
  if (event.type === "MovieFolderScanned") return folderPath || mediaPath || "Local folder was scanned";
  if (event.type === "MovieMetadataParsedFromNfo") {
    const changedFields = event.payload?.changed_fields;
    return Array.isArray(changedFields) && changedFields.length
      ? `NFO changed ${changedFields.join(", ")}`
      : "NFO metadata was parsed";
  }
  if (event.type === "MovieDiscovered") return mediaPath || title || "New library record created";
  if (event.type === "AnalysisCompleted") return stringPayload(event, "micro_genre") || "Genealogy analysis is ready";
  if (event.type === "ExternalScoresRefreshed") {
    const sources = event.payload?.updated_sources;
    return Array.isArray(sources) && sources.length ? `Updated ${sources.join(", ")}` : "External scores updated";
  }
  return message || reason || title || event.aggregate_id || "Event recorded";
}

interface MovieActivityTimelineProps {
  movieId: string;
  open: boolean;
  onClose: () => void;
}

export default function MovieActivityTimeline({ movieId, open, onClose }: MovieActivityTimelineProps) {
  const { data: events = [], isLoading, error } = useMovieAuditEvents(movieId, open);
  const visibleEvents = events.slice(0, 8);

  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose, open]);

  if (!open) {
    return null;
  }

  return (
    <div className="fixed inset-0 z-[70] flex items-end justify-center bg-black/75 px-4 py-6 backdrop-blur-sm sm:items-center">
      <button
        type="button"
        className="absolute inset-0 cursor-default"
        onClick={onClose}
        aria-label="Close library history"
      />
      <section
        className="relative z-10 max-h-[min(42rem,calc(100vh-3rem))] w-full max-w-2xl overflow-hidden border border-neutral-800 bg-black text-white shadow-2xl shadow-black/70"
        role="dialog"
        aria-modal="true"
        aria-labelledby="movie-activity-title"
      >
        <div className="flex items-start justify-between gap-6 border-b border-neutral-800 px-5 py-5 sm:px-6">
          <div className="min-w-0">
            <span className="block text-xs font-bold uppercase tracking-widest text-neutral-500">
              Activity
            </span>
            <h2 id="movie-activity-title" className="mt-2 text-2xl font-bold uppercase text-white">
              Library history
            </h2>
          </div>
          <div className="flex shrink-0 items-center gap-3">
            {isLoading && <Loader2 className="h-5 w-5 animate-spin text-neutral-500" />}
            <button
              type="button"
              onClick={onClose}
              className="flex h-10 w-10 items-center justify-center border border-neutral-800 bg-neutral-950 text-neutral-300 transition-colors hover:border-neutral-500 hover:text-white"
              aria-label="Close library history"
              title="Close library history"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        <div className="max-h-[calc(min(42rem,100vh-3rem)-6.75rem)] overflow-y-auto px-5 py-6 sm:px-6">
          {error ? (
            <div className="border border-neutral-800 bg-neutral-950 px-4 py-4 text-sm text-neutral-400">
              Activity could not be loaded.
            </div>
          ) : visibleEvents.length === 0 ? (
            <div className="border border-neutral-800 bg-neutral-950 px-4 py-4 text-sm text-neutral-500">
              No activity recorded yet.
            </div>
          ) : (
            <ol className="relative space-y-5 border-l border-neutral-800 pl-6">
              {visibleEvents.map((event) => {
                const Icon = eventIcon(event.type);
                return (
                  <li key={event.id} className="relative min-w-0">
                    <span className="absolute -left-[2.05rem] flex h-8 w-8 items-center justify-center border border-neutral-800 bg-black text-neutral-400">
                      <Icon className="h-4 w-4" />
                    </span>
                    <div className="grid gap-1 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-start">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-bold uppercase tracking-widest text-white">
                          {EVENT_LABELS[event.type] || event.type}
                        </p>
                        <p className="mt-1 break-words text-sm leading-relaxed text-neutral-400">
                          {eventSummary(event)}
                        </p>
                      </div>
                      <time className="flex items-center gap-1.5 text-xs uppercase tracking-widest text-neutral-600">
                        <Clock className="h-3 w-3" />
                        {formatEventTime(event.occurred_at)}
                      </time>
                    </div>
                  </li>
                );
              })}
            </ol>
          )}
        </div>
      </section>
    </div>
  );
}
