"use client";

import { useState } from "react";
import { AlertCircle, CheckCircle2, ChevronDown, Database, Loader2, RefreshCw } from "lucide-react";
import { API } from "@/lib/api";
import type { MovieProjectionRebuildReport, MovieReplayBackfillReport } from "@/types/movie";

const MAX_ITEMS = 6;

interface HealthReport {
  projection: MovieProjectionRebuildReport;
  backfill: MovieReplayBackfillReport;
}

function formatValue(value: unknown) {
  if (value === undefined) return "missing";
  if (value === null) return "null";
  if (typeof value === "string") return value || "\"\"";
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function entriesLabel(entries: Record<string, number>) {
  const items = Object.entries(entries);
  if (!items.length) return "None";
  return items.map(([type, count]) => `${type} ${count}`).join(", ");
}

async function postJson<T>(url: string): Promise<T> {
  const response = await fetch(url, { method: "POST" });
  if (!response.ok) {
    const errorBody = await response.json().catch(() => null) as { detail?: unknown } | null;
    throw new Error(typeof errorBody?.detail === "string" ? errorBody.detail : "Event sourcing health check failed");
  }
  return response.json();
}

export default function EventSourcingHealthPanel() {
  const [report, setReport] = useState<HealthReport | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const runCheck = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const [projection, backfill] = await Promise.all([
        postJson<MovieProjectionRebuildReport>(API.libraryMovieProjectionRebuildUrl({ dry_run: true, base: "empty", limit: 5000 })),
        postJson<MovieReplayBackfillReport>(API.libraryMovieReplayBackfillUrl({ dry_run: true, sample_limit: 20 })),
      ]);
      setReport({ projection, backfill });
      setExpanded(true);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Event sourcing health check failed");
    } finally {
      setIsLoading(false);
    }
  };

  const hasIssues = report
    ? report.projection.skipped_projectable_events > 0
      || report.projection.unsupported_events > 0
      || report.projection.movies_with_differences > 0
      || report.backfill.events_to_create > 0
      || report.backfill.unsupported.length > 0
      || report.backfill.unavailable_file_snapshots.length > 0
    : false;

  return (
    <section className="border-y border-neutral-900 py-5">
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-start">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-3">
            <span className="inline-flex h-8 w-8 items-center justify-center border border-neutral-800 text-neutral-400">
              <Database className="h-4 w-4" />
            </span>
            <div className="min-w-0">
              <p className="text-xs font-bold uppercase tracking-widest text-neutral-500">Event sourcing health</p>
              <p className="mt-1 break-words text-sm leading-relaxed text-neutral-400">
                Read-only replay coverage and backfill preview.
              </p>
            </div>
          </div>

          {report ? (
            <div className="mt-4 flex flex-wrap gap-2 text-xs font-bold uppercase tracking-widest">
              <Metric label="Movies compared" value={report.projection.movies_compared} />
              <Metric label="Differences" value={report.projection.movies_with_differences} tone={report.projection.movies_with_differences ? "warn" : "ok"} />
              <Metric label="Skipped" value={report.projection.skipped_projectable_events} tone={report.projection.skipped_projectable_events ? "warn" : "ok"} />
              <Metric label="Backfill events" value={report.backfill.events_to_create} tone={report.backfill.events_to_create ? "warn" : "ok"} />
              <Metric label="File gaps" value={report.backfill.unavailable_file_snapshots.length} tone={report.backfill.unavailable_file_snapshots.length ? "warn" : "ok"} />
            </div>
          ) : null}

          {error ? (
            <p className="mt-3 break-words text-sm text-red-300">{error}</p>
          ) : null}
        </div>

        <div className="flex flex-wrap items-center gap-3">
          {report ? (
            <button
              type="button"
              onClick={() => setExpanded((current) => !current)}
              className="inline-flex h-9 items-center gap-2 border border-neutral-800 px-3 text-xs font-bold uppercase tracking-widest text-neutral-300 transition-colors hover:border-neutral-500 hover:text-white"
            >
              <ChevronDown className={`h-4 w-4 transition-transform ${expanded ? "rotate-0" : "-rotate-90"}`} />
              Details
            </button>
          ) : null}
          <button
            type="button"
            onClick={runCheck}
            disabled={isLoading}
            className="inline-flex h-9 items-center gap-2 border border-neutral-700 bg-neutral-950 px-3 text-xs font-bold uppercase tracking-widest text-white transition-colors hover:border-neutral-400 disabled:cursor-wait disabled:opacity-60"
          >
            {isLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
            Run dry-run
          </button>
        </div>
      </div>

      {report && expanded ? (
        <div className="mt-5 space-y-5 border-t border-neutral-900 pt-5">
          <div className="flex items-start gap-2 text-sm text-neutral-400">
            {hasIssues ? (
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-amber-300" />
            ) : (
              <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-400" />
            )}
            <p className="break-words">
              {hasIssues
                ? "Replay has migration or payload gaps to review before relying on empty-base rebuild."
                : "Empty-base replay and backfill preview did not report actionable gaps."}
            </p>
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <section className="space-y-3">
              <p className="text-xs font-bold uppercase tracking-widest text-neutral-500">Projection replay</p>
              <DetailRow label="Events processed" value={report.projection.events_processed} />
              <DetailRow label="Projectable events" value={report.projection.projectable_events} />
              <DetailRow label="Unsupported types" value={entriesLabel(report.projection.unsupported_event_types)} />
              <PreviewList title="Skipped events" items={report.projection.skipped_events} />
              <PreviewList title="Differences" items={report.projection.differences} />
            </section>

            <section className="space-y-3">
              <p className="text-xs font-bold uppercase tracking-widest text-neutral-500">Backfill preview</p>
              <DetailRow label="Movies checked" value={report.backfill.movies_checked} />
              <DetailRow label="Events checked" value={report.backfill.events_checked} />
              <DetailRow label="Events to create" value={report.backfill.events_to_create} />
              <PreviewList title="Sample events" items={report.backfill.sample_events} />
              <PreviewList title="Unsupported" items={report.backfill.unsupported} />
              <PreviewList title="Unavailable file snapshots" items={report.backfill.unavailable_file_snapshots} />
            </section>
          </div>
        </div>
      ) : null}
    </section>
  );
}

