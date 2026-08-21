"use client";

import { useMemo, useState, useSyncExternalStore } from "react";
import Image from "next/image";
import useSWR from "swr";
import { ChevronDown, Clock, Film, Filter, Wrench } from "lucide-react";
import { ActivityOperationDetails } from "@/components/activity/ActivityOperationDetails";
import { useTechnicalMode } from "@/components/TechnicalModeProvider";
import { Spinner, StateMessage } from "@/components/ui/Feedback";
import { FormField, Select, TextInput } from "@/components/ui/FormControls";
import { useLibrary } from "@/hooks/useLibrary";
import { Link } from "@/i18n/routing";
import {
  EVENT_LABELS,
  EVENT_TYPE_OPTIONS,
  TECHNICAL_EVENT_TYPES,
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
          <FormField label="Aggregate">
            <Select
              value={aggregateType}
              onChange={(event) => setAggregateType(event.target.value)}
            >
              <option value="">All</option>
              <option value="movie">Movie</option>
              <option value="library">Library</option>
              <option value="file">File</option>
            </Select>
          </FormField>
          <FormField label="Event">
            <Select
              value={eventType}
              onChange={(event) => setEventType(event.target.value)}
            >
              <option value="">All events</option>
              {hasMounted ? EVENT_TYPE_OPTIONS.map((type) => (
                <option key={type} value={type}>{EVENT_LABELS[type] || type}</option>
              )) : null}
            </Select>
          </FormField>
          {isTechnical ? (
            <FormField label="Movie ID">
              <TextInput
                value={movieId}
                onChange={(event) => setMovieId(event.target.value)}
                placeholder="Optional aggregate id"
              />
            </FormField>
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
            <Spinner className="h-3.5 w-3.5" />
            Loading
          </span>
        ) : null}
      </div>

      {error ? (
        <StateMessage state="error">
          Activity could not be loaded.
        </StateMessage>
      ) : operations.length === 0 ? (
        <StateMessage>
          {events.length > 0 && hiddenTechnicalCount === events.length
            ? "Only technical events are hidden."
            : "No activity recorded yet."}
        </StateMessage>
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
                      <ActivityOperationDetails
                        operation={operation}
                        mode={isTechnical ? "technical" : "friendly"}
                      />
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
