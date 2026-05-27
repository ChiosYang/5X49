"use client";

import { useMemo, useState, useSyncExternalStore } from "react";
import Image from "next/image";
import useSWR from "swr";
import { ChevronDown, Clock, Film, Filter, Loader2, Wrench } from "lucide-react";
import OperationDryRunPanel from "@/components/OperationDryRunPanel";
import { useTechnicalMode } from "@/components/TechnicalModeProvider";
import TimelineRestorePreviewPanel from "@/components/TimelineRestorePreviewPanel";
import { useLibrary } from "@/hooks/useLibrary";
import { Link } from "@/i18n/routing";
import {
  EVENT_LABELS,
  EVENT_TYPE_OPTIONS,
  TECHNICAL_EVENT_TYPES,
  eventActionName,
  eventSummary,
  formatEventTime,
  formatRelativeEventTime,
  groupActivityEvents,
  movieTitle,
  operationDisplaySummary,
  operationDisplayTitle,
  type ActivityOperation,
} from "@/lib/activity";
import { API } from "@/lib/api";
import type { EventRecord, LibraryMovie } from "@/types/movie";

const subscribeToHydration = () => () => {};
const getClientHydrationSnapshot = () => true;
const getServerHydrationSnapshot = () => false;
const isDevelopment = process.env.NODE_ENV === "development";