function Metric({ label, value, tone = "neutral" }: { label: string; value: number; tone?: "neutral" | "ok" | "warn" }) {
  const toneClass = tone === "ok"
    ? "border-emerald-900/80 text-emerald-300"
    : tone === "warn"
      ? "border-amber-900/80 text-amber-300"
      : "border-neutral-800 text-neutral-400";
  return (
    <span className={`inline-flex h-7 items-center border px-2 ${toneClass}`}>
      {label}: {value}
    </span>
  );
}

function DetailRow({ label, value }: { label: string; value: unknown }) {
  return (
    <p className="grid gap-1 text-sm sm:grid-cols-[10rem_minmax(0,1fr)]">
      <span className="text-xs font-bold uppercase tracking-widest text-neutral-600">{label}</span>
      <span className="break-words text-neutral-400">{formatValue(value)}</span>
    </p>
  );
}

function PreviewList({ title, items }: { title: string; items: Array<Record<string, unknown>> }) {
  const visible = items.slice(0, MAX_ITEMS);
  const hidden = Math.max(0, items.length - MAX_ITEMS);
  if (!items.length) {
    return (
      <div className="space-y-1">
        <p className="text-xs font-bold uppercase tracking-widest text-neutral-600">{title}</p>
        <p className="text-sm text-neutral-700">None</p>
      </div>
    );
  }
  return (
    <div className="space-y-2">
      <p className="text-xs font-bold uppercase tracking-widest text-neutral-600">{title}</p>
      <div className="space-y-2">
        {visible.map((item, index) => (
          <p key={`${title}-${index}`} className="break-words border border-neutral-900 bg-neutral-950/70 p-3 text-sm text-neutral-500">
            {formatValue(item)}
          </p>
        ))}
      </div>
      {hidden ? <p className="text-xs uppercase tracking-widest text-neutral-700">+{hidden} more</p> : null}
    </div>
  );
}
