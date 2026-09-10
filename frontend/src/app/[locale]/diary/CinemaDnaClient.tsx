"use client";

import { useLocale, useTranslations } from "next-intl";
import { useSearchParams } from "next/navigation";
import { useEffect, useSyncExternalStore } from "react";
import { ArrowDownRight, ArrowUpRight, Info } from "lucide-react";

import { Button } from "@/components/ui/Button";
import { StateMessage } from "@/components/ui/Feedback";
import { useCinemaDna } from "@/hooks/useCinemaDna";
import { Link, useRouter } from "@/i18n/routing";
import { changeDnaQuery, DNA_DIMENSIONS, dnaHref, parseDnaQuery } from "@/lib/cinema-dna";
import type { DnaQuery } from "@/lib/cinema-dna";
import { formatExploreFacetLabel } from "@/lib/explore";
import type { DnaFacet, DnaMetric } from "@/types/cinema-dna";

const subscribe = () => () => {};

export default function CinemaDnaClient() {
  const t = useTranslations("CinemaDna");
  const locale = useLocale();
  const router = useRouter();
  const params = useSearchParams();
  const query = parseDnaQuery(params);
  const { overview, facets, contributors } = useCinemaDna(query);
  const hydrated = useSyncExternalStore(subscribe, () => true, () => false);
  const { mutate: refreshOverview } = overview;
  const { mutate: refreshFacets } = facets;
  const { mutate: refreshContributors } = contributors;

  useEffect(() => {
    const source = new EventSource("/api/library/events");
    let timer: ReturnType<typeof setTimeout> | undefined;
    const refresh = () => {
      clearTimeout(timer);
      timer = setTimeout(() => {
        void refreshOverview();
        void refreshFacets();
        void refreshContributors();
      }, 750);
    };
    source.addEventListener("library_changed", refresh);
    return () => { clearTimeout(timer); source.close(); };
  }, [refreshOverview, refreshFacets, refreshContributors]);

  const navigate = (patch: Partial<DnaQuery>) => router.push(dnaHref(changeDnaQuery(query, patch)), { scroll: false });
  const label = (facet: Pick<DnaFacet, "key" | "label">) =>
    formatExploreFacetLabel(query.dimension, facet.key, facet.label, locale, hydrated);
  const number = (value: number) => new Intl.NumberFormat(locale).format(value);
  const percent = (value: number | null) => value === null ? "—" : new Intl.NumberFormat(locale, { style: "percent", maximumFractionDigits: 1 }).format(value);
  const stars = (value: number) => new Intl.NumberFormat(locale, { minimumFractionDigits: 1, maximumFractionDigits: 1 }).format(value);
  const sourceLabel = (value?: string | null) => value && ["canonical", "curated", "filename", "nfo", "rule", "tmdb", "user"].includes(value)
    ? t(`sources.${value}`) : t("sources.unknown");

  if (overview.error) return <div><StateMessage state="error">{t("error")}</StateMessage><Button onClick={() => void overview.mutate()}>{t("retry")}</Button></div>;
  if (!overview.data) return <StateMessage state="loading">{t("loading")}</StateMessage>;
  const summary = overview.data;
  const page = facets.data;
  const contribution = contributors.data;
  const selected = contribution?.facet;

  return (
    <section aria-label={t("title")} className="space-y-8">
      <p className="type-meta text-ink-subtle">{t("allTime")}</p>

      <dl className="grid grid-cols-1 divide-y divide-line border-y border-line sm:grid-cols-3 sm:divide-x sm:divide-y-0">
        {(["watched_films", "viewing_records", "rated_films"] as const).map((key) => (
          <div key={key} className="min-w-0 px-3 py-5 sm:px-6">
            <dt className="type-label text-ink-subtle">{t(`totals.${key}`)}</dt>
            <dd className="mt-3 text-4xl font-light tabular-nums sm:text-5xl">{number(summary.totals[key])}</dd>
          </div>
        ))}
      </dl>

      <div className="flex flex-wrap gap-2" role="group" aria-label={t("metricLabel")}>
        {(["exposure", "preference"] as DnaMetric[]).map((metric) => (
          <Button key={metric} variant={query.metric === metric ? "primary" : "secondary"} aria-pressed={query.metric === metric} onClick={() => navigate({ metric })}>{t(metric)}</Button>
        ))}
      </div>
      <p className="max-w-3xl text-sm leading-7 text-ink-muted">{t(query.metric === "exposure" ? "exposureBasis" : "preferenceBasis", {
        global: summary.thresholds.global_rated_films, category: summary.thresholds.category_rated_films,
      })}</p>
      {query.metric === "preference" && summary.needed_global_ratings > 0 ? (
        <div className="flex items-start gap-3 border border-line bg-surface px-5 py-4 text-sm leading-7 text-ink-muted" role="status">
          <Info className="mt-1 h-4 w-4 shrink-0" aria-hidden />
          <p>{t("needGlobal", { count: summary.needed_global_ratings })} {t("inspectExposure")}</p>
        </div>
      ) : null}

      <div className="grid grid-cols-2 gap-2 sm:flex sm:flex-wrap" role="group" aria-label={t("dimensionLabel")}>
        {DNA_DIMENSIONS.map((dimension) => (
          <Button key={dimension} aria-pressed={query.dimension === dimension} variant={query.dimension === dimension ? "primary" : "ghost"} onClick={() => navigate({ dimension })}>{t(`dimensions.${dimension}`)}</Button>
        ))}
      </div>

      <div aria-live="polite" aria-busy={facets.isLoading}>
        {facets.error ? <div><StateMessage state="error">{t("error")}</StateMessage><Button onClick={() => void facets.mutate()}>{t("retry")}</Button></div>
          : !page ? <StateMessage state="loading">{t("loading")}</StateMessage>
          : <>
            <p className="mb-6 text-xs leading-6 text-ink-subtle">{t("coverage", { covered: page.coverage.covered_films, conflicted: page.coverage.conflicted_films, missing: page.coverage.missing_films, total: page.coverage.total_films })}</p>
            {page.items.length === 0 ? (
              <StateMessage>{t(summary.totals.watched_films === 0 ? "emptyHistory" : query.offset > 0 ? "emptyPage" : query.metric === "preference" ? "emptyPreference" : "emptyFacts")}</StateMessage>
            ) : <ol className="divide-y divide-line border-y border-line">
              {page.items.map((facet) => (
                <li key={facet.key}>
                  <button type="button" aria-expanded={query.facet === facet.key} aria-controls="dna-contributors" onClick={() => navigate({ facet: query.facet === facet.key ? null : facet.key })} className={`focus-ring group w-full px-3 py-5 text-left hover:bg-surface sm:px-5 ${query.facet === facet.key ? "bg-surface" : ""}`}>
                    <div className="flex items-start justify-between gap-4">
                      <div className="min-w-0">
                        <span className="break-words text-lg font-semibold">{label(facet)}</span>
                        {facet.roles.length > 0 ? <span className="mt-1 block text-xs text-ink-subtle">{facet.roles.map((role) => t(`roles.${role}`)).join(" · ")}</span> : null}
                      </div>
                      <span className="shrink-0 text-lg tabular-nums">{query.metric === "exposure" ? percent(facet.share) : `${stars(facet.preference!)} / 5`}</span>
                    </div>
                    <div className="my-3 h-1 w-full bg-line" aria-hidden>
                      <div className="h-full bg-ink-muted" style={{ width: `${Math.min(100, (query.metric === "exposure" ? facet.share || 0 : (facet.preference || 0) / 5) * 100)}%` }} />
                    </div>
                    <div className="flex flex-wrap items-center justify-between gap-x-5 gap-y-2 text-xs leading-6 text-ink-subtle">
                      <span>{t("basis", { count: facet.film_count, total: facet.denominator, rated: facet.rated_count })}</span>
                      <span className="inline-flex items-center gap-2">{t("contributors")}<ArrowDownRight className="h-3 w-3" aria-hidden /></span>
                    </div>
                  </button>
                </li>
              ))}
            </ol>}
            <div className="mt-5 flex flex-wrap items-center justify-between gap-3">
              <Button size="sm" disabled={query.offset === 0} onClick={() => navigate({ offset: Math.max(0, query.offset - page.limit) })}>{t("previous")}</Button>
              <span className="type-meta text-ink-subtle">{t("pageCount", { count: page.total })}</span>
              <Button size="sm" disabled={page.next_offset === null} onClick={() => navigate({ offset: page.next_offset! })}>{t("next")}</Button>
            </div>
          </>}
      </div>

      <div id="dna-contributors">
        {query.facet ? <section className="space-y-5 border border-line bg-surface p-4 sm:p-7" aria-labelledby="dna-contributors-title" aria-busy={contributors.isLoading}>
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0"><p className="type-label text-ink-subtle">{t("contributors")}</p><h3 id="dna-contributors-title" className="mt-2 break-words text-2xl font-bold">{selected ? label(selected) : t("contributionTitle")}</h3></div>
            <Button size="sm" onClick={() => navigate({ facet: null })}>{t("close")}</Button>
          </div>
          {contributors.error ? <div><StateMessage state="error">{t("error")}</StateMessage><Button onClick={() => void contributors.mutate()}>{t("retry")}</Button></div>
            : !contribution ? <StateMessage state="loading">{t("loading")}</StateMessage>
            : <>
              {selected ? <div className="space-y-2 text-sm leading-7 text-ink-muted">
                <p>{t("basis", { count: selected.film_count, total: selected.denominator, rated: selected.rated_count })}</p>
                <p>{t("sourceLabel", { sources: selected.source_kinds.map(sourceLabel).join(" · ") || t("sources.unknown") })}</p>
                {contribution.needed_global_ratings > 0 ? <p>{t("needGlobal", { count: contribution.needed_global_ratings })}</p> : null}
                {selected.needed_category_ratings > 0 ? <p>{t("needCategory", { count: selected.needed_category_ratings })}</p> : null}
              </div> : null}
              {contribution.items.length === 0 ? <StateMessage>{t("emptyContributors")}</StateMessage> : (
                <ul className="divide-y divide-line">
                  {contribution.items.map((film) => <li key={film.film_id} className="flex flex-col gap-3 py-5 sm:flex-row sm:items-center sm:justify-between">
                    <div className="min-w-0">
                      <p className="break-words font-semibold">{film.title}</p>
                      <p className="mt-1 text-xs leading-6 text-ink-subtle">{film.year ?? t("unknownYear")} · {t("records", { count: film.viewing_count })} · {film.rating === null ? t("unrated") : `${film.rating} / 5`}</p>
                      <p className="text-xs leading-6 text-ink-subtle">{sourceLabel(film.fact.source.source_kind)}{!film.in_library ? ` · ${t("outsideLibrary")}` : ""}</p>
                    </div>
                    <Link href={`/diary?film=${film.film_id}`} className="focus-ring inline-flex min-h-11 shrink-0 items-center gap-2 self-start border border-line px-4 text-xs font-bold sm:self-auto">{t("viewDiary")}<ArrowUpRight className="h-3 w-3" aria-hidden /></Link>
                  </li>)}
                </ul>
              )}
              <div className="flex flex-wrap items-center justify-between gap-3">
                <Button size="sm" disabled={query.contributorsOffset === 0} onClick={() => navigate({ contributorsOffset: Math.max(0, query.contributorsOffset - contribution.limit) })}>{t("previous")}</Button>
                <span className="type-meta text-ink-subtle">{t("filmCount", { count: contribution.total })}</span>
                <Button size="sm" disabled={contribution.next_offset === null} onClick={() => navigate({ contributorsOffset: contribution.next_offset! })}>{t("next")}</Button>
              </div>
            </>}
        </section> : null}
      </div>

      <details className="border-t border-line py-5 text-sm leading-7 text-ink-subtle">
        <summary className="focus-ring cursor-pointer font-semibold text-ink-muted">{t("methodTitle")}</summary>
        <p className="mt-4 max-w-3xl">{t("method")}</p>
        <p className="mt-2 type-meta">{summary.formula_version}</p>
      </details>
    </section>
  );
}
