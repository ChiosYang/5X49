"use client";

import { useMemo, useState } from "react";
import { Search, X } from "lucide-react";
import { useTranslations } from "next-intl";
import useSWRInfinite from "swr/infinite";

import { Button, IconButton } from "@/components/ui/Button";
import { TextInput } from "@/components/ui/FormControls";
import { Dialog } from "@/components/ui/Dialog";
import { InlineFeedback, Spinner } from "@/components/ui/Feedback";
import { API } from "@/lib/api";
import { EXPLORE_DIMENSIONS, formatExploreFacetLabel } from "@/lib/explore";
import { fetcher } from "@/lib/fetcher";
import type { ExploreDimension, ExploreFacetPage, ExploreFacetSummary } from "@/types/movie";

const PAGE_SIZE = 30;

type ExploreFactFinderProps = {
  open: boolean;
  dimension: ExploreDimension;
  locale: string;
  localizeCountries: boolean;
  reducedMotion: boolean;
  onDimensionChange: (dimension: ExploreDimension) => void;
  onClose: () => void;
  onSelect: (dimension: ExploreDimension, item: ExploreFacetSummary) => void;
};

export default function ExploreFactFinder({
  open,
  dimension,
  locale,
  localizeCountries,
  reducedMotion,
  onDimensionChange,
  onClose,
  onSelect,
}: ExploreFactFinderProps) {
  const t = useTranslations("Explore");
  const [search, setSearch] = useState("");
  const query = search.trim();
  const { data, error, isLoading, isValidating, size, setSize } = useSWRInfinite<ExploreFacetPage>(
    (pageIndex, previousPage) => {
      if (!open || (previousPage && previousPage.next_offset === null)) return null;
      return API.exploreFacets(dimension, {
        q: query || undefined,
        limit: PAGE_SIZE,
        offset: pageIndex * PAGE_SIZE,
      });
    },
    fetcher,
    { revalidateFirstPage: false },
  );
  const items = useMemo(() => {
    const unique = new Map<string, ExploreFacetSummary>();
    data?.forEach((page) => page.items.forEach((item) => unique.set(item.key, item)));
    return [...unique.values()];
  }, [data]);
  const lastPage = data?.at(-1);
  const hasMore = lastPage?.next_offset !== null && Boolean(lastPage);

  const close = () => {
    setSearch("");
    void setSize(1);
    onClose();
  };

  return (
    <Dialog
      animated={!reducedMotion}
      open={open}
      onClose={close}
      closeLabel={t("closeFinder")}
      ariaLabelledBy="fact-finder-title"
      size="lg"
      placement="bottom"
      panelClassName="max-h-[min(48rem,calc(100dvh-3rem))] rounded-control sm:rounded-control"
    >
      <div className="flex items-start justify-between gap-5 border-b border-line-strong px-5 py-5 sm:px-7">
        <div>
          <p className="type-label text-ink-muted">{t("finderEyebrow")}</p>
          <h2 id="fact-finder-title" className="mt-1 font-serif text-3xl text-ink">
            {t("finderTitle")}
          </h2>
          <p className="mt-1 text-sm text-ink-muted">{t("finderDescription")}</p>
        </div>
        <IconButton
          variant="ghost"
          onClick={close}
          aria-label={t("closeFinder")}
          icon={<X className="h-4 w-4" />}
        />
      </div>

      <div className="border-b border-line px-5 pt-5 sm:px-7">
        <div className="grid grid-cols-4 gap-1 rounded-control border border-line bg-surface p-1">
          {EXPLORE_DIMENSIONS.map((entry) => (
            <button
              key={entry}
              type="button"
              onClick={() => {
                onDimensionChange(entry);
                void setSize(1);
              }}
              aria-pressed={entry === dimension}
              className={`focus-ring duration-standard min-h-11 min-w-0 rounded-control px-2 py-2.5 text-xs transition-colors ${
                entry === dimension ? "bg-inverse text-inverse-ink" : "text-ink-muted hover:bg-surface-hover hover:text-ink"
              }`}
            >
              <span className="block truncate">{t(`dimensions.${entry}`)}</span>
            </button>
          ))}
        </div>

        <label className="mt-4 flex items-center gap-2 pb-3">
          <Search className="h-5 w-5 shrink-0 text-ink-subtle" />
          <TextInput
            aria-label={t("searchFacet", { dimension: t(`dimensions.${dimension}`) })}
            data-dialog-initial-focus
            value={search}
            maxLength={100}
            onChange={(event) => {
              setSearch(event.target.value);
              void setSize(1);
            }}
            placeholder={t("searchFacet", { dimension: t(`dimensions.${dimension}`) })}
            className="min-w-0 flex-1"
          />
          {search ? (
            <IconButton
              variant="ghost"
              onClick={() => {
                setSearch("");
                void setSize(1);
              }}
              aria-label={t("clearSearch")}
              icon={<X className="h-4 w-4" />}
            />
          ) : null}
        </label>
      </div>

      <div className="max-h-[52dvh] overflow-y-auto px-5 py-5 sm:px-7">
        {isLoading && !data ? (
          <div className="flex min-h-40 items-center justify-center gap-2 text-sm text-ink-muted">
            <Spinner /> {t("loadingFacts")}
          </div>
        ) : null}
        {error ? <InlineFeedback tone="error">{t("facetLoadFailed")}</InlineFeedback> : null}
        {!isLoading && !error && items.length === 0 ? (
          <div className="flex min-h-40 items-center justify-center text-sm text-ink-muted">{t("noFacets")}</div>
        ) : null}
        <div className="grid gap-2 sm:grid-cols-2">
          {items.map((item) => {
            const label = formatExploreFacetLabel(
              dimension,
              item.key,
              item.label,
              locale,
              localizeCountries,
            );
            return (
              <button
                key={item.key}
                type="button"
                onClick={() => {
                  onSelect(dimension, item);
                  close();
                }}
                className="focus-ring duration-standard flex min-h-11 min-w-0 items-center justify-between gap-4 rounded-control border border-line-strong px-4 py-3 text-left transition-colors hover:border-ink-muted hover:bg-surface-hover"
              >
                <span className="min-w-0">
                  <span className="block truncate text-sm font-medium text-ink">{label}</span>
                  {dimension === "person" && item.roles.length > 0 ? (
                    <span className="mt-1 block truncate text-[10px] uppercase tracking-[0.14em] text-ink-subtle">
                      {item.roles.map((role) => t(`roles.${role}`)).join(" · ")}
                    </span>
                  ) : null}
                </span>
                <span className="shrink-0 rounded-full border border-line px-2 py-1 text-[10px] text-ink-subtle">
                  {t("factFilmCount", { count: item.owned_count })}
                </span>
              </button>
            );
          })}
        </div>
        {hasMore ? (
          <Button
            className="mt-5 w-full"
            variant="secondary"
            busy={isValidating && data?.length === size}
            onClick={() => void setSize(size + 1)}
          >
            {t("loadMore")}
          </Button>
        ) : null}
      </div>
    </Dialog>
  );
}
