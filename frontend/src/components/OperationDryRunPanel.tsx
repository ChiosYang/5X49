"use client";

import { useState } from "react";
import { AlertCircle, CheckCircle2, Loader2 } from "lucide-react";
import { API } from "@/lib/api";
import type { OperationDryRunReport } from "@/types/movie";

interface OperationDryRunPanelProps {
  commandId?: string | null;
  correlationId?: string | null;
}

const CHECK_LABELS: Record<string, string> = {
  poster_restore: "Poster restore",
  nfo_writer_trace: "NFO trace",
  root_move_reverse: "Root move reverse",
  scrape_side_effects: "Side effects",
};

export default function OperationDryRunPanel({ commandId, correlationId }: OperationDryRunPanelProps) {
  const [report, setReport] = useState<OperationDryRunReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!commandId && !correlationId) return null;

  const runCheck = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(API.libraryOperationDryRunUrl({
        command_id: commandId,
        correlation_id: correlationId,
        limit: 500,
      }));
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(body?.detail || "Operation check failed");
      }
      setReport(await response.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Operation check failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mt-5 border border-neutral-900 bg-neutral-950/60 p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-bold uppercase tracking-widest text-neutral-500">Dry-run</p>
          {report ? (
            <p className="mt-1 text-sm text-neutral-300">
              {report.status.toUpperCase()} · {report.events_analyzed} events analyzed
            </p>
          ) : (
            <p className="mt-1 text-sm text-neutral-500">No check has been run.</p>
          )}
        </div>
        <button
          type="button"
          onClick={runCheck}
          disabled={loading}
          className="inline-flex h-9 items-center gap-2 border border-neutral-800 px-3 text-xs font-bold uppercase tracking-widest text-neutral-300 transition-colors hover:border-neutral-500 hover:text-white disabled:cursor-wait disabled:opacity-60"
        >
          {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
          Check
        </button>
      </div>

      {error ? (
        <p className="mt-3 text-sm text-red-300">{error}</p>
      ) : null}

      {report ? (
        <div className="mt-4 space-y-4">
          <div className="grid gap-2 sm:grid-cols-2">
            {Object.entries(report.checks).map(([key, check]) => (
              <div key={key} className="min-w-0 border border-neutral-900 bg-black/40 p-3">
                <div className="flex items-center gap-2">
                  {check.can ? (
                    <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-400" />
                  ) : (
                    <AlertCircle className="h-4 w-4 shrink-0 text-neutral-500" />
                  )}
                  <p className="truncate text-xs font-bold uppercase tracking-widest text-neutral-300">
                    {CHECK_LABELS[key] || key}
                  </p>
                </div>
                <p className="mt-2 break-words text-sm leading-relaxed text-neutral-500">
                  {check.message}
                </p>
                <p className="mt-2 text-xs uppercase tracking-widest text-neutral-700">
                  {check.status}
                </p>
              </div>
            ))}
          </div>

          {report.missing_payload.length || report.unsafe_actions.length ? (
            <div className="space-y-2 border-t border-neutral-900 pt-4">
              {report.missing_payload.length ? (
                <p className="text-sm text-neutral-400">
                  Missing payload: {report.missing_payload.length}
                </p>
              ) : null}
              {report.unsafe_actions.length ? (
                <p className="text-sm text-neutral-400">
                  Unsafe actions: {report.unsafe_actions.length}
                </p>
              ) : null}
            </div>
          ) : null}

          <div className="flex flex-wrap gap-2 border-t border-neutral-900 pt-4 text-xs uppercase tracking-widest text-neutral-600">
            <span>{report.side_effects.length} side effects</span>
            <span>{report.recoverable_fields.length} recoverable fields</span>
          </div>
        </div>
      ) : null}
    </div>
  );
}
