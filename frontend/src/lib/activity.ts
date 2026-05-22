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
import type { EventRecord } from "@/types/movie";

export const EVENT_LABELS: Record<string, string> = {
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
  ArtworkDownloaded: "Artwork downloaded",
  ArtworkSelected: "Artwork selected",
  ArtworkRestored: "Artwork restored",
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
  "MetadataMatchSuggested",
  "MetadataMatched",
  "MetadataScrapeFailed",
  "ArtworkDownloaded",
  "ArtworkSelected",
  "ArtworkRestored",
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

export function stringPayload(event: EventRecord, key: string) {
  const value = event.payload?.[key];
  return typeof value === "string" && value.trim() ? value : null;
}

export function numberPayload(event: EventRecord, key: string) {
  const value = event.payload?.[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function eventTitle(event: EventRecord) {
  return stringPayload(event, "title") || event.aggregate_id || "System event";
}

export function eventSummary(event: EventRecord) {
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
  if (event.type === "MetadataMatchSuggested") return reason || "Review required before writing metadata";
  if (event.type === "ArtworkDownloaded") {
    const label = assetType === "backdrop" ? "Backdrop downloaded" : "Poster downloaded";
    return destination ? `${label}: ${destination}` : label;
  }
  if (event.type === "ArtworkRestored") {
    const label = assetType === "backdrop" ? "Backdrop restored" : "Poster restored";
    return destination ? `${label}: ${destination}` : label;
  }
  if (event.type === "ArtworkSelected") return "Poster or backdrop was updated";
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
    ArtworkSelected: 2,
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
  if (events.some((event) => event.type === "ArtworkSelected" || event.type === "ArtworkDownloaded")) {
    return "Artwork update";
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
  if (events.length === 1) return eventSummary(primaryEvent);
  const labels = unique(events.map((event) => EVENT_LABELS[event.type] || event.type)).slice(0, 4);
  const suffix = labels.length < events.length ? "more" : null;
  return [eventSummary(primaryEvent), `${events.length} events`, ...labels, suffix].filter(Boolean).join(" · ");
}

function unique(values: string[]) {
  return Array.from(new Set(values));
}
