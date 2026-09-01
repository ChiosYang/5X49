"use client";

import { CalendarPlus, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { useTranslations } from "next-intl";

import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { InlineFeedback } from "@/components/ui/Feedback";
import {
  invalidateViewingCaches,
  useCreateFilmViewing,
  useDeleteViewing,
  useUpdateViewing,
} from "@/hooks/useFilm";
import { todayLocalDate, viewingDateMode } from "@/lib/diary";
import type { ViewingView } from "@/types/movie";

type DateMode = "date" | "year" | "unknown";

interface ViewingEditorDialogProps {
  filmId: string;
  filmTitle?: string;
  onClose: () => void;
  onSaved?: () => void | Promise<void>;
  open: boolean;
  viewing?: ViewingView | null;
}

export default function ViewingEditorDialog({
  filmId,
  filmTitle,
  onClose,
  onSaved,
  open,
  viewing,
}: ViewingEditorDialogProps) {
  const t = useTranslations("Diary");
  const [mode, setMode] = useState<DateMode>(() => viewingDateMode(viewing));
  const [dateValue, setDateValue] = useState(() => viewing?.watched_at?.slice(0, 10) || todayLocalDate());
  const [yearValue, setYearValue] = useState(() =>
    viewing?.watched_at_precision === "year"
      ? viewing.watched_at || String(new Date().getFullYear())
      : String(new Date().getFullYear()),
  );
  const [feedback, setFeedback] = useState<{ tone: "success" | "error"; text: string } | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const createViewing = useCreateFilmViewing(filmId);
  const updateViewing = useUpdateViewing(viewing?.id);
  const deleteViewing = useDeleteViewing(viewing?.id);
  const busy = createViewing.isMutating || updateViewing.isMutating || deleteViewing.isMutating;
  const succeeded = feedback?.tone === "success";
  const editable = viewing?.editable ?? true;

  const dirty = useMemo(() => {
    if (!viewing) return true;
    const initialMode = viewingDateMode(viewing);
    if (mode !== initialMode) return true;
    if (mode === "unknown") return false;
    if (mode === "year") return yearValue !== viewing.watched_at;
    return dateValue !== viewing.watched_at?.slice(0, 10);
  }, [dateValue, mode, viewing, yearValue]);

  const watchedAt = mode === "unknown" ? null : mode === "year" ? yearValue : dateValue;
  const valid = mode === "unknown"
    || (mode === "year" ? /^[0-9]{4}$/.test(yearValue) && Number(yearValue) > 0 : Boolean(dateValue));

  const complete = async (message: string) => {
    setFeedback({ tone: "success", text: message });
    await invalidateViewingCaches(filmId);
    await onSaved?.();
    window.setTimeout(onClose, 650);
  };

  const save = async () => {
    if (succeeded) return;
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

  return (
    <Dialog
      open={open}
      onClose={onClose}
      closeLabel={t("closeEditor")}
      ariaLabel={viewing ? t("editViewing") : t("recordViewing")}
      size="sm"
      panelClassName="max-h-[min(42rem,calc(100vh-2rem))] overflow-y-auto p-6 sm:p-8"
    >
      <div className="space-y-6">
        <header className="space-y-2">
          <p className="type-label text-ink-subtle">{viewing ? t("editViewing") : t("recordViewing")}</p>
          <h2 className="break-words font-serif text-3xl text-ink">{filmTitle || t("filmFallback")}</h2>
          {viewing ? (
            <p className="type-meta text-ink-subtle">
              {t("sourceLabel", {
                source: viewing.source === "manual"
                  ? t("sources.manual")
                  : viewing.source === "diary"
                    ? t("sources.diary")
                    : t("sources.external", { source: viewing.source }),
              })}
            </p>
          ) : null}
        </header>

        {!editable ? (
          <InlineFeedback tone="warning">{t("readOnlySource")}</InlineFeedback>
        ) : (
          <>
            <fieldset className="space-y-3">
              <legend className="type-label text-ink-subtle">{t("dateMode")}</legend>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
                {(["date", "year", "unknown"] as DateMode[]).map((value) => (
                  <label key={value} className="focus-within:border-ink flex min-h-11 cursor-pointer items-center gap-2 border border-line px-3 text-sm text-ink-muted">
                    <input
                      type="radio"
                      name="viewing-date-mode"
                      value={value}
                      checked={mode === value}
                      onChange={() => setMode(value)}
                    />
                    {t(`modes.${value}`)}
                  </label>
                ))}
              </div>
            </fieldset>

            {mode === "date" ? (
              <label className="block space-y-2">
                <span className="type-label text-ink-subtle">{t("date")}</span>
                <input
                  type="date"
                  max={todayLocalDate()}
                  value={dateValue}
                  onChange={(event) => setDateValue(event.target.value)}
                  className="focus-ring h-11 w-full border border-line-strong bg-surface-raised px-3 text-ink"
                />
              </label>
            ) : null}
            {mode === "year" ? (
              <label className="block space-y-2">
                <span className="type-label text-ink-subtle">{t("year")}</span>
                <input
                  type="number"
                  inputMode="numeric"
                  pattern="[0-9]{4}"
                  min="1"
                  max={new Date().getFullYear()}
                  value={yearValue}
                  onChange={(event) => setYearValue(event.target.value.replace(/\D/g, "").slice(0, 4))}
                  className="focus-ring h-11 w-full border border-line-strong bg-surface-raised px-3 text-ink"
                />
              </label>
            ) : null}
          </>
        )}

        <div aria-live="polite" className="min-h-5">
          {feedback ? <InlineFeedback tone={feedback.tone}>{feedback.text}</InlineFeedback> : null}
        </div>

        <div className="flex flex-col-reverse gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            {viewing?.editable ? (
              confirmDelete ? (
                <div className="flex flex-wrap items-center gap-2">
                  <Button variant="danger" size="sm" busy={deleteViewing.isMutating} onClick={remove}>{t("confirmDelete")}</Button>
                  <Button variant="ghost" size="sm" onClick={() => setConfirmDelete(false)}>{t("cancel")}</Button>
                </div>
              ) : (
                <Button variant="ghost" size="sm" icon={<Trash2 className="h-4 w-4" />} onClick={() => setConfirmDelete(true)}>{t("delete")}</Button>
              )
            ) : null}
          </div>
          <div className="flex flex-col gap-2 sm:flex-row">
            <Button variant="ghost" onClick={onClose}>{t("close")}</Button>
            {editable ? (
              <Button
                variant="primary"
                icon={<CalendarPlus className="h-4 w-4" />}
                busy={busy && !deleteViewing.isMutating}
                disabled={!valid || !dirty || succeeded}
                onClick={save}
              >
                {viewing ? t("save") : t("record")}
              </Button>
            ) : null}
          </div>
        </div>
      </div>
    </Dialog>
  );
}
