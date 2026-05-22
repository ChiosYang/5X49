"use client";

import { useState } from "react";
import { AlertCircle, CheckCircle2, Loader2, RotateCcw } from "lucide-react";
import { API } from "@/lib/api";
import type { OperationDryRunReport, OperationRestoreAction, OperationRestoreReport } from "@/types/movie";

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

const RESTORE_LABELS: Record<OperationRestoreAction, string> = {
  restore_artwork_selection: "artwork selection",
  restore_metadata: "metadata fields",
  restore_poster: "poster",
  restore_nfo: "NFO",
  reverse_root_move: "root video",
};

function restoreActionsForReport(report: OperationDryRunReport): OperationRestoreAction[] {
  const actions: OperationRestoreAction[] = [];
  if (report.recoverable_fields.some((field) => (
    field.type === "MetadataMatched"
    && field.can_restore_value === true
  ))) {
    actions.push("restore_metadata");
  }
  if (report.recoverable_fields.some((field) => (
    field.type === "ArtworkSelected"
    && field.can_restore_value === true
  ))) {
    actions.push("restore_artwork_selection");
  }
  if (report.can_restore_poster) actions.push("restore_poster");
  if (report.side_effects.some((effect) => (
    effect.type === "NfoWritten"
    && typeof effect.backup_path === "string"
    && effect.backup_path.length > 0
  ))) {
    actions.push("restore_nfo");
  }
  if (report.can_reverse_root_move) actions.push("reverse_root_move");
  return actions;
}

async function responseError(response: Response, fallback: string) {
  const body = await response.json().catch(() => null) as { detail?: unknown } | null;
  if (typeof body?.detail === "string") return body.detail;
  if (body?.detail) return JSON.stringify(body.detail);
  return fallback;
}

export default function OperationDryRunPanel({ commandId, correlationId }: OperationDryRunPanelProps) {
  const [report, setReport] = useState<OperationDryRunReport | null>(null);
  const [restoreResult, setRestoreResult] = useState<OperationRestoreReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [restoring, setRestoring] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [restoreError, setRestoreError] = useState<string | null>(null);

  if (!commandId && !correlationId) return null;

  const restoreActions = report ? restoreActionsForReport(report) : [];
  const hasRestored = Boolean(restoreResult?.restored.length);
  const canRestore = restoreActions.length > 0 && !hasRestored;

  const runCheck = async () => {
    setLoading(true);
    setError(null);
    setRestoreError(null);
    try {
      const response = await fetch(API.libraryOperationDryRunUrl({
        command_id: commandId,
        correlation_id: correlationId,
        limit: 500,
      }));
      if (!response.ok) {
        throw new Error(await responseError(response, "Operation check failed"));
      }
      setReport(await response.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Operation check failed");
    } finally {
      setLoading(false);
    }
  };

  const runRestore = async () => {
    if (!report || !canRestore) return;
    const actionSummary = restoreActions.map((action) => RESTORE_LABELS[action]).join(", ");
    const confirmed = window.confirm(`Restore ${actionSummary} from recorded recovery data?`);
    if (!confirmed) return;

    setRestoring(true);
    setRestoreError(null);
    try {
      const response = await fetch(API.libraryOperationRestore(), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          command_id: commandId,
          correlation_id: correlationId,
          actions: restoreActions,
          limit: 500,
        }),
      });
      if (!response.ok) {
        throw new Error(await responseError(response, "Operation restore failed"));
      }
      setRestoreResult(await response.json());
      await runCheck();
    } catch (err) {
      setRestoreError(err instanceof Error ? err.message : "Operation restore failed");
    } finally {
      setRestoring(false);
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

          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-neutral-900 pt-4">
            <div className="min-w-0">
              <p className="text-xs font-bold uppercase tracking-widest text-neutral-500">Restore</p>
              <p className="mt-1 break-words text-sm text-neutral-400">
                {hasRestored
                  ? `${restoreResult?.restored.length || 0} restored · ${restoreResult?.skipped.length || 0} skipped`
                  : canRestore
                    ? restoreActions.map((action) => RESTORE_LABELS[action]).join(", ")
                    : "No restorable file actions"}
              </p>
            </div>
            <button
              type="button"
              onClick={runRestore}
              disabled={!canRestore || loading || restoring}
              className="inline-flex h-9 items-center gap-2 border border-neutral-800 px-3 text-xs font-bold uppercase tracking-widest text-neutral-300 transition-colors hover:border-neutral-500 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
            >
              {restoring ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RotateCcw className="h-3.5 w-3.5" />}
              Restore
            </button>
          </div>

          {restoreError ? (
            <p className="text-sm text-red-300">{restoreError}</p>
          ) : null}

          {restoreResult ? (
            <div className="space-y-2 border-t border-neutral-900 pt-4 text-sm text-neutral-400">
              {restoreResult.restored.length ? (
                <p>{restoreResult.restored.length} compensation events recorded.</p>
              ) : null}
              {restoreResult.skipped.length ? (
                <p>{restoreResult.skipped.length} actions skipped.</p>
              ) : null}
            </div>
          ) : null}

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
