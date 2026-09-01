"use client";

import {
  useEffect,
  useLayoutEffect,
  useMemo,
  useOptimistic,
  useRef,
  useState,
  useSyncExternalStore,
  useTransition,
} from "react";
import { Compass, X } from "lucide-react";
import { useReducedMotion } from "framer-motion";
import { useTranslations } from "next-intl";

import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { useRouter } from "@/i18n/routing";
import {
  clearExploreFilters,
  exploreNavigation,
  hasExploreFilters,
  initialExploreLens,
  withExploreFacet,
  withoutExploreFacet,
  type ExploreQueryState,
} from "@/lib/explore";
import type {
  ExploreContext,
  ExploreContextItem,
  ExploreDimension,
  ExploreFacetSummary,
  ExploreFilmPage,
  ExploreOverview,
  ExploreView,
} from "@/types/movie";
import ExploreFactFinder from "./ExploreFactFinder";
import {
  ExploreHeader,
  LensDeck,
  LensPanel,
  QueryRibbon,
  ResultStage,
} from "./ExploreViews";

const subscribeHydration = () => () => {};
const getHydratedSnapshot = () => true;
const getServerSnapshot = () => false;
const desktopQuery = "(min-width: 1280px)";

function subscribeDesktop(callback: () => void) {
  const media = window.matchMedia(desktopQuery);
  media.addEventListener("change", callback);
  return () => media.removeEventListener("change", callback);
}

function getDesktopSnapshot() {
  return window.matchMedia(desktopQuery).matches;
}

function getDesktopServerSnapshot() {
  return false;
}

type RememberedFact = {
  label: string;
  roles?: string[];
};

