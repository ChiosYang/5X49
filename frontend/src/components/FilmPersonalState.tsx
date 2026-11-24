"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useRouter } from "@/i18n/routing";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { FormField, Select, TextArea } from "@/components/ui/FormControls";
import { InlineFeedback } from "@/components/ui/Feedback";
import { invalidateViewingCaches, useFilmProfileState, useUpdateFilmProfileState } from "@/hooks/useFilm";
import { personalStateChanges } from "@/lib/personal-state";
import type { FilmProfileState } from "@/types/movie";

export default function FilmPersonalState({
  filmId,
  initialState,
  embedded = false,
}: {
  filmId: string;
  initialState: FilmProfileState;
  embedded?: boolean;
}) {
  const t = useTranslations("PersonalState");
  const router = useRouter();
  const { data: state = initialState, mutate } = useFilmProfileState(filmId);
  const update = useUpdateFilmProfileState(filmId);
  const [open, setOpen] = useState(false);
  const [baseline, setBaseline] = useState(state);
  const [rating, setRating] = useState<number | null>(null);
  const [notes, setNotes] = useState("");
  const [error, setError] = useState(false);
  const [saved, setSaved] = useState(false);
  const changes = personalStateChanges(baseline, { rating, notes });

  const edit = () => {
    setBaseline(state);
    setRating(state.rating ?? null);
    setNotes(state.notes ?? "");
    setError(false);
    setSaved(false);
    setOpen(true);
  };
  const save = async () => {
    setError(false);
    try {
      const result = await update.trigger(changes);
      await mutate(result, { revalidate: false });
      setOpen(false);
      setSaved(true);
      await invalidateViewingCaches(filmId);
      router.refresh();
    } catch {
      setError(true);
    }
  };

  return (
    <section
      className={
        embedded
          ? "min-w-0 space-y-5 border-b border-line pb-8 lg:border-r lg:border-b-0 lg:pr-10 lg:pb-0"
          : "space-y-5 border-b border-line-strong px-8 py-10 md:px-16"
      }
      aria-label={t("title")}
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className={embedded ? "text-lg font-semibold tracking-tight text-ink" : "type-section-title"}>{t("title")}</h2>
        <Button size="sm" variant="secondary" className="rounded-pill px-4" onClick={edit}>{t("edit")}</Button>
      </div>
      <div className="space-y-2.5">
        <p className={state.rating == null ? "text-sm text-ink-subtle" : "font-mono text-sm tabular-nums text-ink"}>
          {state.rating == null ? t("unrated") : t("rated", { rating: state.rating })}
        </p>
        <p className={`max-w-3xl whitespace-pre-wrap break-words text-sm leading-6 ${state.notes ? "text-ink-muted" : "text-ink-subtle"}`}>
          {state.notes || t("noNotes")}
        </p>
      </div>
      {saved && <InlineFeedback tone="success">{t("saved")}</InlineFeedback>}
      <Dialog open={open} onClose={() => { if (!update.isMutating) setOpen(false); }} closeLabel={t("cancel")} ariaLabelledBy="personal-state-title" size="sm" panelClassName="rounded-media">
        <form className="space-y-6 p-6 sm:p-8" onSubmit={(event) => { event.preventDefault(); void save(); }}>
          <h2 id="personal-state-title" className="type-section-title">{t("title")}</h2>
          <FormField label={t("rating")} description={t("ratingHelp")}>
            <Select value={rating ?? ""} disabled={update.isMutating} onChange={(event) => setRating(event.target.value ? Number(event.target.value) : null)}>
              <option value="">{t("unrated")}</option>
              {[1, 2, 3, 4, 5].map((value) => <option key={value} value={value}>{t("rated", { rating: value })}</option>)}
            </Select>
          </FormField>
          <FormField label={t("notes")} description={t("notesHelp")}>
            <TextArea value={notes} maxLength={10000} rows={7} disabled={update.isMutating} onChange={(event) => setNotes(event.target.value)} />
          </FormField>
          {error && <InlineFeedback tone="error">{t("failed")}</InlineFeedback>}
          <div className="flex flex-wrap justify-end gap-3">
            <Button size="sm" className="rounded-pill px-4" disabled={update.isMutating} onClick={() => setOpen(false)}>{t("cancel")}</Button>
            <Button size="sm" type="submit" variant="primary" className="rounded-pill px-5" busy={update.isMutating} disabled={update.isMutating || Object.keys(changes).length === 0}>{t("save")}</Button>
          </div>
        </form>
      </Dialog>
    </section>
  );
}
