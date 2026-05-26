"use client";

import { useState } from "react";
import { useSWRConfig } from "swr";
import { AlertCircle, CheckCircle2, ChevronDown, Loader2, RotateCcw } from "lucide-react";
import { useMovieTimelineRestore, useMovieTimelineRestorePreview } from "@/hooks/useMovie";
import { API } from "@/lib/api";
import type {
  EventRecord,
  MovieTimelineFileRestoreItem,
  MovieTimelineRestoreFileType,
  MovieTimelineRestorePreviewReport,
  MovieTimelineRestoreReport,
} from "@/types/movie";

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
  if (status === "safe" || status === "restored") return "border-emerald-900/80 text-emerald-300";
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

function isExecutableFileType(fileType?: string | null): fileType is MovieTimelineRestoreFileType {
  return fileType === "poster" || fileType === "backdrop" || fileType === "nfo";
}

function executableFileTypes(report: MovieTimelineRestorePreviewReport): MovieTimelineRestoreFileType[] {
  return Array.from(new Set(
    report.restorable_files
      .map((file) => file.file_type)
      .filter(isExecutableFileType)
  ));
}

export default function TimelineRestorePreviewPanel({ event, movieId }: TimelineRestorePreviewPanelProps) {
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [selectedFields, setSelectedFields] = useState<string[]>([]);
  const [selectedFiles, setSelectedFiles] = useState<MovieTimelineRestoreFileType[]>([]);
  const [allowPartial, setAllowPartial] = useState(false);
  const { mutate } = useSWRConfig();
  const { trigger, data: report, isMutating, error } = useMovieTimelineRestorePreview(movieId, event.id);
  const {
    trigger: triggerRestore,
    data: restoreReport,
    isMutating: isRestoring,
    error: restoreError,
  } = useMovieTimelineRestore(movieId, event.id);
  const canPreview = canPreviewEvent(event, movieId);

  if (!canPreview) return null;

  const runPreview = async () => {
    const nextReport = await trigger({ before_event_id: event.id }).catch(() => undefined);
    if (nextReport) {
      setSelectedFields(nextReport.field_restore.map((diff) => diff.field));
      setSelectedFiles(executableFileTypes(nextReport));
      setAllowPartial(false);
      setDetailsOpen(true);
    }
  };

  const errorMessage = error instanceof Error ? error.message : null;
  const restoreErrorMessage = restoreError instanceof Error ? restoreError.message : null;

  return (
    <div className="mt-3 border border-neutral-900 bg-black/40 p-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-bold uppercase tracking-widest text-neutral-500">Historical preview</p>
          <p className="mt-1 break-words text-sm text-neutral-500">
            Start with a dry-run. Execution requires selected actions and confirmation.
          </p>
        </div>
        <button
          type="button"
          onClick={runPreview}
          disabled={isMutating}
          className="inline-flex h-9 items-center gap-2 border border-neutral-800 px-3 text-xs font-bold uppercase tracking-widest text-neutral-300 transition-colors hover:border-neutral-500 hover:text-white disabled:cursor-wait disabled:opacity-60"
        >
          {isMutating ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RotateCcw className="h-3.5 w-3.5" />}
          Preview point
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

          <TimelineRestoreExecutionPanel
            event={event}
            report={report}
            selectedFields={selectedFields}
            selectedFiles={selectedFiles}
            allowPartial={allowPartial}
            restoreReport={restoreReport}
            restoreErrorMessage={restoreErrorMessage}
            isRestoring={isRestoring}
            onToggleField={(field) => {
              setSelectedFields((current) => current.includes(field)
                ? current.filter((item) => item !== field)
                : [...current, field]);
            }}
            onToggleFile={(fileType) => {
              setSelectedFiles((current) => current.includes(fileType)
                ? current.filter((item) => item !== fileType)
                : [...current, fileType]);
            }}
            onAllowPartialChange={setAllowPartial}
            onRestore={async () => {
              const confirmed = window.confirm(
                "Restore this movie to the selected historical point? This appends compensation events and may copy selected backup files."
              );
              if (!confirmed) return;
              const result = await triggerRestore({
                before_event_id: event.id,
                restore_fields: selectedFields,
                restore_files: selectedFiles,
                allow_partial: allowPartial,
              }).catch(() => undefined);
              if (result && movieId) {
                await mutate(API.libraryMovie(movieId));
                await mutate(API.libraryMovieAuditEvents(movieId));
              }
            }}
          />
        </div>
      ) : null}
    </div>
  );
}

