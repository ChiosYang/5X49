"use client";

import { CalendarPlus, ChevronDown, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";

import { Button } from "@/components/ui/Button";
import { InlineFeedback } from "@/components/ui/Feedback";
import { useFilmViewings } from "@/hooks/useFilm";
import { Link } from "@/i18n/routing";
import { useViewingWrite } from "./useViewingWrite";
import { cn } from "@/lib/cn";
import {
  createViewingDateDraft,
  todayLocalDate,
  viewingDateDraftDirty,
  viewingDateDraftValid,
  viewingDraftWatchedAt,
  type ViewingDateMode,
} from "@/lib/diary";
import type { ViewingView } from "@/types/movie";

interface ViewingInlineEditorProps {
  className?: string;
  filmId: string;
  onCancel: () => void;
  onSaved?: () => void | Promise<void>;
  onBusyChange?: (busy: boolean) => void;
  viewing?: ViewingView | null;
}

export default function ViewingInlineEditor({
  className,
  filmId,
  onCancel,
  onSaved,
  onBusyChange,
  viewing,
}: ViewingInlineEditorProps) {
  const t = useTranslations("Diary");
  const [draft, setDraft] = useState(() => createViewingDateDraft(viewing));
  const [advancedOpen, setAdvancedOpen] = useState(() => draft.mode !== "date");
  const [actionsOpen, setActionsOpen] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const actions = useViewingWrite(filmId, viewing, onSaved);
  const { busy, completed: succeeded, feedback } = actions;
  useEffect(() => {
    onBusyChange?.(busy);
    return () => onBusyChange?.(false);
  }, [busy, onBusyChange]);
  const editable = viewing?.editable ?? true;
  const watchedAt = viewingDraftWatchedAt(draft);
  const valid = viewingDateDraftValid(draft);
  const dirty = viewingDateDraftDirty(draft, viewing);
  const save = () => { if (valid && dirty) void actions.save(watchedAt); };
  const remove = () => { void actions.remove(); };
  const setMode = (mode: ViewingDateMode) => setDraft((current) => ({ ...current, mode }));

  if (!editable) {
    return (
      <div className={cn("mt-4 space-y-3 border-t border-line pt-4", className)}>
        <InlineFeedback tone="warning">{t("readOnlySource")}</InlineFeedback>
        <Button variant="ghost" size="sm" onClick={onCancel}>{t("close")}</Button>
      </div>
    );
  }

  return (
    <div
      className={cn("mt-4 space-y-4 border-t border-line pt-4", className)}
      aria-label={viewing ? t("editViewing") : t("otherDate")}
    >
      <fieldset disabled={busy || succeeded} className="space-y-4">
      {draft.mode === "date" ? (
        <label className="block space-y-2">
          <span className="type-label text-ink-subtle">{t("date")}</span>
          <input
            type="date"
            max={todayLocalDate()}
            value={draft.dateValue}
            onChange={(event) => setDraft((current) => ({ ...current, dateValue: event.target.value }))}
            className="focus-ring h-11 w-full border border-line-strong bg-surface-raised px-3 text-ink"
          />
        </label>
      ) : null}

      {draft.mode === "year" ? (
        <label className="block space-y-2">
          <span className="type-label text-ink-subtle">{t("year")}</span>
          <input
            type="number"
            inputMode="numeric"
            pattern="[0-9]{4}"
            min="1"
            max={new Date().getFullYear()}
            value={draft.yearValue}
            onChange={(event) => setDraft((current) => ({
              ...current,
              yearValue: event.target.value.replace(/\D/g, "").slice(0, 4),
            }))}
            className="focus-ring h-11 w-full border border-line-strong bg-surface-raised px-3 text-ink"
          />
        </label>
      ) : null}

      {draft.mode === "unknown" ? (
        <p className="type-meta text-ink-subtle">{t("unknownDateSelected")}</p>
      ) : null}

      <div>
        <button
          type="button"
          className="focus-ring duration-fast inline-flex min-h-9 items-center gap-2 type-badge text-ink-muted transition-colors hover:text-ink"
          aria-expanded={advancedOpen}
          onClick={() => setAdvancedOpen((current) => !current)}
        >
          <ChevronDown className={cn("h-4 w-4 transition-transform", advancedOpen && "rotate-180")} />
          {advancedOpen ? t("hideDateOptions") : t("moreDateOptions")}
        </button>
        {advancedOpen ? (
          <fieldset className="mt-3 space-y-2">
            <legend className="sr-only">{t("dateMode")}</legend>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
              {(["date", "year", "unknown"] as ViewingDateMode[]).map((mode) => (
                <label
                  key={mode}
                  className="focus-within:border-ink flex min-h-10 cursor-pointer items-center gap-2 border border-line px-3 text-sm text-ink-muted"
                >
                  <input
                    type="radio"
                    name={`viewing-date-mode-${viewing?.id || filmId}`}
                    value={mode}
                    checked={draft.mode === mode}
                    onChange={() => setMode(mode)}
                  />
                  {t(`modes.${mode}`)}
                </label>
              ))}
            </div>
          </fieldset>
        ) : null}
      </div>

      </fieldset>
      <div aria-live="polite" className="min-h-5">
        {feedback ? <InlineFeedback tone={feedback.tone}>{feedback.text}</InlineFeedback> : null}
      </div>

      <ViewingReceipt filmId={filmId} actions={actions} />
      <div className="flex flex-col-reverse gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          {viewing && !succeeded ? (
            <button
              type="button"
              className="focus-ring duration-fast inline-flex min-h-9 items-center gap-2 type-badge text-ink-subtle transition-colors hover:text-ink"
              aria-expanded={actionsOpen}
              onClick={() => { setActionsOpen((current) => !current); setConfirmDelete(false); }}
            >
              <ChevronDown className={cn("h-4 w-4 transition-transform", actionsOpen && "rotate-180")} />
              {actionsOpen ? t("hideActions") : t("moreActions")}
            </button>
          ) : null}
          {actionsOpen && !succeeded ? (
            <div className="mt-2 flex flex-wrap items-center gap-2">
              {confirmDelete ? (
                <>
                  <Button variant="danger" size="sm" busy={busy} onClick={remove}>
                    {t("confirmDelete")}
                  </Button>
                  <Button variant="ghost" size="sm" disabled={busy} onClick={() => setConfirmDelete(false)}>{t("cancel")}</Button>
                </>
              ) : (
                <Button
                  variant="ghost"
                  size="sm"
                  icon={<Trash2 className="h-4 w-4" />}
                  disabled={busy} onClick={() => setConfirmDelete(true)}
                >
                  {t("delete")}
                </Button>
              )}
            </div>
          ) : null}
        </div>
        <div className="flex flex-col gap-2 sm:flex-row">
          <Button variant="ghost" size="sm" disabled={busy} onClick={onCancel}>{succeeded ? t("close") : t("cancel")}</Button>
          <Button
            variant="primary"
            size="sm"
            icon={<CalendarPlus className="h-4 w-4" />}
            busy={busy}
            disabled={busy || !valid || !dirty || succeeded}
            onClick={save}
          >
            {viewing ? t("save") : t("record")}
          </Button>
        </div>
      </div>
    </div>
  );
}

