"use client";

import { useEffect, useLayoutEffect, useMemo, useOptimistic, useRef, useState, useSyncExternalStore, useTransition } from "react";
import { useReducedMotion } from "framer-motion";
import { useTranslations } from "next-intl";

import { useRouter } from "@/i18n/routing";
import { clearExploreFilters, exploreNavigation, hasExploreFilters, withExploreFacet, withoutExploreFacet, type ExploreQueryState } from "@/lib/explore";
import type { ExploreCollection, ExploreCollections, ExploreDimension, ExploreFacetSummary, ExploreFilmPage, ExploreView } from "@/types/movie";
import ExploreSearch from "./ExploreSearch";
import { CollectionEntries, QueryRibbon, ResultStage } from "./ExploreViews";

const subscribeHydration = () => () => {};
const getHydratedSnapshot = () => true;
const getServerSnapshot = () => false;

export default function ExploreClient({ collections, locale, query, results }: {
  collections: ExploreCollections | null;
  locale: string;
  query: ExploreQueryState;
  results: ExploreFilmPage;
}) {
  const t = useTranslations("Explore");
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
  const filtered = hasExploreFilters(optimisticQuery);
  const labels = useMemo(() => {
    const map = new Map(Object.entries(remembered));
    collections?.items.forEach(item => map.set(`${item.dimension}:${item.key}`, { label: item.label }));
    results.filters.forEach(item => map.set(`${item.dimension}:${item.key}`, item));
    return map;
  }, [collections, remembered, results]);
  const unresolved = useMemo(() => new Set(results.unresolved_filters.map(item => `${item.dimension}:${item.key}`)), [results]);

  const navigate = (next: ExploreQueryState, intent: "filter" | "page" = "filter") => {
    const navigation = exploreNavigation(next, intent);
    paginationTarget.current = navigation.focusResults ? navigation.href : null;
    scrollTarget.current = navigation.focusResults ? null : { href: navigation.href, x: window.scrollX, y: window.scrollY };
    startTransition(() => {
      setOptimisticQuery(next);
      router.push(navigation.href, { scroll: navigation.scroll });
    });
  };
  const select = (dimension: ExploreDimension, item: Pick<ExploreFacetSummary, "key" | "label" | "roles">) => {
    if (optimisticQuery[dimension].includes(item.key)) return;
    setRemembered(current => ({ ...current, [`${dimension}:${item.key}`]: item }));
    navigate(withExploreFacet(optimisticQuery, dimension, item.key));
  };
  const openCollection = (item: ExploreCollection) => {
    setRemembered(current => ({ ...current, [`${item.dimension}:${item.key}`]: { label: item.label } }));
    navigate({ ...clearExploreFilters(optimisticQuery), [item.dimension]: [item.key], view: item.view });
  };
  const clear = () => navigate(clearExploreFilters(optimisticQuery));
  const setView = (view: ExploreView) => navigate({ ...optimisticQuery, view, offset: 0 });
  const setSort = (sort: ExploreQueryState["sort"]) => navigate({ ...optimisticQuery, sort, dir: sort === "year" ? "desc" : "asc", offset: 0 });

  const refreshAfterProfileSaved = () => {
    const activeQuery = activeQueryRef.current;
    // An in-flight card save may finish after its card or Explore route is left.
    // Keep the latest query; never refresh a different page or a detail overlay.
    if (!activeQuery || !/\/explore\/?$/.test(window.location.pathname)) return;
    scrollTarget.current = {
      href: exploreNavigation(activeQuery, "filter").href,
      x: window.scrollX,
      y: window.scrollY,
    };
    // These results and collections are RSC props, outside the card's SWR caches.
    // Refresh the current route once after a successful save, without pushing history.
    startTransition(() => router.refresh());
  };

  useLayoutEffect(() => {
    const target = scrollTarget.current;
    if (!target || target.href !== exploreNavigation(query, "filter").href) return;
    window.scrollTo(target.x, target.y);
    const frame = window.requestAnimationFrame(() => {
      window.scrollTo(target.x, target.y);
      if (scrollTarget.current === target) scrollTarget.current = null;
    });
    return () => window.cancelAnimationFrame(frame);
  }, [query]);
  useEffect(() => {
    if (pending || paginationTarget.current !== exploreNavigation(query, "page").href) return;
    paginationTarget.current = null;
    const frame = window.requestAnimationFrame(() => {
      headingRef.current?.focus({ preventScroll: true });
      sectionRef.current?.scrollIntoView({ behavior: reducedMotion ? "auto" : "smooth", block: "start" });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [pending, query, reducedMotion]);

  return (
    <div className="page-x min-h-screen bg-canvas pb-24 pt-38 text-ink selection:bg-inverse selection:text-inverse-ink md:pt-44">
      <header className="flex flex-col gap-7 border-b border-line pb-8 lg:flex-row lg:items-end lg:justify-between">
        <div><h1 className="type-display-editorial">{t("title")}</h1></div>
      </header>
      <div className="mt-6 min-w-0 space-y-8">
        {!filtered && collections ? <CollectionEntries collections={collections} emptyView={results.total === 0} locale={locale} localizeCountries={localizeCountries} onSelect={openCollection} /> : null}
        <ExploreSearch query={optimisticQuery} locale={locale} localizeCountries={localizeCountries} onSelect={select} />
        <QueryRibbon
          query={optimisticQuery} labels={labels} unresolved={unresolved} locale={locale} localizeCountries={localizeCountries}
          onRemove={(dimension, key) => navigate(withoutExploreFacet(optimisticQuery, dimension, key))}
          onClear={clear}
          onPersonMatch={personMatch => navigate({ ...optimisticQuery, personMatch, offset: 0 })}
        />
        <ResultStage
          query={optimisticQuery} results={results} pending={pending} locale={locale} localizeCountries={localizeCountries}
          sectionRef={sectionRef} headingRef={headingRef} onView={setView} onSort={setSort}
          onDirection={() => navigate({ ...optimisticQuery, dir: optimisticQuery.dir === "asc" ? "desc" : "asc", offset: 0 })}
          onPage={offset => navigate({ ...optimisticQuery, offset }, "page")} onClear={clear}
          onProfileSaved={refreshAfterProfileSaved}
        />
      </div>
    </div>
  );
}
