"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Button, ButtonLink } from "@/components/ui/Button";
import { FormField, Select, TextInput } from "@/components/ui/FormControls";
import { buildLibraryHref, type LibraryQueryState } from "@/lib/library-care";
import { clearLibraryFilters, invalidLibraryRanges, LIBRARY_RANGES, readLibraryRanges } from "@/lib/library-filters";

/** Native GET navigation makes the committed URL the single source of truth.
 * A later navigation cancels an earlier document request; no result is copied
 * into a second client-side cache. Drafts only take effect on Apply. */
export default function LibraryFilters({ state, locale }: { state: LibraryQueryState; locale: string }) {
  const t = useTranslations("LibraryFilters");
  const libraryT = useTranslations("Library");
  const [errors, setErrors] = useState(invalidLibraryRanges(state));
  return <form action={`/${locale}/library`} method="get" autoComplete="off" aria-label={t("label")}
    className="space-y-5 border-b border-line py-6" onSubmit={(event) => {
      const values = Object.fromEntries(new FormData(event.currentTarget)) as Record<string, string>;
      const invalid = invalidLibraryRanges(readLibraryRanges(values));
      setErrors(invalid);
      if (invalid.length) event.preventDefault();
    }}>
    <input type="hidden" name="sort" value={state.sort} />
    <input type="hidden" name="dir" value={state.direction} />
    <div className="grid min-w-0 gap-4 sm:grid-cols-2 lg:grid-cols-4">
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
    <div className="grid min-w-0 gap-5 lg:grid-cols-3">
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
  </form>;
}