interface ViewingQuickAddProps {
  className?: string;
  filmId: string;
  onSaved?: () => void | Promise<void>;
}

export function ViewingQuickAdd({ className, filmId, onSaved }: ViewingQuickAddProps) {
  const t = useTranslations("Diary");
  const [otherDateOpen, setOtherDateOpen] = useState(false);
  const [editorBusy, setEditorBusy] = useState(false);
  const actions = useViewingWrite(filmId, null, onSaved);
  const { data: existingViewings } = useFilmViewings(filmId);
  const todayCount = existingViewings?.filter((item) => item.watched_at?.slice(0, 10) === todayLocalDate()).length || 0;
  const { busy, feedback, completed } = actions;
  const recordToday = () => { void actions.save(todayLocalDate()); };

  return (
    <div className={cn("w-full sm:w-auto", className)}>
      {todayCount > 0 ? <p className="mb-2 text-xs text-ink-subtle">{t("todayCount", { count: todayCount })}</p> : null}
      <div className="flex flex-col gap-2 sm:flex-row">
        <Button
          variant="primary"
          icon={<CalendarPlus className="h-4 w-4" />}
          busy={busy}
          disabled={otherDateOpen || completed || busy}
          responsiveWidth
          onClick={recordToday}
        >
          {t("watchToday")}
        </Button>
        <Button
          variant="secondary"
          responsiveWidth
          disabled={busy || editorBusy}
          aria-expanded={otherDateOpen}
          onClick={() => setOtherDateOpen((current) => !current)}
        >
          {otherDateOpen ? t("cancelOtherDate") : t("otherDate")}
        </Button>
      </div>
      <div aria-live="polite" className="mt-2 min-h-5">
        {feedback ? <InlineFeedback tone={feedback.tone}>{feedback.text}</InlineFeedback> : null}
      </div>
      <ViewingReceipt filmId={filmId} actions={actions} />
      {completed && !otherDateOpen ? <Button size="sm" variant="ghost" disabled={busy} onClick={actions.reset}>{t("recordAnother")}</Button> : null}
      {otherDateOpen ? (
        <ViewingInlineEditor
          key="new-viewing"
          filmId={filmId}
          onCancel={() => setOtherDateOpen(false)}
          onSaved={onSaved}
          onBusyChange={setEditorBusy}
        />
      ) : null}
    </div>
  );
}

function ViewingReceipt({ filmId, actions }: { filmId: string; actions: ReturnType<typeof useViewingWrite> }) {
  const t = useTranslations("Diary");
  return <div className="space-y-2">
    {actions.refreshFailed ? <div role="status">
      <InlineFeedback tone="warning">{t("savedRefreshFailed")}</InlineFeedback>
      <Button size="sm" variant="ghost" disabled={actions.busy} onClick={actions.retryRefresh}>{t("retryRefresh")}</Button>
    </div> : null}
    {actions.receipt ? <div className="flex flex-wrap gap-3">
      <details className="w-full">
        <summary className="focus-ring cursor-pointer py-2 text-sm underline">{t("viewSaved")}</summary>
        <p className="py-2 text-sm text-ink-muted">{t("date")}: {actions.receipt.watched_at || t("unknownDate")}</p>
        <Link className="focus-ring inline-flex min-h-10 items-center text-sm underline" href={`/diary?film=${encodeURIComponent(filmId)}`}>{t("viewAll")}</Link>
      </details>
      <Button size="sm" variant="ghost" disabled={actions.busy} onClick={actions.undo}>{t("undoNew")}</Button>
    </div> : null}
  </div>;
}
