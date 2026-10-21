"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Check, Search, X } from "lucide-react";
import { useTranslations } from "next-intl";
import useSWRInfinite from "swr/infinite";

import { Button, IconButton } from "@/components/ui/Button";
import { TextInput } from "@/components/ui/FormControls";
import { InlineFeedback, Spinner } from "@/components/ui/Feedback";
import { API } from "@/lib/api";
import { EXPLORE_DIMENSIONS, formatExploreFacetLabel, type ExploreQueryState } from "@/lib/explore";
import { fetcher } from "@/lib/fetcher";
import type { ExploreDimension, ExploreFacetPage, ExploreFacetSummary } from "@/types/movie";

type Props = {
  query: ExploreQueryState;
  locale: string;
  localizeCountries: boolean;
  onSelect: (dimension: ExploreDimension, item: ExploreFacetSummary) => void;
};

function SearchGroup({ dimension, search, query, locale, localizeCountries, onSelect }: Props & {
  dimension: ExploreDimension;
  search: string;
}) {
  const t = useTranslations("Explore");
  const { data, error, isLoading, isValidating, size, setSize, mutate } = useSWRInfinite<ExploreFacetPage>(
    (pageIndex, previousPage) => previousPage?.next_offset === null ? null : API.exploreFacets(dimension, {
      q: search || undefined, limit: 6, offset: pageIndex * 6,
    }),
    fetcher,
    { revalidateFirstPage: false },
  );
  const items = useMemo(() => {
    const unique = new Map<string, ExploreFacetSummary>();
    data?.forEach(page => page.items.forEach(item => unique.set(item.key, item)));
    return [...unique.values()];
  }, [data]);
  const hasMore = Boolean(data?.at(-1) && data.at(-1)?.next_offset !== null);

  return (
    <section aria-label={t(`dimensions.${dimension}`)} className="min-w-0">
      <h3 className="type-label mb-2 text-ink-muted">{t(`dimensions.${dimension}`)}</h3>
      {isLoading ? <Spinner className="text-ink-muted" /> : null}
      {error ? <InlineFeedback tone="error">{t("facetLoadFailed")} <Button variant="ghost" size="sm" onClick={() => void mutate()}>{t("retry")}</Button></InlineFeedback> : null}
      {!isLoading && !error && items.length === 0 ? <p className="py-2 text-sm text-ink-subtle">{t("noFacets")}</p> : null}
      <div className="grid gap-1">
        {items.map(item => {
          const label = formatExploreFacetLabel(dimension, item.key, item.label, locale, localizeCountries);
          const selected = query[dimension].includes(item.key);
          return (
            <button
              key={item.key}
              type="button"
              aria-pressed={selected}
              onClick={() => { if (!selected) onSelect(dimension, item); }}
              className="focus-ring duration-standard flex min-h-11 min-w-0 items-center justify-between gap-3 border-b border-line px-2 py-2 text-left transition-colors hover:bg-surface-hover"
            >
              <span className="min-w-0">
                <span className="block truncate text-sm text-ink">{label}</span>
                {item.roles.length > 0 ? <span className="block text-xs text-ink-subtle">{item.roles.map(role => t(`roles.${role}`)).join(" · ")}</span> : null}
              </span>
              <span className="flex shrink-0 items-center gap-2 text-xs text-ink-subtle">
                {t("factFilmCount", { count: item.owned_count })}
                {selected ? <Check className="h-3.5 w-3.5" aria-label={t("selected")} /> : null}
              </span>
            </button>
          );
        })}
      </div>
      {hasMore ? <Button className="mt-2" variant="ghost" size="sm" busy={isValidating} onClick={() => void setSize(size + 1)}>{t("loadMore")}</Button> : null}
    </section>
  );
}

export default function ExploreSearch(props: Props) {
  const t = useTranslations("Explore");
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  const [dimension, setDimension] = useState<ExploreDimension | "all">("all");
  const inputRef = useRef<HTMLInputElement>(null);
  const text = search.trim();
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(text), 200);
    return () => window.clearTimeout(timer);
  }, [text]);
  useEffect(() => {
    const shortcut = (event: KeyboardEvent) => {
      const target = event.target;
      if (event.key !== "/" || event.altKey || event.ctrlKey || event.metaKey ||
          (target instanceof HTMLElement && (target.matches("input, textarea, select") || target.isContentEditable))) return;
      event.preventDefault();
      inputRef.current?.focus();
    };
    window.addEventListener("keydown", shortcut);
    return () => window.removeEventListener("keydown", shortcut);
  }, []);
  const dimensions = dimension === "all" ? EXPLORE_DIMENSIONS : [dimension];
  const searching = Boolean(text) || dimension !== "all";

  return (
    <section aria-labelledby="explore-search-title" className="min-w-0 space-y-3">
      <h2 id="explore-search-title" className="font-serif text-2xl text-ink">{t("searchTitle")}</h2>
      <div className="flex items-center gap-2">
        <Search className="h-4 w-4 shrink-0 text-ink-subtle" aria-hidden="true" />
        <TextInput
          ref={inputRef}
          aria-label={t("searchAll")}
          aria-describedby="explore-search-hint"
          aria-keyshortcuts="/"
          value={search}
          maxLength={100}
          onChange={event => setSearch(event.target.value)}
          onKeyDown={event => { if (event.key === "Escape") { setSearch(""); setDimension("all"); } }}
          placeholder={t("searchAll")}
          className="min-w-0 flex-1"
        />
        {search ? <IconButton variant="ghost" aria-label={t("clearSearch")} icon={<X className="h-4 w-4" />} onClick={() => { setSearch(""); inputRef.current?.focus(); }} /> : null}
      </div>
      <div role="group" aria-label={t("searchType")} className="flex flex-wrap gap-1">
        {(["all", ...EXPLORE_DIMENSIONS] as const).map(entry => <Button key={entry} size="sm" variant={dimension === entry ? "primary" : "ghost"} aria-pressed={dimension === entry} onClick={() => setDimension(entry)}>{entry === "all" ? t("allTypes") : t(`dimensions.${entry}`)}</Button>)}
      </div>
      <p id="explore-search-hint" className="text-xs leading-5 text-ink-subtle">{t("searchDescription")}</p>
      {searching ? (
        <div className="max-h-80 overflow-y-auto border-y border-line py-4" aria-busy={text !== debounced}>
          {text !== debounced ? <Spinner className="text-ink-muted" /> : (
            <div className="grid gap-5 sm:grid-cols-2">
              {dimensions.map(entry => <SearchGroup key={`${entry}:${debounced}`} {...props} dimension={entry} search={debounced} />)}
            </div>
          )}
        </div>
      ) : null}
    </section>
  );
}
