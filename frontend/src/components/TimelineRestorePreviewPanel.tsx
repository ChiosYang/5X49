"use client";

import { useState } from "react";
import { AlertCircle, CheckCircle2, ChevronDown, Loader2, RotateCcw } from "lucide-react";
import { useMovieTimelineRestorePreview } from "@/hooks/useMovie";
import type { EventRecord, MovieTimelineFileRestoreItem, MovieTimelineRestorePreviewReport } from "@/types/movie";

interface TimelineRestorePreviewPanelProps {
  event: EventRecord;
  movieId?: string | null;
}

const MAX_VISIBLE_ITEMS = 8;

const STATUS_COPY: Record<string, string> = {
  safe: "Preview is fully recoverable from recorded data.",
  partial: "Some fields or files need attention before restore.",
  unsafe: "File conflicts may make this restore unsafe.",
  unknown: "No supported restore actions were identified.",
};

function statusClass(status: string) {
  if (status === "safe") return "border-emerald-900/80 text-emerald-300";
  if (status === "partial") return "border-amber-900/80 text-amber-300";
  if (status === "unsafe") return "border-red-900/80 text-red-300";
  return "border-neutral-800 text-neutral-400";
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

function visibleItems<T>(items: T[]) {
  return {
    shown: items.slice(0, MAX_VISIBLE_ITEMS),
    hidden: Math.max(0, items.length - MAX_VISIBLE_ITEMS),
  };
}

function issueCount(report: MovieTimelineRestorePreviewReport) {
  return report.unsupported_events + report.skipped_events.length + report.missing_payload.length;
}

function canPreviewEvent(event: EventRecord, movieId?: string | null) {
  return event.aggregate_type === "movie" && Boolean(movieId);
}

function isBackfillEvent(event: EventRecord) {
  return event.type === "MovieStateBackfilled" || event.type === "MovieFileSnapshotBackfilled";
}

export default function TimelineRestorePreviewPanel({ event, movieId }: TimelineRestorePreviewPanelProps) {
  const [detailsOpen, setDetailsOpen] = useState(false);
  const { trigger, data: report, isMutating, error } = useMovieTimelineRestorePreview(movieId);
  const canPreview = canPreviewEvent(event, movieId);

  if (!canPreview) return null;

  const runPreview = async () => {
    await trigger({ before_event_id: event.id }).catch(() => undefined);
  };

  const errorMessage = error instanceof Error ? error.message : null;

  return (
    <div className="mt-3 border border-neutral-900 bg-black/40 p-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-bold uppercase tracking-widest text-neutral-500">Historical preview</p>
          <p className="mt-1 break-words text-sm text-neutral-500">
            Dry-run only. No fields, files, or events will be changed.
          </p>
        </div>
        <button
          type="button"
          onClick={runPreview}
          disabled={isMutating}
          className="inline-flex h-9 items-center gap-2 border border-neutral-800 px-3 text-xs font-bold uppercase tracking-widest text-neutral-300 transition-colors hover:border-neutral-500 hover:text-white disabled:cursor-wait disabled:opacity-60"
        >
          {isMutating ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RotateCcw className="h-3.5 w-3.5" />}
          Restore to this point
        </button>
      </div>

      {errorMessage ? (
        <p className="mt-3 break-words text-sm text-red-300">{errorMessage}</p>
      ) : null}

      {report ? (
        <div className="mt-4 space-y-4 border-t border-neutral-900 pt-4">
          {isBackfillEvent(event) ? (
            <div className="flex items-start gap-2 border border-amber-950/80 bg-amber-950/10 p-3 text-sm text-amber-200/90">
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
              <p className="break-words">
                This point is a migration snapshot. It improves replay from the migration point forward, but it is not original historical evidence.
              </p>
            </div>
          ) : null}

          <div className="flex flex-wrap items-center gap-2">
            <span className={`inline-flex h-7 items-center border px-2 text-xs font-bold uppercase tracking-widest ${statusClass(report.status)}`}>
              {report.status}
            </span>
            <span className="text-xs uppercase tracking-widest text-neutral-600">
              {report.field_restore.length} fields
            </span>
            <span className="text-xs uppercase tracking-widest text-neutral-600">
              {report.restorable_files.length} files
            </span>
            <span className="text-xs uppercase tracking-widest text-neutral-600">
              {report.missing_file_backups.length} missing backups
            </span>
            <span className="text-xs uppercase tracking-widest text-neutral-600">
              {issueCount(report)} issues
            </span>
          </div>

          <div className="flex items-start gap-2 text-sm leading-relaxed text-neutral-400">
            {report.status === "safe" ? (
              <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-400" />
            ) : (
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-amber-300" />
            )}
            <p className="break-words">
              {report.target_state === null
                ? "Target state could not be rebuilt from the event timeline."
                : STATUS_COPY[report.status] || STATUS_COPY.unknown}
            </p>
          </div>

          <button
            type="button"
            onClick={() => setDetailsOpen((current) => !current)}
            className="inline-flex items-center gap-2 text-xs font-bold uppercase tracking-widest text-neutral-400 transition-colors hover:text-white"
          >
            <ChevronDown className={`h-4 w-4 transition-transform ${detailsOpen ? "rotate-0" : "-rotate-90"}`} />
            Preview details
          </button>

          {detailsOpen ? <PreviewDetails report={report} /> : null}
        </div>
      ) : null}
    </div>
  );
}

function PreviewDetails({ report }: { report: MovieTimelineRestorePreviewReport }) {
  const visibleFields = visibleItems(report.field_restore);
  const visibleRestorableFiles = visibleItems(report.restorable_files);
  const visibleMissingFiles = visibleItems(report.missing_file_backups);
  const visibleUnsafeFiles = visibleItems(report.file_restore.unsafe_files);
  const visibleSkipped = visibleItems(report.skipped_events);
  const visibleMissingPayload = visibleItems(report.missing_payload);

  return (
    <div className="space-y-4 border-t border-neutral-900 pt-4">
      <section className="space-y-2">
        <p className="text-xs font-bold uppercase tracking-widest text-neutral-500">Field changes</p>
        {visibleFields.shown.length ? (
          <div className="space-y-2">
            {visibleFields.shown.map((diff) => (
              <div key={diff.field} className="grid gap-2 border border-neutral-900 bg-neutral-950/70 p-3 text-sm sm:grid-cols-[9rem_minmax(0,1fr)]">
                <p className="break-all text-xs font-bold uppercase tracking-widest text-neutral-400">{diff.field}</p>
                <div className="grid min-w-0 gap-1 text-neutral-500">
                  <p className="break-words">
                    <span className="text-neutral-700">Current:</span> {formatValue(diff.current)}
                  </p>
                  <p className="break-words">
                    <span className="text-neutral-700">Target:</span> {formatValue(diff.target)}
                  </p>
                </div>
              </div>
            ))}
            {visibleFields.hidden ? (
              <p className="text-xs uppercase tracking-widest text-neutral-700">+{visibleFields.hidden} more fields</p>
            ) : null}
          </div>
        ) : (
          <p className="text-sm text-neutral-600">No field changes were identified.</p>
        )}
      </section>

      <FileGroup title="Restorable files" files={visibleRestorableFiles.shown} hidden={visibleRestorableFiles.hidden} />
      <FileGroup title="Missing file backups" files={visibleMissingFiles.shown} hidden={visibleMissingFiles.hidden} />
      <FileGroup title="Unsafe file checks" files={visibleUnsafeFiles.shown} hidden={visibleUnsafeFiles.hidden} />

      {report.unsupported_events || visibleSkipped.shown.length || visibleMissingPayload.shown.length ? (
        <section className="space-y-2">
          <p className="text-xs font-bold uppercase tracking-widest text-neutral-500">Replay issues</p>
          {report.unsupported_events ? (
            <p className="break-words text-sm text-neutral-500">
              Unsupported events: {Object.entries(report.unsupported_event_types).map(([type, count]) => `${type} ${count}`).join(", ")}
            </p>
          ) : null}
          <IssueList title="Skipped events" items={visibleSkipped.shown} hidden={visibleSkipped.hidden} />
          <IssueList title="Missing payload" items={visibleMissingPayload.shown} hidden={visibleMissingPayload.hidden} />
        </section>
      ) : null}
    </div>
  );
}

function FileGroup({ title, files, hidden }: { title: string; files: MovieTimelineFileRestoreItem[]; hidden: number }) {
  if (!files.length && !hidden) return null;
  return (
    <section className="space-y-2">
      <p className="text-xs font-bold uppercase tracking-widest text-neutral-500">{title}</p>
      <div className="space-y-2">
        {files.map((file) => (
          <div key={`${file.event_id}-${file.file_type || file.type}`} className="space-y-1 border border-neutral-900 bg-neutral-950/70 p-3 text-sm text-neutral-500">
            <p className="break-words text-xs font-bold uppercase tracking-widest text-neutral-300">
              {file.file_type || file.type}
            </p>
            {file.path ? <p className="break-all">Path: {file.path}</p> : null}
            {file.backup_path ? <p className="break-all">Backup: {file.backup_path}</p> : null}
            {file.source_path ? <p className="break-all">Source: {file.source_path}</p> : null}
            {file.target_path ? <p className="break-all">Target: {file.target_path}</p> : null}
            {file.reason ? <p className="break-words text-neutral-600">{file.reason}</p> : null}
          </div>
        ))}
      </div>
      {hidden ? <p className="text-xs uppercase tracking-widest text-neutral-700">+{hidden} more files</p> : null}
    </section>
  );
}

function IssueList({ title, items, hidden }: { title: string; items: Array<Record<string, unknown>>; hidden: number }) {
  if (!items.length && !hidden) return null;
  return (
    <div className="space-y-1">
      <p className="text-xs uppercase tracking-widest text-neutral-600">{title}</p>
      {items.map((item, index) => (
        <p key={`${title}-${index}`} className="break-words text-sm text-neutral-500">
          {formatValue(item)}
        </p>
      ))}
      {hidden ? <p className="text-xs uppercase tracking-widest text-neutral-700">+{hidden} more issues</p> : null}
    </div>
  );
}