function TimelineRestoreExecutionPanel({
  report,
  selectedFields,
  selectedFiles,
  allowPartial,
  restoreReport,
  restoreErrorMessage,
  isRestoring,
  onToggleField,
  onToggleFile,
  onAllowPartialChange,
  onRestore,
}: {
  event: EventRecord;
  report: MovieTimelineRestorePreviewReport;
  selectedFields: string[];
  selectedFiles: MovieTimelineRestoreFileType[];
  allowPartial: boolean;
  restoreReport?: MovieTimelineRestoreReport;
  restoreErrorMessage?: string | null;
  isRestoring: boolean;
  onToggleField: (field: string) => void;
  onToggleFile: (fileType: MovieTimelineRestoreFileType) => void;
  onAllowPartialChange: (value: boolean) => void;
  onRestore: () => Promise<void>;
}) {
  const executableFiles = executableFileTypes(report);
  const hasActions = selectedFields.length > 0 || selectedFiles.length > 0;
  const canExecute = report.target_state !== null && hasActions;

  return (
    <section className="space-y-4 border-t border-neutral-900 pt-4">
      <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-start">
        <div className="min-w-0">
          <p className="text-xs font-bold uppercase tracking-widest text-neutral-500">Execute historical restore</p>
          <p className="mt-1 break-words text-sm text-neutral-500">
            Writes compensation events for fields and copies selected poster, backdrop, or NFO backups.
          </p>
        </div>
        <button
          type="button"
          onClick={onRestore}
          disabled={!canExecute || isRestoring}
          className="inline-flex h-9 items-center gap-2 border border-amber-800/80 bg-amber-950/20 px-3 text-xs font-bold uppercase tracking-widest text-amber-200 transition-colors hover:border-amber-500 hover:text-amber-100 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isRestoring ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RotateCcw className="h-3.5 w-3.5" />}
          Execute restore
        </button>
      </div>

      {report.target_state === null ? (
        <p className="break-words text-sm text-amber-300">Cannot execute because the target state could not be rebuilt.</p>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-2">
        <ChecklistGroup
          title="Fields"
          emptyLabel="No restorable field changes."
          items={report.field_restore.map((diff) => ({
            id: diff.field,
            label: diff.field,
            detail: `${formatValue(diff.current)} -> ${formatValue(diff.target)}`,
          }))}
          selected={selectedFields}
          onToggle={onToggleField}
        />

        <ChecklistGroup
          title="Files"
          emptyLabel="No executable file restores. Root video remains preview-only."
          items={executableFiles.map((fileType) => {
            const item = report.restorable_files.find((file) => file.file_type === fileType);
            return {
              id: fileType,
              label: fileType,
              detail: item?.path || item?.backup_path || "Backup is available",
            };
          })}
          selected={selectedFiles}
          onToggle={onToggleFile}
        />
      </div>

      <label className="flex items-start gap-2 text-sm text-neutral-400">
        <input
          type="checkbox"
          checked={allowPartial}
          onChange={(event) => onAllowPartialChange(event.target.checked)}
          className="mt-1 h-4 w-4 accent-amber-400"
        />
        <span className="min-w-0 break-words">Allow partial restore if selected actions conflict during preflight.</span>
      </label>

      {restoreErrorMessage ? (
        <p className="break-words text-sm text-red-300">{restoreErrorMessage}</p>
      ) : null}

      {restoreReport ? <RestoreResult report={restoreReport} /> : null}
    </section>
  );
}

function ChecklistGroup<T extends string>({
  title,
  emptyLabel,
  items,
  selected,
  onToggle,
}: {
  title: string;
  emptyLabel: string;
  items: Array<{ id: T; label: string; detail?: string }>;
  selected: T[];
  onToggle: (id: T) => void;
}) {
  return (
    <div className="space-y-2">
      <p className="text-xs font-bold uppercase tracking-widest text-neutral-500">{title}</p>
      {items.length ? (
        <div className="space-y-2">
          {items.map((item) => (
            <label key={item.id} className="flex items-start gap-2 border border-neutral-900 bg-neutral-950/70 p-3 text-sm text-neutral-400">
              <input
                type="checkbox"
                checked={selected.includes(item.id)}
                onChange={() => onToggle(item.id)}
                className="mt-1 h-4 w-4 shrink-0 accent-amber-400"
              />
              <span className="min-w-0">
                <span className="block break-all text-xs font-bold uppercase tracking-widest text-neutral-300">{item.label}</span>
                {item.detail ? <span className="mt-1 block break-words text-neutral-600">{item.detail}</span> : null}
              </span>
            </label>
          ))}
        </div>
      ) : (
        <p className="text-sm text-neutral-600">{emptyLabel}</p>
      )}
    </div>
  );
}

function RestoreResult({ report }: { report: MovieTimelineRestoreReport }) {
  return (
    <div className="space-y-3 border border-neutral-900 bg-neutral-950/70 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className={`inline-flex h-7 items-center border px-2 text-xs font-bold uppercase tracking-widest ${statusClass(report.status)}`}>
          {report.status}
        </span>
        <span className="text-xs uppercase tracking-widest text-neutral-600">
          Restored {report.restored.length}
        </span>
        <span className="text-xs uppercase tracking-widest text-neutral-600">
          Skipped {report.skipped.length}
        </span>
        <span className="text-xs uppercase tracking-widest text-neutral-600">
          Conflicts {report.conflicts.length}
        </span>
      </div>
      {report.restore_correlation_id ? (
        <p className="break-all text-xs uppercase tracking-widest text-neutral-600">
          Correlation {report.restore_correlation_id}
        </p>
      ) : null}
      <IssueList title="Restored actions" items={report.restored} hidden={0} />
      <IssueList title="Skipped actions" items={report.skipped} hidden={0} />
      <IssueList title="Conflicts" items={report.conflicts} hidden={0} />
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
