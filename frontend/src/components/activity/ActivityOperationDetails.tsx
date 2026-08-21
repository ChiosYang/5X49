"use client";

import { Clock } from "lucide-react";
import OperationDryRunPanel from "@/components/OperationDryRunPanel";
import TimelineRestorePreviewPanel from "@/components/TimelineRestorePreviewPanel";
import {
  EVENT_LABELS,
  eventActionName,
  eventSummary,
  formatEventTime,
  videoDetailItems,
  type ActivityOperation,
} from "@/lib/activity";
import { cn } from "@/lib/cn";

export function ActivityOperationDetails({
  mode,
  movieId,
  operation,
  variant = "page",
}: {
  mode: "friendly" | "technical";
  movieId?: string | null;
  operation: ActivityOperation;
  variant?: "page" | "timeline";
}) {
  if (mode === "friendly") {
    return <FriendlyDetails operation={operation} variant={variant} />;
  }
  return <TechnicalDetails movieId={movieId} operation={operation} variant={variant} />;
}

function FriendlyDetails({
  operation,
  variant,
}: {
  operation: ActivityOperation;
  variant: "page" | "timeline";
}) {
  return (
    <ul className={cn("space-y-3 border-l border-line pl-4", variant === "page" ? "mt-5" : "mt-4")}>
      {operation.events.map((event) => {
        const details = videoDetailItems(event);
        return (
          <li key={event.id} className="grid gap-1 sm:grid-cols-[8.5rem_minmax(0,1fr)]">
            <time className="flex items-center gap-1.5 text-xs tracking-widest text-ink-disabled/70 uppercase">
              <Clock className="h-3 w-3" />
              {formatEventTime(event.occurred_at)}
            </time>
            <div className="min-w-0">
              <p className="break-words text-sm leading-relaxed text-ink-subtle">
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
        <div key={item.label} className="min-w-0 border border-line bg-canvas/30 px-3 py-2">
          <dt className="truncate tracking-widest text-ink-disabled/70 uppercase">{item.label}</dt>
          <dd className="mt-1 break-words font-medium text-ink-muted">{item.value}</dd>
        </div>
      ))}
    </dl>
  );
}

function TechnicalDetails({
  movieId,
  operation,
  variant,
}: {
  movieId?: string | null;
  operation: ActivityOperation;
  variant: "page" | "timeline";
}) {
  return (
    <>
      <OperationDryRunPanel commandId={operation.command_id} correlationId={operation.correlation_id} />
      <ul className={cn("space-y-5 border-l border-line pl-4", variant === "page" ? "mt-5" : "mt-4")}>
        {operation.events.map((event) => (
          <li
            key={event.id}
            className={cn(
              "min-w-0",
              variant === "page" ? "grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-start" : "space-y-3",
            )}
          >
            <div className="min-w-0 space-y-3">
              <div>
                <p className="truncate text-xs font-bold tracking-widest text-ink-muted uppercase">
                  {EVENT_LABELS[event.type] || event.type}
                </p>
                <p className="mt-1 break-words text-sm leading-relaxed text-ink-subtle">
                  {eventSummary(event, true)}
                </p>
                <div className="mt-2 grid gap-1 text-xs tracking-widest text-ink-disabled/70 uppercase">
                  <span className="break-all">Event: {event.id}</span>
                  {event.command_id ? <span className="break-all">Command: {event.command_id}</span> : null}
                  {event.correlation_id ? <span className="break-all">Correlation: {event.correlation_id}</span> : null}
                  {event.aggregate_id ? <span className="break-all">Aggregate: {event.aggregate_type}/{event.aggregate_id}</span> : null}
                </div>
              </div>
              <JsonBlock label="Payload" value={event.payload} />
              <JsonBlock label="Context" value={event.context} />
              <TimelineRestorePreviewPanel event={event} movieId={movieId ?? event.aggregate_id} />
            </div>
            {variant === "page" ? (
              <time className="flex items-center gap-1.5 text-xs tracking-widest text-ink-disabled/70 uppercase">
                <Clock className="h-3 w-3" />
                {formatEventTime(event.occurred_at)}
              </time>
            ) : null}
          </li>
        ))}
      </ul>
    </>
  );
}

function JsonBlock({ label, value }: { label: string; value?: Record<string, unknown> | null }) {
  if (!value || Object.keys(value).length === 0) return null;

  return (
    <details className="border border-line bg-canvas/40 p-3">
      <summary className="focus-ring cursor-pointer text-xs font-bold tracking-widest text-ink-subtle uppercase">
        {label}
      </summary>
      <pre className="mt-3 max-h-72 overflow-auto text-xs leading-relaxed whitespace-pre-wrap break-words text-ink-subtle">
        {JSON.stringify(value, null, 2)}
      </pre>
    </details>
  );
}
