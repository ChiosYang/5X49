"use client";

import { useState } from "react";
import { ChevronDown, Clock, Film, X } from "lucide-react";
import { ActivityOperationDetails } from "@/components/activity/ActivityOperationDetails";
import { useTechnicalMode } from "@/components/TechnicalModeProvider";
import { IconButton } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { Spinner, StateMessage } from "@/components/ui/Feedback";
import { useMovieAuditEvents } from "@/hooks/useMovie";
import {
  TECHNICAL_EVENT_TYPES,
  formatEventTime,
  formatRelativeEventTime,
  groupActivityEvents,
  operationDisplaySummary,
  operationDisplayTitle,
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

  return (
    <Dialog
      open={open}
      onClose={onClose}
      closeLabel="Close library history"
      closeOnBackdrop
      closeOnEscape
      lockScroll={false}
      placement="bottom"
      ariaLabelledBy="movie-activity-title"
      panelClassName="max-h-[min(42rem,calc(100vh-3rem))]"
    >
        <div className="flex items-start justify-between gap-6 border-b border-line-strong px-5 py-5 sm:px-6">
          <div className="min-w-0 flex-1">
            <span className="block text-xs font-bold tracking-widest text-ink-subtle uppercase">
              Activity
            </span>
            <h2 id="movie-activity-title" className="type-section-title mt-2 text-ink">
              Library history
            </h2>
            <label className="duration-standard mt-4 flex w-fit cursor-pointer items-center gap-3 text-xs font-bold tracking-widest text-ink-subtle uppercase transition-colors hover:text-ink-muted">
              <input
                type="checkbox"
                checked={isTechnical}
                onChange={(event) => setIsTechnical(event.target.checked)}
                className="focus-ring h-4 w-4 accent-ink"
              />
              Show technical
              {!isTechnical && hiddenTechnicalCount > 0 ? (
                <span className="text-ink-disabled/70">({hiddenTechnicalCount} hidden)</span>
              ) : null}
            </label>
          </div>
          <div className="flex shrink-0 items-center gap-3">
            {isLoading && <Spinner className="h-5 w-5 text-ink-subtle" />}
            <IconButton
              onClick={onClose}
              className="h-10 w-10"
              aria-label="Close library history"
              title="Close library history"
              icon={<X className="h-4 w-4" />}
            />
          </div>
        </div>

        <div className="max-h-[calc(min(42rem,100vh-3rem)-6.75rem)] overflow-y-auto px-5 py-6 sm:px-6">
          {error ? (
            <StateMessage state="error">
              Activity could not be loaded.
            </StateMessage>
          ) : visibleOperations.length === 0 ? (
            <StateMessage>
              {events.length > 0 && hiddenTechnicalCount === events.length
                ? "Only technical events are hidden."
                : "No activity recorded yet."}
            </StateMessage>
          ) : (
            <ol className="relative space-y-5 border-l border-line-strong pl-6">
              {visibleOperations.map((operation) => {
                const expanded = expandedOperationIds.includes(operation.id);
                return (
                  <li key={operation.id} className="relative min-w-0">
                    <span className="absolute -left-[2.05rem] flex h-8 w-8 items-center justify-center border border-line-strong bg-canvas text-ink-muted">
                      <Film className="h-4 w-4" />
                    </span>
                    <div className="grid gap-1 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-start">
                      <div className="min-w-0">
                        <button
                          type="button"
                          onClick={() => toggleOperation(operation.id)}
                          className="focus-ring duration-standard inline-flex max-w-full items-center gap-2 text-left text-sm font-bold tracking-widest text-ink uppercase transition-colors hover:text-ink-muted"
                        >
                          <ChevronDown className={`duration-standard h-4 w-4 shrink-0 transition-transform ${expanded ? "rotate-0" : "-rotate-90"}`} />
                          <span className="truncate">{operationDisplayTitle(operation, null, isTechnical)}</span>
                        </button>
                        <p className="mt-1 break-words text-sm leading-relaxed text-ink-muted">
                          {operationDisplaySummary(operation, isTechnical)}
                        </p>
                        <p className="mt-2 text-xs tracking-widest text-ink-disabled/70 uppercase">
                          {operation.eventCount} {operation.eventCount === 1 ? "step" : "steps"}
                        </p>
                        {expanded ? (
                          <ActivityOperationDetails
                            operation={operation}
                            mode={isTechnical ? "technical" : "friendly"}
                            movieId={movieId}
                            variant="timeline"
                          />
                        ) : null}
                      </div>
                      <time className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs tracking-widest text-ink-disabled uppercase sm:justify-end">
                        <Clock className="h-3 w-3" />
                        {formatEventTime(operation.occurred_at)}
                        <span className="text-ink-disabled/70">{formatRelativeEventTime(operation.occurred_at)}</span>
                      </time>
                    </div>
                  </li>
                );
              })}
            </ol>
          )}
        </div>
    </Dialog>
  );
}