export default function ExploreClient({
  context,
  locale,
  overview,
  query,
  results,
}: {
  context: ExploreContext;
  locale: string;
  overview: ExploreOverview;
  query: ExploreQueryState;
  results: ExploreFilmPage | null;
}) {
  const t = useTranslations("Explore");
  const router = useRouter();
  const reducedMotion = useReducedMotion() ?? false;
  const localizeCountries = useSyncExternalStore(
    subscribeHydration,
    getHydratedSnapshot,
    getServerSnapshot,
  );
  const isDesktop = useSyncExternalStore(
    subscribeDesktop,
    getDesktopSnapshot,
    getDesktopServerSnapshot,
  );
  const [optimisticQuery, setOptimisticQuery] = useOptimistic(query);
  const [pending, startTransition] = useTransition();
  const [activeLens, setActiveLens] = useState<ExploreDimension | null>(() => initialExploreLens(query));
  const [lensSheetOpen, setLensSheetOpen] = useState(false);
  const [finderOpen, setFinderOpen] = useState(false);
  const [finderDimension, setFinderDimension] = useState<ExploreDimension>(
    () => initialExploreLens(query) ?? "genre",
  );
  const [rememberedFacts, setRememberedFacts] = useState<Record<string, RememberedFact>>({});
  const resultSectionRef = useRef<HTMLElement>(null);
  const resultHeadingRef = useRef<HTMLHeadingElement>(null);
  const paginationTarget = useRef<number | null>(null);
  const filterScrollTarget = useRef<{ href: string; x: number; y: number } | null>(null);

  const hasFilters = hasExploreFilters(optimisticQuery);
  const resolvedLens = activeLens ?? initialExploreLens(optimisticQuery);
  const unresolved = useMemo(
    () => new Set((results?.unresolved_filters ?? []).map((item) => `${item.dimension}:${item.key}`)),
    [results],
  );
  const factLabels = useMemo(() => {
    const labels = new Map<string, RememberedFact>();
    overview.dimensions.forEach((entry) => {
      entry.items.forEach((item) => labels.set(`${entry.dimension}:${item.key}`, item));
    });
    context.dimensions.forEach((entry) => {
      entry.items.forEach((item) => labels.set(`${entry.dimension}:${item.key}`, item));
    });
    results?.filters.forEach((item) => labels.set(`${item.dimension}:${item.key}`, item));
    Object.entries(rememberedFacts).forEach(([key, fact]) => labels.set(key, fact));
    return labels;
  }, [context, overview, rememberedFacts, results]);

  const remember = (
    dimension: ExploreDimension,
    item: Pick<ExploreContextItem | ExploreFacetSummary, "key" | "label" | "roles">,
  ) => {
    setRememberedFacts((current) => ({
      ...current,
      [`${dimension}:${item.key}`]: { label: item.label, roles: item.roles },
    }));
  };

  const navigate = (next: ExploreQueryState, intent: "filter" | "page" = "filter") => {
    const navigation = exploreNavigation(next, intent);
    if (navigation.focusResults) {
      paginationTarget.current = next.offset;
      filterScrollTarget.current = null;
    } else {
      filterScrollTarget.current = {
        href: navigation.href,
        x: window.scrollX,
        y: window.scrollY,
      };
    }
    startTransition(() => {
      setOptimisticQuery(next);
      router.push(navigation.href, { scroll: navigation.scroll });
    });
  };

  const openLens = (dimension: ExploreDimension) => {
    setActiveLens(dimension);
    if (!isDesktop) setLensSheetOpen(true);
  };

  const openFinder = (dimension?: ExploreDimension) => {
    const target = dimension ?? resolvedLens ?? "genre";
    setFinderDimension(target);
    setFinderOpen(true);
  };

  const selectFact = (
    dimension: ExploreDimension,
    item: Pick<ExploreContextItem | ExploreFacetSummary, "key" | "label" | "roles">,
  ) => {
    remember(dimension, item);
    setActiveLens(dimension);
    setLensSheetOpen(false);
    navigate(withExploreFacet(optimisticQuery, dimension, item.key));
  };

  const removeFact = (dimension: ExploreDimension, key: string) => {
    const next = withoutExploreFacet(optimisticQuery, dimension, key);
    if (!hasExploreFilters(next)) {
      setActiveLens(null);
      setLensSheetOpen(false);
    }
    navigate(next);
  };

  const clearAll = () => {
    setActiveLens(null);
    setLensSheetOpen(false);
    navigate(clearExploreFilters(optimisticQuery));
  };

  const setView = (view: ExploreView) => navigate({ ...optimisticQuery, view, offset: 0 });
  const setSort = (sort: ExploreQueryState["sort"]) => navigate({
    ...optimisticQuery,
    sort,
    dir: sort === "year" ? "desc" : "asc",
    offset: 0,
  });
  const toggleDirection = () => navigate({
    ...optimisticQuery,
    dir: optimisticQuery.dir === "asc" ? "desc" : "asc",
    offset: 0,
  });
  const setPage = (offset: number) => navigate({ ...optimisticQuery, offset }, "page");

  useEffect(() => {
    const handleShortcut = (event: KeyboardEvent) => {
      const target = event.target;
      const editing = target instanceof HTMLElement && (
        target.matches("input, textarea, select") || target.isContentEditable
      );
      if (
        event.key !== "/" ||
        editing ||
        event.altKey ||
        event.ctrlKey ||
        event.metaKey ||
        finderOpen
      ) return;
      event.preventDefault();
      openFinder();
    };
    window.addEventListener("keydown", handleShortcut);
    return () => window.removeEventListener("keydown", handleShortcut);
  });

  useLayoutEffect(() => {
    const target = filterScrollTarget.current;
    if (!target || target.href !== exploreNavigation(query, "filter").href) return;
    window.scrollTo(target.x, target.y);
    const animationFrame = window.requestAnimationFrame(() => {
      window.scrollTo(target.x, target.y);
      if (filterScrollTarget.current === target) filterScrollTarget.current = null;
    });
    return () => window.cancelAnimationFrame(animationFrame);
  }, [query]);

  useEffect(() => {
    if (paginationTarget.current === null || paginationTarget.current !== query.offset || pending) return;
    paginationTarget.current = null;
    const animationFrame = window.requestAnimationFrame(() => {
      resultHeadingRef.current?.focus({ preventScroll: true });
      resultSectionRef.current?.scrollIntoView({
        behavior: reducedMotion ? "auto" : "smooth",
        block: "start",
      });
    });
    return () => window.cancelAnimationFrame(animationFrame);
  }, [pending, query.offset, reducedMotion, results]);

  return (
    <div className="page-x min-h-screen bg-canvas pb-24 pt-32 text-ink selection:bg-inverse selection:text-inverse-ink">
      <ExploreHeader total={overview.total_films} onFind={() => openFinder()} />

      {hasFilters ? (
        <div className="sticky top-0 z-sticky -mx-2 mt-5 bg-canvas/92 px-2 py-3 backdrop-blur-xl">
          <QueryRibbon
            query={optimisticQuery}
            labels={factLabels}
            unresolved={unresolved}
            locale={locale}
            localizeCountries={localizeCountries}
            onRemove={removeFact}
            onClear={clearAll}
          />
        </div>
      ) : null}

      <div className={`mt-9 min-w-0 ${resolvedLens ? "xl:grid xl:grid-cols-[minmax(0,1fr)_21rem] xl:gap-8" : ""}`}>
        <div className="min-w-0">
          {hasFilters ? (
            <ResultStage
              query={optimisticQuery}
              results={results}
              pending={pending}
              locale={locale}
              localizeCountries={localizeCountries}
              sectionRef={resultSectionRef}
              headingRef={resultHeadingRef}
              onView={setView}
              onSort={setSort}
              onDirection={toggleDirection}
              onPage={setPage}
              onClear={clearAll}
            />
          ) : (
            <LensDeck
              overview={overview}
              context={context}
              locale={locale}
              localizeCountries={localizeCountries}
              onOpenLens={openLens}
            />
          )}
        </div>

        {resolvedLens ? (
          <aside className="hidden min-w-0 border-l border-white/8 pl-7 xl:block">
            <div className="sticky top-36">
              <LensPanel
                activeDimension={resolvedLens}
                context={context}
                locale={locale}
                localizeCountries={localizeCountries}
                reducedMotion={reducedMotion}
                onChangeDimension={setActiveLens}
                onSelect={selectFact}
                onBrowseAll={openFinder}
              />
            </div>
          </aside>
        ) : null}
      </div>

      {hasFilters && resolvedLens ? (
        <div className="fixed inset-x-0 bottom-5 z-sticky flex justify-center px-4 xl:hidden">
          <Button className="shadow-2xl" variant="primary" onClick={() => setLensSheetOpen(true)}>
            <Compass className="h-4 w-4" />
            {t("continueExplore")}
          </Button>
        </div>
      ) : null}

      <Dialog
        animated={!reducedMotion}
        open={lensSheetOpen && Boolean(resolvedLens)}
        onClose={() => setLensSheetOpen(false)}
        closeLabel={t("closeLens")}
        ariaLabel={t("currentLens")}
        placement="bottom"
        size="md"
        panelClassName="max-h-[calc(100dvh-2rem)] overflow-y-auto rounded-t-[1.75rem] p-5 sm:rounded-[1.75rem] sm:p-6"
      >
        <div className="mb-4 flex justify-end">
          <button
            type="button"
            onClick={() => setLensSheetOpen(false)}
            aria-label={t("closeLens")}
            className="rounded-full border border-white/10 p-2 text-white/45 outline-none hover:bg-white/5 hover:text-white focus-visible:ring-2 focus-visible:ring-gold/60"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        {resolvedLens ? (
          <LensPanel
            activeDimension={resolvedLens}
            context={context}
            locale={locale}
            localizeCountries={localizeCountries}
            reducedMotion={reducedMotion}
            onChangeDimension={setActiveLens}
            onSelect={selectFact}
            onBrowseAll={(dimension) => {
              setLensSheetOpen(false);
              openFinder(dimension);
            }}
          />
        ) : null}
      </Dialog>

      <ExploreFactFinder
        open={finderOpen}
        dimension={finderDimension}
        locale={locale}
        localizeCountries={localizeCountries}
        reducedMotion={reducedMotion}
        onDimensionChange={setFinderDimension}
        onClose={() => setFinderOpen(false)}
        onSelect={selectFact}
      />
    </div>
  );
}
