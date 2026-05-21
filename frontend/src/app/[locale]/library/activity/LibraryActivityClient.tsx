"use client";

import { useMemo, useState } from "react";
import useSWR from "swr";
import { ChevronDown, Clock, Filter, Loader2 } from "lucide-react";
import OperationDryRunPanel from "@/components/OperationDryRunPanel";
import { Link } from "@/i18n/routing";
import {
  EVENT_LABELS,
  EVENT_TYPE_OPTIONS,
  TECHNICAL_EVENT_TYPES,
  eventIcon,
  eventSummary,
  eventTitle,
  formatEventTime,
  groupActivityEvents,
} from "@/lib/activity";
import { API } from "@/lib/api";
import type { EventRecord } from "@/types/movie";

export default function LibraryActivityClient() {
  const [aggregateType, setAggregateType] = useState("");
  const [eventType, setEventType] = useState("");
  const [movieId, setMovieId] = useState("");
  const [showTechnicalEvents, setShowTechnicalEvents] = useState(false);
  const [expandedOperationIds, setExpandedOperationIds] = useState<string[]>([]);

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
  const operations = groupActivityEvents(events, showTechnicalEvents);
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
          {operations.length} operations / {visibleEvents.length} visible events
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
        <ol className="relative space-y-5 border-l border-neutral-800 pl-6">
          {operations.map((operation) => {
            const Icon = eventIcon(operation.primaryEvent.type);
            const expanded = expandedOperationIds.includes(operation.id);
            return (
              <li key={operation.id} className="relative min-w-0">
                <span className="absolute -left-[2.05rem] flex h-8 w-8 items-center justify-center border border-neutral-800 bg-black text-neutral-400">
                  <Icon className="h-4 w-4" />
                </span>
                <div className="grid gap-2 border-b border-neutral-900 pb-5 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-start">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-3">
                      <button
                        type="button"
                        onClick={() => toggleOperation(operation.id)}
                        className="inline-flex min-w-0 items-center gap-2 text-left text-sm font-bold uppercase tracking-widest text-white transition-colors hover:text-neutral-300"
                      >
                        <ChevronDown className={`h-4 w-4 shrink-0 transition-transform ${expanded ? "rotate-0" : "-rotate-90"}`} />
                        <span className="truncate">{operation.title}</span>
                      </button>
                      <span className="text-xs font-bold uppercase tracking-widest text-neutral-700">
                        {operation.eventCount} {operation.eventCount === 1 ? "event" : "events"}
                      </span>
                    </div>
                    <p className="mt-2 break-words text-sm leading-relaxed text-neutral-400">
                      {operation.summary}
                    </p>
                    <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs uppercase tracking-widest text-neutral-600">
                      {operation.primaryEvent.aggregate_type === "movie" && operation.primaryEvent.aggregate_id ? (
                        <Link href={`/library/${operation.primaryEvent.aggregate_id}`} className="text-neutral-400 hover:text-white">
                          {eventTitle(operation.primaryEvent)}
                        </Link>
                      ) : (
                        <span>{eventTitle(operation.primaryEvent)}</span>
                      )}
                      <span>{operation.primaryEvent.aggregate_type}</span>
                      {operation.correlation_id ? <span>{operation.correlation_id}</span> : <span>{operation.primaryEvent.id}</span>}
                    </div>
                    {expanded ? (
                      <>
                        <OperationDryRunPanel
                          commandId={operation.command_id}
                          correlationId={operation.correlation_id}
                        />
                        <ul className="mt-5 space-y-4 border-l border-neutral-900 pl-4">
                          {operation.events.map((event) => (
                            <li key={event.id} className="grid gap-1 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-start">
                              <div className="min-w-0">
                                <p className="truncate text-xs font-bold uppercase tracking-widest text-neutral-300">
                                  {EVENT_LABELS[event.type] || event.type}
                                </p>
                                <p className="mt-1 break-words text-sm leading-relaxed text-neutral-500">
                                  {eventSummary(event)}
                                </p>
                                <p className="mt-1 break-all text-xs uppercase tracking-widest text-neutral-700">
                                  {event.id}
                                </p>
                              </div>
                              <time className="flex items-center gap-1.5 text-xs uppercase tracking-widest text-neutral-700">
                                <Clock className="h-3 w-3" />
                                {formatEventTime(event.occurred_at)}
                              </time>
                            </li>
                          ))}
                        </ul>
                      </>
                    ) : null}
                  </div>
                  <time className="flex items-center gap-1.5 text-xs uppercase tracking-widest text-neutral-600">
                    <Clock className="h-3 w-3" />
                    {formatEventTime(operation.occurred_at)}
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
