"use client";

import { useEffect, useLayoutEffect, useMemo, useOptimistic, useRef, useState, useSyncExternalStore, useTransition } from "react";
import { useReducedMotion } from "framer-motion";
import { useTranslations } from "next-intl";

import { Link, useRouter } from "@/i18n/routing";
import { clearExploreFilters, correctedExploreOffset, exploreHref, exploreNavigation, formatExploreFacetLabel, withExploreFacet, withoutExploreFacet, type ExploreQueryState } from "@/lib/explore";
import { useExploreRefresh } from "@/hooks/useExploreRefresh";
import { ButtonLink } from "@/components/ui/Button";
import type { LocalCollection, ExploreDimension, ExploreFacetSummary, ExploreFilmPage, ExploreView } from "@/types/movie";
import ExploreSearch from "./ExploreSearch";
import { QueryRibbon, ResultStage } from "./ExploreViews";

const subscribeHydration = () => () => {};
const getHydratedSnapshot = () => true;
const getServerSnapshot = () => false;

export default function ExploreClient({ collection, basePath = "/explore/filter", locale, query, results }: {
  collection?: LocalCollection;
  basePath?: string;
  locale: string;
  query: ExploreQueryState;
  results: ExploreFilmPage;
}) {
  const c = useTranslations("Collections");
  const router = useRouter();
  const reducedMotion = useReducedMotion() ?? false;
  const localizeCountries = useSyncExternalStore(subscribeHydration, getHydratedSnapshot, getServerSnapshot);
  const [optimisticQuery, setOptimisticQuery] = useOptimistic(query);
  const [pending, startTransition] = useTransition();
  const [remembered, setRemembered] = useState<Record<string, { label: string; roles?: string[] }>>({});
  const sectionRef = useRef<HTMLElement>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const paginationTarget = useRef<string | null>(null);
  const scrollTarget = useRef<{ href: string; x: number; y: number } | null>(null);
  const activeQueryRef = useRef<ExploreQueryState | null>(null);
  useLayoutEffect(() => {
    activeQueryRef.current = optimisticQuery;
    return () => { activeQueryRef.current = null; };
  }, [optimisticQuery]);
  const beginRead = useExploreRefresh(results, pending, exploreHref(optimisticQuery, basePath), exploreHref(query, basePath));
  const collectionLabel = collection ? formatExploreFacetLabel(
    collection.kind === "director" || collection.kind === "person" ? "person" : collection.kind,
    collection.key, collection.label, locale, localizeCountries,
  ) : "";
  const labels = useMemo(() => {
    const map = new Map(Object.entries(remembered));
    results.filters.forEach(item => map.set(`${item.dimension}:${item.key}`, item));
    return map;
  }, [remembered, results]);
  const unresolved = useMemo(() => new Set(results.unresolved_filters.map(item => `${item.dimension}:${item.key}`)), [results]);

  const navigate = (next: ExploreQueryState, intent: "filter" | "page" = "filter") => {
    const navigation = exploreNavigation(next, intent, basePath);
    paginationTarget.current = navigation.focusResults ? navigation.href : null;
    scrollTarget.current = navigation.focusResults ? null : { href: navigation.href, x: window.scrollX, y: window.scrollY };
    startTransition(() => {
      beginRead(navigation.href);
      setOptimisticQuery(next);
      router.push(navigation.href, { scroll: navigation.scroll });
    });
  };
  const select = (dimension: ExploreDimension, item: Pick<ExploreFacetSummary, "key" | "label" | "roles">) => {
    if (optimisticQuery[dimension].includes(item.key)) return;
    setRemembered(current => ({ ...current, [`${dimension}:${item.key}`]: item }));
    navigate(withExploreFacet(optimisticQuery, dimension, item.key));
  };
  const clear = () => navigate(clearExploreFilters(optimisticQuery));
  const setView = (view: ExploreView) => navigate({ ...optimisticQuery, view, offset: 0 });
  const setSort = (sort: ExploreQueryState["sort"]) => navigate({ ...optimisticQuery, sort, dir: sort === "year" ? "desc" : "asc", offset: 0 });

  useEffect(() => {
    const activeQuery = activeQueryRef.current;
    if (pending || !activeQuery || !/\/explore(?:\/|$)/.test(window.location.pathname)
        || exploreNavigation(activeQuery, "filter", basePath).href !== exploreNavigation(query, "filter", basePath).href) return;
    const offset = correctedExploreOffset(query.offset, results.total, results.limit);
    if (offset === query.offset) return;
    const href = exploreNavigation({ ...query, offset }, "filter", basePath).href;
    scrollTarget.current = { href, x: window.scrollX, y: window.scrollY };
    // Correct this history entry, retaining every filter and the current viewport.
    startTransition(() => { beginRead(href); router.replace(href, { scroll: false }); });
  }, [basePath, beginRead, pending, query, results.limit, results.total, router]);

  useLayoutEffect(() => {
    const target = scrollTarget.current;
    if (!target || target.href !== exploreNavigation(query, "filter", basePath).href) return;
    window.scrollTo(target.x, target.y);
    const frame = window.requestAnimationFrame(() => {
      window.scrollTo(target.x, target.y);
      if (scrollTarget.current === target) scrollTarget.current = null;
    });
    return () => window.cancelAnimationFrame(frame);
  }, [basePath, query]);
  useEffect(() => {
    if (pending || paginationTarget.current !== exploreNavigation(query, "page", basePath).href) return;
    paginationTarget.current = null;
    const frame = window.requestAnimationFrame(() => {
      headingRef.current?.focus({ preventScroll: true });
      sectionRef.current?.scrollIntoView({ behavior: reducedMotion ? "auto" : "smooth", block: "start" });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [basePath, pending, query, reducedMotion]);

  return (
    <div className="page-x min-h-screen bg-canvas pb-24 pt-38 text-ink selection:bg-inverse selection:text-inverse-ink md:pt-44">
      <nav aria-label={c("breadcrumb")} className="mb-5 flex flex-wrap gap-4 text-sm text-ink-muted">
        <Link prefetch={false} href="/explore" scroll={false} className="focus-ring hover:text-ink">{c("homeTitle")}</Link>
        {collection ? <Link prefetch={false} href="/explore/collections" className="focus-ring hover:text-ink">{c("directoryTitle")}</Link> : null}
      </nav>
      <header className="flex flex-col gap-7 border-b border-line pb-8 lg:flex-row lg:items-end lg:justify-between">
        <div className="min-w-0">
          <h1 className="type-display-editorial break-words">{collection ? c(`titles.${collection.kind}`, { label: collectionLabel }) : c("filterTitle")}</h1>
          <p className="mt-4 max-w-2xl text-sm leading-6 text-ink-muted">{collection ? c(`descriptions.${collection.kind}`, { label: collectionLabel, count: collection.count }) : c("filterDescription")}</p>
        </div>
        {collection ? <ButtonLink prefetch={false} href="/explore/filter" variant="ghost" size="sm">{c("filterTitle")}</ButtonLink> : null}
      </header>
      <div className="mt-6 min-w-0 space-y-8">
        {!collection ? <ExploreSearch query={optimisticQuery} locale={locale} localizeCountries={localizeCountries} onSelect={select} /> : null}
        {!collection ?
        <QueryRibbon
          query={optimisticQuery} labels={labels} unresolved={unresolved} locale={locale} localizeCountries={localizeCountries}
          onRemove={(dimension, key) => navigate(withoutExploreFacet(optimisticQuery, dimension, key))}
          onClear={clear}
          onPersonMatch={personMatch => navigate({ ...optimisticQuery, personMatch, offset: 0 })}
        />
        : null}
        <ResultStage
          query={optimisticQuery} results={results} pending={pending} locale={locale} localizeCountries={localizeCountries}
          sectionRef={sectionRef} headingRef={headingRef} onView={setView} onSort={setSort}
          onDirection={() => navigate({ ...optimisticQuery, dir: optimisticQuery.dir === "asc" ? "desc" : "asc", offset: 0 })}
          onPage={offset => navigate({ ...optimisticQuery, offset }, "page")} onClear={clear}
          showMatchedFacts={!collection}
        />
      </div>
    </div>
  );
}