export default function LibraryActivityClient() {
  const hasMounted = useSyncExternalStore(
    subscribeToHydration,
    getClientHydrationSnapshot,
    getServerHydrationSnapshot,
  );
  const { isTechnical, setIsTechnical } = useTechnicalMode();
  const [aggregateType, setAggregateType] = useState("");
  const [eventType, setEventType] = useState("");
  const [movieId, setMovieId] = useState("");
  const [expandedOperationIds, setExpandedOperationIds] = useState<string[]>([]);

  const queryMovieId = isTechnical ? movieId.trim() : "";
  const url = useMemo(() => API.libraryAuditEventsUrl({
    aggregate_type: aggregateType || undefined,
    aggregate_id: queryMovieId || undefined,
    type: eventType || undefined,
    limit: 100,
  }), [aggregateType, eventType, queryMovieId]);

  const { data: events = [], isLoading, error } = useSWR<EventRecord[]>(hasMounted ? url : null, {
    refreshInterval: 5000,
  });
  const { data: movies = [] } = useLibrary();

  const movieById = useMemo(() => {
    return new Map(movies.map((movie) => [movie.id, movie]));
  }, [movies]);

  const visibleEvents = isTechnical
    ? events
    : events.filter((event) => !TECHNICAL_EVENT_TYPES.has(event.type));
  const operations = groupActivityEvents(events, isTechnical);
  const hiddenTechnicalCount = events.length - visibleEvents.length;

  const toggleOperation = (id: string) => {
    setExpandedOperationIds((current) => (
      current.includes(id)
        ? current.filter((item) => item !== id)
        : [...current, id]
    ));
  };

  return (
    <div className="space-y-8">
      <section className="grid gap-4 border-y border-neutral-900 py-5 md:grid-cols-[minmax(0,1fr)_auto] md:items-end">
        <div className={`grid gap-3 ${isTechnical ? "sm:grid-cols-3" : "sm:grid-cols-2"}`}>
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
              {hasMounted ? EVENT_TYPE_OPTIONS.map((type) => (
                <option key={type} value={type}>{EVENT_LABELS[type] || type}</option>
              )) : null}
            </select>
          </label>
          {isTechnical ? (
            <label className="grid gap-2">
              <span className="text-xs font-bold uppercase tracking-widest text-neutral-500">Movie ID</span>
              <input
                value={movieId}
                onChange={(event) => setMovieId(event.target.value)}
                placeholder="Optional aggregate id"
                className="h-11 border border-neutral-800 bg-black px-3 text-sm text-white outline-none transition-colors placeholder:text-neutral-700 focus:border-neutral-500"
              />
            </label>
          ) : null}
        </div>
        <div className="flex flex-wrap items-center gap-4">
          {isDevelopment ? (
            <Link
              href="/admin/health"
              className="inline-flex h-9 items-center gap-2 border border-neutral-900 px-3 text-xs font-bold uppercase tracking-widest text-neutral-500 transition-colors hover:border-neutral-700 hover:text-neutral-300"
            >
              <Wrench className="h-3.5 w-3.5" />
              Developer tools
            </Link>
          ) : null}
          <label className="flex w-fit cursor-pointer items-center gap-3 text-xs font-bold uppercase tracking-widest text-neutral-500 transition-colors hover:text-neutral-300">
            <input
              type="checkbox"
              checked={isTechnical}
              onChange={(event) => setIsTechnical(event.target.checked)}
              className="h-4 w-4 accent-white"
            />
            Show technical
            {!isTechnical && hiddenTechnicalCount > 0 ? (
              <span className="text-neutral-700">({hiddenTechnicalCount} hidden)</span>
            ) : null}
          </label>
        </div>
      </section>

      <div className="flex items-center justify-between gap-4 text-xs font-bold uppercase tracking-widest text-neutral-600">
        <span className="inline-flex items-center gap-2">
          <Filter className="h-3.5 w-3.5" />
          {operations.length} activity groups / {visibleEvents.length} visible steps
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
      ) : operations.length === 0 ? (
        <div className="border border-neutral-800 bg-neutral-950 px-4 py-4 text-sm text-neutral-500">
          {events.length > 0 && hiddenTechnicalCount === events.length
            ? "Only technical events are hidden."
            : "No activity recorded yet."}
        </div>
      ) : (
        <ol className="space-y-4">
          {operations.map((operation) => {
            const expanded = expandedOperationIds.includes(operation.id);
            const operationMovieId = movieIdForOperation(operation);
            const movie = operationMovieId ? movieById.get(operationMovieId) : undefined;
            return (
              <li key={operation.id} className="grid gap-4 border border-neutral-900 bg-neutral-950/35 p-4 sm:grid-cols-[4.75rem_minmax(0,1fr)]">
                <ActivityPoster movie={movie} />
                <div className="grid min-w-0 gap-3 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-start">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-3">
                      <button
                        type="button"
                        onClick={() => toggleOperation(operation.id)}
                        className="inline-flex min-w-0 items-center gap-2 text-left text-base font-semibold text-white transition-colors hover:text-neutral-300"
                      >
                        <ChevronDown className={`h-4 w-4 shrink-0 transition-transform ${expanded ? "rotate-0" : "-rotate-90"}`} />
                        <span className="truncate">{operationDisplayTitle(operation, movie, isTechnical)}</span>
                      </button>
                      <span className="border border-neutral-800 px-2 py-1 text-[10px] font-bold uppercase tracking-widest text-neutral-600">
                        {operation.eventCount} {operation.eventCount === 1 ? "step" : "steps"}
                      </span>
                    </div>
                    <p className="mt-2 break-words text-sm leading-relaxed text-neutral-400">
                      {operationDisplaySummary(operation, isTechnical)}
                    </p>
                    <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs uppercase tracking-widest text-neutral-600">
                      {operationMovieId ? (
                        <Link href={`/library/${operationMovieId}`} className="text-neutral-400 hover:text-white">
                          {movieTitle(movie, operation.primaryEvent)}
                        </Link>
                      ) : (
                        <span>Library activity</span>
                      )}
                      {isTechnical ? (
                        <>
                          <span>{operation.primaryEvent.aggregate_type}</span>
                          {operation.correlation_id ? <span className="break-all">{operation.correlation_id}</span> : <span className="break-all">{operation.primaryEvent.id}</span>}
                        </>
                      ) : null}
                    </div>
                    {expanded ? (
                      isTechnical ? (
                        <TechnicalOperationDetails operation={operation} />
                      ) : (
                        <FriendlyOperationDetails operation={operation} />
                      )
                    ) : null}
                  </div>
                  <time className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs uppercase tracking-widest text-neutral-600 lg:justify-end">
                    <Clock className="h-3 w-3" />
                    {formatEventTime(operation.occurred_at)}
                    <span className="text-neutral-700">{formatRelativeEventTime(operation.occurred_at)}</span>
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

function movieIdForOperation(operation: ActivityOperation) {
  for (const event of operation.events) {
    if (event.aggregate_type === "movie" && event.aggregate_id) return event.aggregate_id;
    const payloadMovieId = event.payload?.movie_id;
    if (typeof payloadMovieId === "string" && payloadMovieId.trim()) return payloadMovieId;
  }
  return null;
}

function ActivityPoster({ movie }: { movie?: LibraryMovie }) {
  const posterPath = movie?.poster_thumb_local || movie?.poster_local;
  const artworkVersion = movie?.metadata_updated_at ? `?v=${encodeURIComponent(movie.metadata_updated_at)}` : "";
  const posterSrc = posterPath ? `${API.mediaUrl(posterPath)}${artworkVersion}` : null;

  return (
    <div className="relative h-28 w-20 overflow-hidden border border-neutral-800 bg-neutral-950 sm:h-28 sm:w-full">
      {posterSrc ? (
        <Image
          src={posterSrc}
          alt={movie?.title || "Movie poster"}
          fill
          sizes="80px"
          className="object-cover"
        />
      ) : (
        <div className="flex h-full w-full items-center justify-center text-neutral-600">
          <Film className="h-6 w-6" />
        </div>
      )}
    </div>
  );
}

function FriendlyOperationDetails({ operation }: { operation: ActivityOperation }) {
  return (
    <ul className="mt-5 space-y-3 border-l border-neutral-900 pl-4">
      {operation.events.map((event) => (
        <li key={event.id} className="grid gap-1 sm:grid-cols-[8.5rem_minmax(0,1fr)]">
          <time className="flex items-center gap-1.5 text-xs uppercase tracking-widest text-neutral-700">
            <Clock className="h-3 w-3" />
            {formatEventTime(event.occurred_at)}
          </time>
          <p className="break-words text-sm leading-relaxed text-neutral-400">
            {eventActionName(event)}
          </p>
        </li>
      ))}
    </ul>
  );
}

function TechnicalOperationDetails({ operation }: { operation: ActivityOperation }) {
  return (
    <>
      <OperationDryRunPanel
        commandId={operation.command_id}
        correlationId={operation.correlation_id}
      />
      <ul className="mt-5 space-y-5 border-l border-neutral-900 pl-4">
        {operation.events.map((event) => (
          <li key={event.id} className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-start">
            <div className="min-w-0 space-y-3">
              <div>
                <p className="truncate text-xs font-bold uppercase tracking-widest text-neutral-300">
                  {EVENT_LABELS[event.type] || event.type}
                </p>
                <p className="mt-1 break-words text-sm leading-relaxed text-neutral-500">
                  {eventSummary(event, true)}
                </p>
                <div className="mt-2 grid gap-1 text-xs uppercase tracking-widest text-neutral-700">
                  <span className="break-all">Event: {event.id}</span>
                  {event.command_id ? <span className="break-all">Command: {event.command_id}</span> : null}
                  {event.correlation_id ? <span className="break-all">Correlation: {event.correlation_id}</span> : null}
                  {event.aggregate_id ? <span className="break-all">Aggregate: {event.aggregate_type}/{event.aggregate_id}</span> : null}
                </div>
              </div>
              <JsonBlock label="Payload" value={event.payload} />
              <JsonBlock label="Context" value={event.context} />
              <TimelineRestorePreviewPanel
                event={event}
                movieId={event.aggregate_id}
              />
            </div>
            <time className="flex items-center gap-1.5 text-xs uppercase tracking-widest text-neutral-700">
              <Clock className="h-3 w-3" />
              {formatEventTime(event.occurred_at)}
            </time>
          </li>
        ))}
      </ul>
    </>
  );
}

function JsonBlock({ label, value }: { label: string; value?: Record<string, unknown> | null }) {
  if (!value || Object.keys(value).length === 0) {
    return null;
  }

  return (
    <details className="border border-neutral-900 bg-black/40 p-3">
      <summary className="cursor-pointer text-xs font-bold uppercase tracking-widest text-neutral-500">
        {label}
      </summary>
      <pre className="mt-3 max-h-72 overflow-auto whitespace-pre-wrap break-words text-xs leading-relaxed text-neutral-500">
        {JSON.stringify(value, null, 2)}
      </pre>
    </details>
  );
}
