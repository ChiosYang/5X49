import {
  Activity,
  AlertCircle,
  CheckCircle2,
  FileText,
  Image,
  Search,
  Sparkles,
  Video,
  type LucideIcon,
} from "lucide-react";
import type { EventRecord, LibraryMovie } from "@/types/movie";

export const EVENT_LABELS: Record<string, string> = {
  MovieDiscovered: "Discovered",
  MovieFileObserved: "File observed",
  MovieFolderScanned: "Folder scanned",
  MovieMetadataParsedFromNfo: "Metadata file updated",
  MovieMarkedMissing: "Marked missing",
  MovieRestored: "Restored",
  MovieIgnored: "Ignored",
  MovieStateBackfilled: "Migration snapshot",
  MetadataMatchSuggested: "Match suggested",
  MetadataMatched: "Metadata matched",
  MovieStateRestored: "Timeline state restored",
  MetadataRestored: "Metadata restored",
  MetadataScrapeFailed: "Scrape failed",
  ArtworkDownloaded: "Artwork downloaded",
  ArtworkSelected: "Artwork selected",
  ArtworkSelectionRestored: "Artwork selection restored",
  ArtworkRestored: "Artwork restored",
  MovieFileSnapshotBackfilled: "File snapshot",
  NfoWritten: "NFO written",
  NfoRestored: "NFO restored",
  RootVideoMoved: "Root video moved",
  RootVideoMoveReversed: "Root video move reversed",
  RootVideoOrganized: "Root video organized",
  RootVideoOrganizationReverted: "Organization reverted",
  RootVideoOrganizationNeedsReview: "Needs review",
  AnalysisStarted: "Analysis started",
  AnalysisCompleted: "Analysis completed",
  AnalysisFailed: "Analysis failed",
  ExternalScoresRefreshed: "Scores refreshed",
  ExternalScoresRefreshFailed: "Scores failed",
  LibraryReconciled: "Library reconciled",
  LibraryCleared: "Library cleared",
};

export const EVENT_TYPE_OPTIONS = [
  "MovieDiscovered",
  "MovieFileObserved",
  "MovieMetadataParsedFromNfo",
  "MovieMarkedMissing",
  "MovieRestored",
  "MovieIgnored",
  "MovieStateBackfilled",
  "MetadataMatchSuggested",
  "MetadataMatched",
  "MovieStateRestored",
  "MetadataRestored",
  "MetadataScrapeFailed",
  "ArtworkDownloaded",
  "ArtworkSelected",
  "ArtworkSelectionRestored",
  "ArtworkRestored",
  "MovieFileSnapshotBackfilled",
  "NfoWritten",
  "NfoRestored",
  "RootVideoMoved",
  "RootVideoMoveReversed",
  "RootVideoOrganized",
  "RootVideoOrganizationReverted",
  "RootVideoOrganizationNeedsReview",
  "AnalysisStarted",
  "AnalysisCompleted",
  "AnalysisFailed",
  "ExternalScoresRefreshed",
  "ExternalScoresRefreshFailed",
  "MovieFolderScanned",
];

export const TECHNICAL_EVENT_TYPES = new Set([
  "MovieFolderScanned",
  "MovieFileSnapshotBackfilled",
  "MovieProjectionRebuilt",
  "MovieStateBackfilled",
]);

export interface ActivityOperation {
  id: string;
  title: string;
  summary: string;
  primaryEvent: EventRecord;
  events: EventRecord[];
  eventCount: number;
  occurred_at: string;
  command_id?: string | null;
  correlation_id?: string | null;
}

export function eventIcon(type: string): LucideIcon {
  if (type.includes("Failed") || type.includes("Missing")) return AlertCircle;
  if (type.includes("Analysis")) return Sparkles;
  if (type.includes("Artwork")) return Image;
  if (type.includes("Nfo") || type.includes("NFO")) return FileText;
  if (type.includes("Metadata") || type.includes("Match")) return Search;
  if (type.includes("Video") || type.includes("File") || type.includes("Folder") || type.includes("Discovered")) return Video;
  if (type.includes("Completed") || type.includes("Refreshed") || type.includes("Restored")) return CheckCircle2;
  return Activity;
}

