"use client";

import { CalendarPlus, ChevronDown, Trash2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";

import { Button } from "@/components/ui/Button";
import { InlineFeedback } from "@/components/ui/Feedback";
import {
  invalidateViewingCaches,
  useCreateFilmViewing,
  useDeleteViewing,
  useUpdateViewing,
} from "@/hooks/useFilm";
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
  viewing?: ViewingView | null;
}

export default function ViewingInlineEditor({
  className,
  filmId,
  onCancel,
  onSaved,
  viewing,
}: ViewingInlineEditorProps) {
  const t = useTranslations("Diary");
  const [draft, setDraft] = useState(() => createViewingDateDraft(viewing));
  const [advancedOpen, setAdvancedOpen] = useState(() => draft.mode !== "date");
  const [actionsOpen, setActionsOpen] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [feedback, setFeedback] = useState<{ tone: "success" | "error"; text: string } | null>(null);
  const closeTimer = useRef<number | null>(null);
  const createViewing = useCreateFilmViewing(filmId);
  const updateViewing = useUpdateViewing(viewing?.id);
  const deleteViewing = useDeleteViewing(viewing?.id);
  const busy = createViewing.isMutating || updateViewing.isMutating || deleteViewing.isMutating;
  const editable = viewing?.editable ?? true;
  const succeeded = feedback?.tone === "success";
  const watchedAt = viewingDraftWatchedAt(draft);
  const valid = viewingDateDraftValid(draft);
  const dirty = viewingDateDraftDirty(draft, viewing);

  useEffect(() => () => {
    if (closeTimer.current !== null) window.clearTimeout(closeTimer.current);
  }, []);

  const complete = async (message: string) => {
    setFeedback({ tone: "success", text: message });
    await invalidateViewingCaches(filmId);
    await onSaved?.();
    closeTimer.current = window.setTimeout(onCancel, 650);
  };

  const save = async () => {
    if (succeeded || !valid || !dirty) return;
    setFeedback(null);
    try {
      if (viewing) {
        await updateViewing.trigger({ watched_at: watchedAt });
        await complete(t("updated"));
      } else {
        await createViewing.trigger({ watched_at: watchedAt });
        await complete(t("created"));
      }
    } catch (error) {
      setFeedback({ tone: "error", text: error instanceof Error ? error.message : t("saveFailed") });
    }
  };

  const remove = async () => {
    setFeedback(null);
    try {
      await deleteViewing.trigger();
      await complete(t("deleted"));
    } catch (error) {
      setFeedback({ tone: "error", text: error instanceof Error ? error.message : t("deleteFailed") });
    }
  };

  const setMode = (mode: ViewingDateMode) => {
    setDraft((current) => ({ ...current, mode }));
    setFeedback(null);
  };

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

      <div aria-live="polite" className="min-h-5">
        {feedback ? <InlineFeedback tone={feedback.tone}>{feedback.text}</InlineFeedback> : null}
      </div>

      <div className="flex flex-col-reverse gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          {viewing ? (
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
          {actionsOpen ? (
            <div className="mt-2 flex flex-wrap items-center gap-2">
              {confirmDelete ? (
                <>
                  <Button variant="danger" size="sm" busy={deleteViewing.isMutating} onClick={remove}>
                    {t("confirmDelete")}
                  </Button>
                  <Button variant="ghost" size="sm" onClick={() => setConfirmDelete(false)}>{t("cancel")}</Button>
                </>
              ) : (
                <Button
                  variant="ghost"
                  size="sm"
                  icon={<Trash2 className="h-4 w-4" />}
                  onClick={() => setConfirmDelete(true)}
                >
                  {t("delete")}
                </Button>
              )}
            </div>
          ) : null}
        </div>
        <div className="flex flex-col gap-2 sm:flex-row">
          <Button variant="ghost" size="sm" onClick={onCancel}>{t("cancel")}</Button>
          <Button
            variant="primary"
            size="sm"
            icon={<CalendarPlus className="h-4 w-4" />}
            busy={busy && !deleteViewing.isMutating}
            disabled={!valid || !dirty || succeeded}
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
  const createViewing = useCreateFilmViewing(filmId);
  const [otherDateOpen, setOtherDateOpen] = useState(false);
  const [feedback, setFeedback] = useState<{ tone: "success" | "error"; text: string } | null>(null);
  const feedbackTimer = useRef<number | null>(null);

  useEffect(() => () => {
    if (feedbackTimer.current !== null) window.clearTimeout(feedbackTimer.current);
  }, []);

  const recordToday = async () => {
    if (createViewing.isMutating) return;
    setFeedback(null);
    try {
      await createViewing.trigger({ watched_at: todayLocalDate() });
      await invalidateViewingCaches(filmId);
      await onSaved?.();
      setFeedback({ tone: "success", text: t("createdToday") });
      if (feedbackTimer.current !== null) window.clearTimeout(feedbackTimer.current);
      feedbackTimer.current = window.setTimeout(() => setFeedback(null), 1800);
    } catch (error) {
      setFeedback({ tone: "error", text: error instanceof Error ? error.message : t("saveFailed") });
    }
  };

  return (
    <div className={cn("w-full sm:w-auto", className)}>
      <div className="flex flex-col gap-2 sm:flex-row">
        <Button
          variant="primary"
          icon={<CalendarPlus className="h-4 w-4" />}
          busy={createViewing.isMutating}
          disabled={otherDateOpen}
          responsiveWidth
          onClick={recordToday}
        >
          {t("watchToday")}
        </Button>
        <Button
          variant="secondary"
          responsiveWidth
          disabled={createViewing.isMutating}
          aria-expanded={otherDateOpen}
          onClick={() => { setOtherDateOpen((current) => !current); setFeedback(null); }}
        >
          {otherDateOpen ? t("cancelOtherDate") : t("otherDate")}
        </Button>
      </div>
      <div aria-live="polite" className="mt-2 min-h-5">
        {feedback ? <InlineFeedback tone={feedback.tone}>{feedback.text}</InlineFeedback> : null}
      </div>
      {otherDateOpen ? (
        <ViewingInlineEditor
          key="new-viewing"
          filmId={filmId}
          onCancel={() => setOtherDateOpen(false)}
          onSaved={onSaved}
        />
      ) : null}
    </div>
  );
}
