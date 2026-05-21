"use client";

import { useMemo, useState } from "react";
import useSWR from "swr";
import { Activity, AlertCircle, CheckCircle2, Clock, Filter, Image, Loader2, Search, Sparkles, Video } from "lucide-react";
import { Link } from "@/i18n/routing";
import { API } from "@/lib/api";
import type { EventRecord } from "@/types/movie";

const EVENT_LABELS: Record<string, string> = {
  MovieDiscovered: "Discovered",
  MovieFileObserved: "File observed",
  MovieFolderScanned: "Folder scanned",
  MovieMetadataParsedFromNfo: "Metadata file updated",
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
  LibraryReconciled: "Library reconciled",
  LibraryCleared: "Library cleared",
};

const EVENT_TYPE_OPTIONS = [
  "MovieDiscovered",
  "MovieFileObserved",
  "MovieMetadataParsedFromNfo",
  "MovieMarkedMissing",
  "MovieRestored",
  "MovieIgnored",
  "MetadataMatched",
  "ArtworkSelected",
  "AnalysisStarted",
  "AnalysisCompleted",
  "AnalysisFailed",
  "ExternalScoresRefreshed",
  "MovieFolderScanned",
];

const TECHNICAL_EVENT_TYPES = new Set([
  "MovieFolderScanned",
]);

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

function eventTitle(event: EventRecord) {
  return stringPayload(event, "title") || event.aggregate_id || "System event";
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
      ? `NFO signature changed: ${changedFields.join(", ")}`
      : "NFO metadata file changed";
  }
  if (event.type === "MovieDiscovered") return mediaPath || title || "New library record created";
  if (event.type === "AnalysisCompleted") return stringPayload(event, "micro_genre") || "Genealogy analysis is ready";
  if (event.type === "ExternalScoresRefreshed") {
    const sources = event.payload?.updated_sources;
    return Array.isArray(sources) && sources.length ? `Updated ${sources.join(", ")}` : "External scores updated";
  }
  return message || reason || title || event.aggregate_id || "Event recorded";
}

export default function LibraryActivityClient() {
  const [aggregateType, setAggregateType] = useState("");
  const [eventType, setEventType] = useState("");
  const [movieId, setMovieId] = useState("");
  const [showTechnicalEvents, setShowTechnicalEvents] = useState(false);

  const queryMovieId = movieId.trim();
  const url = useMemo(() => API.libraryAuditEventsUrl({
    aggregate_type: aggregateType || undefined,
    aggregate_id: queryMovieId || undefined,
    type: eventType || undefined,
    limit: 100,
  }), [aggregateType, eventType, queryMovieId]);

  const { data: events = [], isLoading, error } = useSWR<EventRecord[]>(url, {
    refreshInterval: 5000,
  });

  const visibleEvents = showTechnicalEvents
    ? events
    : events.filter((event) => !TECHNICAL_EVENT_TYPES.has(event.type));
  const hiddenTechnicalCount = events.length - visibleEvents.length;

  return (
    <div className="space-y-8">
      <section className="grid gap-4 border-y border-neutral-900 py-5 md:grid-cols-[minmax(0,1fr)_auto] md:items-end">
        <div className="grid gap-3 sm:grid-cols-3">
          <label className="grid gap-2">
            <span className="text-xs font-bold uppercase tracking-widest text-neutral-500">Aggregate</span>
            <select
              value={aggregateType}
              onChange={(event) => setAggregateType(event.target.value)}
              className="h-11 border border-neutral-800 bg-black px-3 text-sm text-white outline-none transition-colors focus:border-neutral-500"
            >
              <option value="">All</option>
              <option value="movie">Movie</option>
              <option value="library">Library</option>
              <option value="file">File</option>
            </select>
          </label>
          <label className="grid gap-2">
            <span className="text-xs font-bold uppercase tracking-widest text-neutral-500">Event</span>
            <select
              value={eventType}
              onChange={(event) => setEventType(event.target.value)}
              className="h-11 border border-neutral-800 bg-black px-3 text-sm text-white outline-none transition-colors focus:border-neutral-500"
            >
              <option value="">All events</option>
              {EVENT_TYPE_OPTIONS.map((type) => (
                <option key={type} value={type}>{EVENT_LABELS[type] || type}</option>
              ))}
            </select>
          </label>
          <label className="grid gap-2">
            <span className="text-xs font-bold uppercase tracking-widest text-neutral-500">Movie ID</span>
            <input
              value={movieId}
              onChange={(event) => setMovieId(event.target.value)}
              placeholder="Optional aggregate id"
              className="h-11 border border-neutral-800 bg-black px-3 text-sm text-white outline-none transition-colors placeholder:text-neutral-700 focus:border-neutral-500"
            />
          </label>
        </div>
        <label className="flex w-fit cursor-pointer items-center gap-3 text-xs font-bold uppercase tracking-widest text-neutral-500 transition-colors hover:text-neutral-300">
          <input
            type="checkbox"
            checked={showTechnicalEvents}
            onChange={(event) => setShowTechnicalEvents(event.target.checked)}
            className="h-4 w-4 accent-white"
          />
          Show technical
          {!showTechnicalEvents && hiddenTechnicalCount > 0 ? (
            <span className="text-neutral-700">({hiddenTechnicalCount} hidden)</span>
          ) : null}
        </label>
      </section>

      <div className="flex items-center justify-between gap-4 text-xs font-bold uppercase tracking-widest text-neutral-600">
        <span className="inline-flex items-center gap-2">
          <Filter className="h-3.5 w-3.5" />
          {visibleEvents.length} visible / {events.length} loaded
        </span>
        {isLoading ? (
          <span className="inline-flex items-center gap-2 text-neutral-500">
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            Loading
          </span>
        ) : null}
      </div>

      {error ? (
        <div className="border border-neutral-800 bg-neutral-950 px-4 py-4 text-sm text-neutral-400">
          Activity could not be loaded.
        </div>
      ) : visibleEvents.length === 0 ? (
        <div className="border border-neutral-800 bg-neutral-950 px-4 py-4 text-sm text-neutral-500">
          {events.length > 0 && hiddenTechnicalCount === events.length
            ? "Only technical events are hidden."
            : "No activity recorded yet."}
        </div>
      ) : (
        <ol className="relative space-y-5 border-l border-neutral-800 pl-6">
          {visibleEvents.map((event) => {
            const Icon = eventIcon(event.type);
            const label = EVENT_LABELS[event.type] || event.type;
            return (
              <li key={event.id} className="relative min-w-0">
                <span className="absolute -left-[2.05rem] flex h-8 w-8 items-center justify-center border border-neutral-800 bg-black text-neutral-400">
                  <Icon className="h-4 w-4" />
                </span>
                <div className="grid gap-2 border-b border-neutral-900 pb-5 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-start">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-3">
                      <p className="text-sm font-bold uppercase tracking-widest text-white">
                        {label}
                      </p>
                      <span className="text-xs font-bold uppercase tracking-widest text-neutral-700">
                        {event.aggregate_type}
                      </span>
                    </div>
                    <p className="mt-2 break-words text-sm leading-relaxed text-neutral-400">
                      {eventSummary(event)}
                    </p>
                    <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs uppercase tracking-widest text-neutral-600">
                      {event.aggregate_type === "movie" && event.aggregate_id ? (
                        <Link href={`/library/${event.aggregate_id}`} className="text-neutral-400 hover:text-white">
                          {eventTitle(event)}
                        </Link>
                      ) : (
                        <span>{eventTitle(event)}</span>
                      )}
                      <span>{event.id}</span>
                    </div>
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
  );
}