export function formatEventTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export function formatRelativeEventTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";

  const diffSeconds = Math.round((date.getTime() - Date.now()) / 1000);
  const absSeconds = Math.abs(diffSeconds);
  const units: Array<[Intl.RelativeTimeFormatUnit, number]> = [
    ["year", 60 * 60 * 24 * 365],
    ["month", 60 * 60 * 24 * 30],
    ["week", 60 * 60 * 24 * 7],
    ["day", 60 * 60 * 24],
    ["hour", 60 * 60],
    ["minute", 60],
  ];

  for (const [unit, seconds] of units) {
    if (absSeconds >= seconds) {
      return new Intl.RelativeTimeFormat(undefined, { numeric: "auto" }).format(
        Math.round(diffSeconds / seconds),
        unit,
      );
    }
  }

  return "just now";
}

export function stringPayload(event: EventRecord, key: string) {
  const value = event.payload?.[key];
  return typeof value === "string" && value.trim() ? value : null;
}

export function numberPayload(event: EventRecord, key: string) {
  const value = event.payload?.[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function eventTitle(event: EventRecord, movie?: LibraryMovie | null) {
  return movieTitle(movie, event);
}

export function eventSummary(event: EventRecord, isTechnical = false) {
  return isTechnical ? technicalEventSummary(event) : semanticEventAction(event);
}

export function eventActionName(event: EventRecord, isTechnical = false) {
  return isTechnical ? EVENT_LABELS[event.type] || event.type : semanticEventAction(event);
}

export function operationDisplayTitle(
  operation: ActivityOperation,
  movie?: LibraryMovie | null,
  isTechnical = false,
) {
  if (isTechnical) {
    return operation.title;
  }

  const movieName = movieTitle(movie, operation.primaryEvent);

  if (operation.events.some((event) => event.type === "MovieDiscovered" || event.type === "RootVideoOrganized")) {
    return `Added ${movieName}`;
  }
  if (operation.events.some((event) => event.type === "MetadataMatched" || event.type === "ArtworkSelected" || event.type === "ArtworkDownloaded" || event.type === "NfoWritten")) {
    return `Updated ${movieName}`;
  }
  if (operation.events.some((event) => event.type === "MovieStateRestored" || event.type === "MetadataRestored" || event.type === "ArtworkSelectionRestored" || event.type === "ArtworkRestored" || event.type === "NfoRestored")) {
    return `Restored ${movieName}`;
  }
  if (operation.events.some((event) => event.type === "RootVideoOrganizationReverted" || event.type === "RootVideoMoveReversed")) {
    return `Reverted ${movieName}`;
  }
  if (operation.events.some((event) => event.type === "AnalysisCompleted")) {
    return `Analyzed ${movieName}`;
  }
  if (operation.events.some((event) => event.type === "AnalysisFailed")) {
    return `Could not analyze ${movieName}`;
  }
  if (operation.events.some((event) => event.type === "ExternalScoresRefreshed")) {
    return `Refreshed scores for ${movieName}`;
  }
  if (operation.events.some((event) => event.type === "MovieMarkedMissing")) {
    return `Marked ${movieName} as missing`;
  }
  if (operation.events.some((event) => event.type === "MovieRestored")) {
    return `Restored ${movieName} to the library`;
  }
  if (operation.events.some((event) => event.type === "MovieIgnored")) {
    return `Ignored ${movieName}`;
  }

  return semanticEventAction(operation.primaryEvent);
}

export function operationDisplaySummary(operation: ActivityOperation, isTechnical = false) {
  if (isTechnical) {
    return operation.summary;
  }

  if (operation.events.some((event) => event.type === "MetadataMatched") && operation.events.some((event) => event.type === "ArtworkDownloaded" || event.type === "ArtworkSelected")) {
    return "Metadata and artwork were refreshed.";
  }
  if (operation.events.some((event) => event.type === "MetadataMatched")) {
    return "Movie metadata was matched and saved.";
  }
  if (operation.events.some((event) => event.type === "ArtworkDownloaded" || event.type === "ArtworkSelected")) {
    return "Poster or backdrop artwork was updated.";
  }
  if (operation.events.some((event) => event.type === "NfoWritten")) {
    return "Local metadata files were updated.";
  }
  if (operation.events.some((event) => event.type === "RootVideoOrganized")) {
    return "A video was organized into the movie library.";
  }
  if (operation.events.some((event) => event.type === "MovieDiscovered")) {
    return "A new movie was added to the library.";
  }
  if (operation.events.some((event) => event.type === "AnalysisCompleted")) {
    return "Genealogy analysis is ready.";
  }
  if (operation.events.some((event) => event.type === "ExternalScoresRefreshed")) {
    return "External ratings and rankings were updated.";
  }
  if (operation.events.some((event) => event.type.includes("Failed"))) {
    return "An activity could not be completed.";
  }

  return semanticEventAction(operation.primaryEvent);
}

export function movieTitle(movie?: LibraryMovie | null, event?: EventRecord | null) {
  const title = movie?.title_cn || movie?.title || titleFromEvent(event) || "This movie";
  const year = movie?.year || (event ? numberPayload(event, "year") : null);
  return year ? `${title} (${year})` : title;
}

function titleFromEvent(event?: EventRecord | null) {
  if (!event) return null;
  const title = stringPayload(event, "title") || stringPayload(event, "title_cn");
  if (title) return title;

  const current = event.payload?.current;
  if (current && typeof current === "object") {
    const record = current as Record<string, unknown>;
    const currentTitle = record.title_cn || record.title;
    return typeof currentTitle === "string" && currentTitle.trim() ? currentTitle : null;
  }

  const after = event.payload?.after;
  if (after && typeof after === "object") {
    const record = after as Record<string, unknown>;
    const afterTitle = record.title_cn || record.title;
    return typeof afterTitle === "string" && afterTitle.trim() ? afterTitle : null;
  }

  return null;
}

function semanticEventAction(event: EventRecord) {
  const assetType = stringPayload(event, "asset_type");
  const action = stringPayload(event, "action");

  if (event.type === "MetadataMatched") return "Updated movie metadata";
  if (event.type === "MetadataMatchSuggested") return "Found a possible metadata match";
  if (event.type === "MetadataScrapeFailed") return "Could not update metadata";
  if (event.type === "MetadataRestored") return "Restored previous metadata";
  if (event.type === "MovieStateRestored") return "Restored previous movie details";
  if (event.type === "MovieStateBackfilled") return "Prepared movie history for replay";
  if (event.type === "ArtworkDownloaded") return assetType === "backdrop" ? "Downloaded backdrop image" : "Downloaded poster image";
  if (event.type === "ArtworkSelected") return "Selected new artwork";
  if (event.type === "ArtworkSelectionRestored") return "Restored previous artwork selection";
  if (event.type === "ArtworkRestored") return assetType === "backdrop" ? "Restored backdrop image" : "Restored poster image";
  if (event.type === "MovieFileSnapshotBackfilled") return "Recorded current file state";
  if (event.type === "NfoWritten") return action === "update_artwork" ? "Updated NFO artwork references" : "Generated NFO file";
  if (event.type === "NfoRestored") return "Restored previous NFO file";
  if (event.type === "RootVideoMoved") return "Moved video into place";
  if (event.type === "RootVideoMoveReversed") return "Moved video back";
  if (event.type === "RootVideoOrganized") return "Organized video into the library";
  if (event.type === "RootVideoOrganizationReverted") return "Reverted video organization";
  if (event.type === "RootVideoOrganizationNeedsReview") return "Needs review before organizing";
  if (event.type === "MovieFileObserved") return "Updated local file details";
  if (event.type === "MovieFolderScanned") return "Scanned movie folder";
  if (event.type === "MovieMetadataParsedFromNfo") return "Read metadata from NFO";
  if (event.type === "MovieDiscovered") return "Added movie to the library";
  if (event.type === "MovieMarkedMissing") return "Marked movie as missing";
  if (event.type === "MovieRestored") return "Movie became available again";
  if (event.type === "MovieIgnored") return "Ignored movie in the library";
  if (event.type === "AnalysisStarted") return "Started genealogy analysis";
  if (event.type === "AnalysisCompleted") return "Completed genealogy analysis";
  if (event.type === "AnalysisFailed") return "Genealogy analysis failed";
  if (event.type === "ExternalScoresRefreshed") return "Refreshed external scores";
  if (event.type === "ExternalScoresRefreshFailed") return "External score refresh failed";
  if (event.type === "LibraryReconciled") return "Reconciled the library";
  if (event.type === "LibraryCleared") return "Cleared the library";
  if (event.type === "MissingMoviesCleaned") return "Cleaned missing movie records";
  if (event.type === "LibrarySeeded") return "Seeded the library";
  return "Recorded library activity";
}

function technicalEventSummary(event: EventRecord) {
  const reason = stringPayload(event, "reason");
  const message = stringPayload(event, "message");
  const title = stringPayload(event, "title");
  const sourcePath = stringPayload(event, "source_path");
  const targetPath = stringPayload(event, "target_path");
  const destination = stringPayload(event, "destination");
  const path = stringPayload(event, "path");
  const folderPath = stringPayload(event, "folder_path");
  const mediaPath = stringPayload(event, "media_path");
  const assetType = stringPayload(event, "asset_type");
  const action = stringPayload(event, "action");
  const tmdbId = numberPayload(event, "tmdb_id") ?? stringPayload(event, "tmdb_id");
  const confidence = numberPayload(event, "confidence") ?? numberPayload(event, "score");

  if (event.type === "MetadataMatched") {
    return [
      title,
      tmdbId ? `TMDB ${tmdbId}` : null,
      confidence !== null ? `${Math.round(confidence)}% confidence` : null,
    ].filter(Boolean).join(" · ");
  }
  if (event.type === "MetadataRestored") {
    const restoredFields = event.payload?.restored_fields;
    const count = Array.isArray(restoredFields) ? restoredFields.length : 0;
    return count ? `${count} metadata fields restored` : "Metadata fields restored";
  }
  if (event.type === "MovieStateRestored") {
    const restoredFields = event.payload?.restored_fields;
    const count = Array.isArray(restoredFields) ? restoredFields.length : 0;
    const target = event.payload?.target;
    const beforeEventId = typeof target === "object" && target
      ? (target as Record<string, unknown>).before_event_id
      : null;
    return [
      count ? `${count} fields restored` : "Movie fields restored",
      typeof beforeEventId === "string" ? `before ${beforeEventId}` : null,
    ].filter(Boolean).join(" · ");
  }
  if (event.type === "MovieStateBackfilled") {
    const current = event.payload?.current;
    const fieldCount = typeof current === "object" && current
      ? Object.keys(current).length
      : 0;
    const sourceTypes = event.payload?.source_event_types;
    return [
      fieldCount ? `${fieldCount} current fields snapshotted` : "Current Movie state snapshotted",
      Array.isArray(sourceTypes) && sourceTypes.length ? `for ${sourceTypes.join(", ")}` : null,
      "migration only",
    ].filter(Boolean).join(" · ");
  }
  if (event.type === "MetadataMatchSuggested") return reason || "Review required before writing metadata";
  if (event.type === "ArtworkDownloaded") {
    const label = assetType === "backdrop" ? "Backdrop downloaded" : "Poster downloaded";
    return destination ? `${label}: ${destination}` : label;
  }
  if (event.type === "ArtworkRestored") {
    const label = assetType === "backdrop" ? "Backdrop restored" : "Poster restored";
    return destination ? `${label}: ${destination}` : label;
  }
  if (event.type === "MovieFileSnapshotBackfilled") {
    const fileType = stringPayload(event, "file_type") || "file";
    return path ? `${fileType} snapshot only: ${path}` : `${fileType} snapshot only`;
  }
  if (event.type === "ArtworkSelected") return "Poster or backdrop was updated";
  if (event.type === "ArtworkSelectionRestored") {
    const restoredFields = event.payload?.restored_fields;
    const count = Array.isArray(restoredFields) ? restoredFields.length : 0;
    return count ? `${count} artwork fields restored` : "Artwork selection restored";
  }
  if (event.type === "NfoWritten") {
    const label = action === "update_artwork" ? "NFO artwork references updated" : "NFO metadata written";
    return path ? `${label}: ${path}` : label;
  }
  if (event.type === "NfoRestored") return path ? `NFO restored: ${path}` : "NFO restored from backup";
  if (event.type === "RootVideoMoved") return targetPath || sourcePath || "Root video file moved";
  if (event.type === "RootVideoMoveReversed") return sourcePath || targetPath || "Root video moved back to its source path";
  if (event.type === "RootVideoOrganized") return targetPath || sourcePath || "Root video moved into the library";
  if (event.type === "RootVideoOrganizationReverted") return sourcePath || targetPath || "Root video organization was reverted";
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

export function groupActivityEvents(events: EventRecord[], showTechnicalEvents: boolean): ActivityOperation[] {
  const visibleEvents = showTechnicalEvents
    ? events
    : events.filter((event) => !TECHNICAL_EVENT_TYPES.has(event.type));
  const grouped = new Map<string, EventRecord[]>();

  for (const event of visibleEvents) {
    const groupId = event.correlation_id || event.command_id || event.id;
    const groupEvents = grouped.get(groupId);
    if (groupEvents) {
      groupEvents.push(event);
    } else {
      grouped.set(groupId, [event]);
    }
  }

  return Array.from(grouped.entries())
    .map(([id, groupEvents]) => {
      const sortedEvents = [...groupEvents].sort((a, b) => compareEventTimeDesc(a, b));
      const primaryEvent = choosePrimaryEvent(sortedEvents);
      return {
        id,
        title: operationTitle(sortedEvents, primaryEvent),
        summary: operationSummary(sortedEvents, primaryEvent),
        primaryEvent,
        events: sortedEvents,
        eventCount: sortedEvents.length,
        occurred_at: sortedEvents[0]?.occurred_at || primaryEvent.occurred_at,
        command_id: primaryEvent.command_id,
        correlation_id: primaryEvent.correlation_id,
      };
    })
    .sort((a, b) => new Date(b.occurred_at).getTime() - new Date(a.occurred_at).getTime());
}

function compareEventTimeDesc(a: EventRecord, b: EventRecord) {
  const timeDiff = new Date(b.occurred_at).getTime() - new Date(a.occurred_at).getTime();
  if (timeDiff !== 0) return timeDiff;
  return b.id.localeCompare(a.id);
}

function choosePrimaryEvent(events: EventRecord[]) {
  return [...events].sort((a, b) => primaryRank(a.type) - primaryRank(b.type))[0] || events[0];
}

function primaryRank(type: string) {
  const ranks: Record<string, number> = {
    MetadataMatched: 1,
    MovieStateBackfilled: 1,
    MovieStateRestored: 1,
    MetadataRestored: 1,
    ArtworkSelected: 2,
    ArtworkSelectionRestored: 2,
    RootVideoOrganizationReverted: 2,
    RootVideoOrganized: 3,
    RootVideoMoveReversed: 3,
    RootVideoMoved: 4,
    MetadataMatchSuggested: 5,
    MetadataScrapeFailed: 6,
    AnalysisCompleted: 7,
    AnalysisFailed: 8,
    ExternalScoresRefreshed: 9,
    MovieDiscovered: 10,
  };
  return ranks[type] ?? 50;
}

function operationTitle(events: EventRecord[], primaryEvent: EventRecord) {
  if (events.some((event) => event.type === "RootVideoOrganized" || event.type === "RootVideoMoved")) {
    return "Root video organization";
  }
  if (events.some((event) => event.type === "RootVideoOrganizationReverted" || event.type === "RootVideoMoveReversed")) {
    return "Root video restore";
  }
  if (events.some((event) => event.type === "MetadataMatched" || event.type === "MetadataMatchSuggested" || event.type === "MetadataScrapeFailed")) {
    return "Metadata scrape";
  }
  if (events.some((event) => event.type === "MovieStateRestored")) {
    return "Timeline restore";
  }
  if (events.some((event) => event.type === "MovieStateBackfilled" || event.type === "MovieFileSnapshotBackfilled")) {
    return "Replay backfill";
  }
  if (events.some((event) => event.type === "MetadataRestored")) {
    return "Metadata restore";
  }
  if (events.some((event) => event.type === "ArtworkSelected" || event.type === "ArtworkDownloaded")) {
    return "Artwork update";
  }
  if (events.some((event) => event.type === "ArtworkSelectionRestored" || event.type === "ArtworkRestored")) {
    return "Artwork restore";
  }
  if (events.some((event) => event.type.startsWith("Analysis"))) {
    return "Analysis";
  }
  if (events.some((event) => event.type.startsWith("ExternalScores"))) {
    return "External scores";
  }
  return EVENT_LABELS[primaryEvent.type] || primaryEvent.type;
}

function operationSummary(events: EventRecord[], primaryEvent: EventRecord) {
  if (events.length === 1) return technicalEventSummary(primaryEvent);
  const labels = unique(events.map((event) => EVENT_LABELS[event.type] || event.type)).slice(0, 4);
  const suffix = labels.length < events.length ? "more" : null;
  return [technicalEventSummary(primaryEvent), `${events.length} events`, ...labels, suffix].filter(Boolean).join(" · ");
}

function unique(values: string[]) {
  return Array.from(new Set(values));
}
