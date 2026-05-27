"use client";

import { useEffect, useState } from "react";
import { ChevronDown, Clock, Film, Loader2, X } from "lucide-react";
import OperationDryRunPanel from "@/components/OperationDryRunPanel";
import { useTechnicalMode } from "@/components/TechnicalModeProvider";
import TimelineRestorePreviewPanel from "@/components/TimelineRestorePreviewPanel";
import { useMovieAuditEvents } from "@/hooks/useMovie";
import {
  EVENT_LABELS,
  TECHNICAL_EVENT_TYPES,
  eventActionName,
  eventSummary,
  formatEventTime,
  formatRelativeEventTime,
  groupActivityEvents,
  operationDisplaySummary,
  operationDisplayTitle,
  videoDetailItems,
  type ActivityOperation,
} from "@/lib/activity";

interface MovieActivityTimelineProps {
  movieId: string;
  open: boolean;
  onClose: () => void;
}

export default function MovieActivityTimeline({ movieId, open, onClose }: MovieActivityTimelineProps) {
  const { isTechnical, setIsTechnical } = useTechnicalMode();
  const [expandedOperationIds, setExpandedOperationIds] = useState<string[]>([]);
  const { data: events = [], isLoading, error } = useMovieAuditEvents(movieId, open);
  const filteredEvents = isTechnical
    ? events
    : events.filter((event) => !TECHNICAL_EVENT_TYPES.has(event.type));
  const operations = groupActivityEvents(events, isTechnical);
  const visibleOperations = operations.slice(0, 8);
  const hiddenTechnicalCount = events.length - filteredEvents.length;

  const toggleOperation = (id: string) => {
    setExpandedOperationIds((current) => (
      current.includes(id)
        ? current.filter((item) => item !== id)
        : [...current, id]
    ));
  };

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
          <div className="min-w-0 flex-1">
            <span className="block text-xs font-bold uppercase tracking-widest text-neutral-500">
              Activity
            </span>
            <h2 id="movie-activity-title" className="mt-2 text-2xl font-bold uppercase text-white">
              Library history
            </h2>
            <label className="mt-4 flex w-fit cursor-pointer items-center gap-3 text-xs font-bold uppercase tracking-widest text-neutral-500 transition-colors hover:text-neutral-300">
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
          ) : visibleOperations.length === 0 ? (
            <div className="border border-neutral-800 bg-neutral-950 px-4 py-4 text-sm text-neutral-500">
              {events.length > 0 && hiddenTechnicalCount === events.length
                ? "Only technical events are hidden."
                : "No activity recorded yet."}
            </div>
          ) : (
            <ol className="relative space-y-5 border-l border-neutral-800 pl-6">
              {visibleOperations.map((operation) => {
                const expanded = expandedOperationIds.includes(operation.id);
                return (
                  <li key={operation.id} className="relative min-w-0">
                    <span className="absolute -left-[2.05rem] flex h-8 w-8 items-center justify-center border border-neutral-800 bg-black text-neutral-400">
                      <Film className="h-4 w-4" />
                    </span>
                    <div className="grid gap-1 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-start">
                      <div className="min-w-0">
                        <button
                          type="button"
                          onClick={() => toggleOperation(operation.id)}
                          className="inline-flex max-w-full items-center gap-2 text-left text-sm font-bold uppercase tracking-widest text-white transition-colors hover:text-neutral-300"
                        >
                          <ChevronDown className={`h-4 w-4 shrink-0 transition-transform ${expanded ? "rotate-0" : "-rotate-90"}`} />
                          <span className="truncate">{operationDisplayTitle(operation, null, isTechnical)}</span>
                        </button>
                        <p className="mt-1 break-words text-sm leading-relaxed text-neutral-400">
                          {operationDisplaySummary(operation, isTechnical)}
                        </p>
                        <p className="mt-2 text-xs uppercase tracking-widest text-neutral-700">
                          {operation.eventCount} {operation.eventCount === 1 ? "step" : "steps"}
                        </p>
                        {expanded ? (
                          isTechnical ? (
                            <TechnicalOperationDetails operation={operation} movieId={movieId} />
                          ) : (
                            <FriendlyOperationDetails operation={operation} />
                          )
                        ) : null}
                      </div>
                      <time className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs uppercase tracking-widest text-neutral-600 sm:justify-end">
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
      </section>
    </div>
  );
}

function FriendlyOperationDetails({ operation }: { operation: ActivityOperation }) {
  return (
    <ul className="mt-4 space-y-3 border-l border-neutral-900 pl-4">
      {operation.events.map((event) => {
        const details = videoDetailItems(event);
        return (
          <li key={event.id} className="grid gap-1 sm:grid-cols-[8.5rem_minmax(0,1fr)]">
            <time className="flex items-center gap-1.5 text-xs uppercase tracking-widest text-neutral-700">
              <Clock className="h-3 w-3" />
              {formatEventTime(event.occurred_at)}
            </time>
            <div className="min-w-0">
              <p className="break-words text-sm leading-relaxed text-neutral-500">
                {eventActionName(event)}
              </p>
              {details.length ? <VideoDetailList items={details} /> : null}
            </div>
          </li>
        );
      })}
    </ul>
  );
}

function VideoDetailList({ items }: { items: ReturnType<typeof videoDetailItems> }) {
  return (
    <dl className="mt-3 grid gap-2 text-xs sm:grid-cols-2">
      {items.map((item) => (
        <div key={item.label} className="min-w-0 border border-neutral-900 bg-black/30 px-3 py-2">
          <dt className="truncate uppercase tracking-widest text-neutral-700">{item.label}</dt>
          <dd className="mt-1 break-words font-medium text-neutral-300">{item.value}</dd>
        </div>
      ))}
    </dl>
  );
}

function TechnicalOperationDetails({ operation, movieId }: { operation: ActivityOperation; movieId: string }) {
  return (
    <>
      <OperationDryRunPanel
        commandId={operation.command_id}
        correlationId={operation.correlation_id}
      />
      <ul className="mt-4 space-y-5 border-l border-neutral-900 pl-4">
        {operation.events.map((event) => (
          <li key={event.id} className="min-w-0 space-y-3">
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
              movieId={movieId}
            />
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
