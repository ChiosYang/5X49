"use client";

import { useId, useRef, useState } from "react";
import { ListFilter, X } from "lucide-react";
import { useTranslations } from "next-intl";
import { Button, ButtonLink, IconButton } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { FormField, Select, TextInput } from "@/components/ui/FormControls";
import { buildLibraryHref, type LibraryQueryState } from "@/lib/library-care";
import { clearLibraryFilters, invalidLibraryRanges, libraryFilterCount, LIBRARY_RANGES, readLibraryRanges } from "@/lib/library-filters";

export function LibraryFilterSummary({ state }: { state: LibraryQueryState }) {
  const t = useTranslations("LibraryFilters");
  const libraryT = useTranslations("Library");
  const conditions = [
    state.query,
    state.filter === "watched" ? libraryT("filterWatched") : state.filter === "unwatched" ? libraryT("filterUnwatched") : null,
    state.favorite || state.filter === "favorite" ? t("favorite") : null,
    ...LIBRARY_RANGES.map(({ key }) => state[`${key}_min`] || state[`${key}_max`]
      ? `${t(key)}: ${state[`${key}_min`] || t("any")}–${state[`${key}_max`] || t("any")}` : null),
  ].filter(Boolean);
  if (!conditions.length) return null;
  return <div className="mt-4 flex min-w-0 flex-wrap items-center gap-x-4 gap-y-2 text-xs text-ink-subtle" aria-label={t("applied")}>
    {conditions.map((condition, index) => <span key={index} className="max-w-full break-words">{condition}</span>)}
    <ButtonLink href={buildLibraryHref(clearLibraryFilters(state), "all")} size="sm" variant="ghost">{t("clear")}</ButtonLink>
  </div>;
}

/** Native GET navigation makes the committed URL the single source of truth.
 * A later navigation cancels an earlier document request; no result is copied
 * into a second client-side cache. Drafts only take effect on Apply. */
export default function LibraryFilters({ state, locale }: { state: LibraryQueryState; locale: string }) {
  const t = useTranslations("LibraryFilters");
  const libraryT = useTranslations("Library");
  const [open, setOpen] = useState(false);
  const id = useId();
  const count = libraryFilterCount(state);
  const [errors, setErrors] = useState(invalidLibraryRanges(state));
  const lastSubmit = useRef<{ query: string; at: number } | null>(null);
  const close = () => { setOpen(false); setErrors(invalidLibraryRanges(state)); };
  return <>
    <IconButton variant="ghost" aria-label={libraryT("filter")} aria-haspopup="dialog" aria-expanded={open} aria-controls={id}
      aria-describedby={count ? `${id}-count` : undefined} onClick={() => setOpen(true)} className="relative"
      icon={<><ListFilter className="h-4 w-4" />{count > 0 && <span aria-hidden="true" className="absolute top-2 right-2 h-1.5 w-1.5 rounded-full bg-ink" />}</>} />
    {count > 0 && <span id={`${id}-count`} className="sr-only">{t("activeCount", { count })}</span>}
    <Dialog id={id} open={open} onClose={close} closeLabel={t("close")} ariaLabel={t("label")} glass={false}
      overlayClassName="items-stretch justify-end p-0" panelClassName="h-dvh max-w-xl overflow-y-auto border-l border-line p-5 sm:p-8">
    <div className="mb-7 flex items-center justify-between gap-4">
      <h2 className="type-section-title">{t("label")}</h2>
      <IconButton variant="ghost" aria-label={t("close")} icon={<X className="h-5 w-5" />} onClick={close} />
    </div>
    <form action={`/${locale}/library`} method="get" autoComplete="off" aria-label={t("label")}
    className="space-y-6" onSubmit={(event) => {
      const values = Object.fromEntries(new FormData(event.currentTarget)) as Record<string, string>;
      const invalid = invalidLibraryRanges(readLibraryRanges(values));
      setErrors(invalid);
      if (invalid.length) { event.preventDefault(); return; }
      // A second native GET can otherwise land after the drawer is reopened.
      const query = new URLSearchParams(values).toString();
      const at = performance.now();
      if (lastSubmit.current?.query === query && at - lastSubmit.current.at < 1000) event.preventDefault();
      else lastSubmit.current = { query, at };
    }}>
    <input type="hidden" name="sort" value={state.sort} />
    <input type="hidden" name="dir" value={state.direction} />
    <div className="grid min-w-0 gap-4 sm:grid-cols-2">
      <div className="min-w-0 sm:col-span-2">
        <FormField label={t("query")}><TextInput name="q" type="search" defaultValue={state.query} maxLength={200} placeholder={t("searchPlaceholder")} /></FormField>
      </div>
      <FormField label={t("watched")}><Select name="filter" aria-label={t("watched")} defaultValue={state.filter === "favorite" ? "all" : state.filter}>
        <option value="all">{libraryT("filterAll")}</option><option value="watched">{libraryT("filterWatched")}</option><option value="unwatched">{libraryT("filterUnwatched")}</option>
      </Select></FormField>
      <label className="flex min-h-11 items-center gap-3 self-end text-sm text-ink-muted">
        <input name="favorite" type="checkbox" value="true" defaultChecked={state.favorite || state.filter === "favorite"} className="focus-ring h-5 w-5 accent-current" />{t("favorite")}
      </label>
    </div>
    <div className="grid min-w-0 gap-5">
      {LIBRARY_RANGES.map(({key, min, max}) => <fieldset key={key} className="min-w-0">
        <legend className="mb-2 type-label text-ink-subtle">{t(key)} <span className="text-ink-disabled">{min}–{max}</span></legend>
        <div className="flex min-w-0 items-center gap-2">
          <TextInput name={`${key}_min`} aria-label={t(`${key}Min`)} aria-invalid={errors.includes(key)} type="number" min={min} max={max} step={1} defaultValue={state[`${key}_min`]} placeholder={t("minimum")} />
          <span aria-hidden="true" className="text-ink-disabled">–</span>
          <TextInput name={`${key}_max`} aria-label={t(`${key}Max`)} aria-invalid={errors.includes(key)} type="number" min={min} max={max} step={1} defaultValue={state[`${key}_max`]} placeholder={t("maximum")} />
        </div>
      </fieldset>)}
    </div>
    <p className="max-w-4xl text-xs leading-6 text-ink-subtle">{t("help")}</p>
    {errors.length > 0 && <p role="alert" className="text-sm text-danger">{t("invalid", { fields: errors.map(key => t(key)).join(" / ") })}</p>}
    <div className="flex flex-wrap items-center gap-3">
      <Button type="submit" variant="primary">{t("apply")}</Button>
      <ButtonLink href={buildLibraryHref(clearLibraryFilters(state), "all")} variant="ghost">{t("clear")}</ButtonLink>
    </div>
    </form>
    </Dialog>
  </>;
}
