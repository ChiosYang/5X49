import { getTranslations } from "next-intl/server";
import { normalizeFilmPage, FILM_PAGE_SIZE } from "@/lib/film-pagination";
import { parseExploreQuery } from "@/lib/explore";
import { discoveryFailure, discoveryKeywords, discoveryReason, normalizeDiscoverySearch, parseDiscoveryPlan, type DiscoveryResolution, type DiscoveryState } from "@/lib/discovery-search";
import { getCollectionCatalog, getDiscoveryResolution, getLibraryFilmPage, getLocalPeople } from "@/lib/server-api";
import DiscoverySearch from "./DiscoverySearch";
import { parsePeopleIds } from "@/lib/search-plan";

const first = (value?: string | string[]) => Array.isArray(value) ? value[0] : value;
export default async function ExploreSearchPage({ params, searchParams }: {
  params: Promise<{ locale: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { locale } = await params;
  const search = await searchParams;
  const query = normalizeDiscoverySearch(search.q);
  const page = normalizeFilmPage(search.page);
  const peopleOffset = parseExploreQuery({ offset: search.people_offset }).offset;
  const collectionOffset = parseExploreQuery({ offset: search.collection_offset }).offset;
  const plan = parseDiscoveryPlan(first(search.p));
  const peopleIds = parsePeopleIds(first(search.people_ids));
  const state: DiscoveryState = { plan, personId: first(search.person_id), edited: first(search.edited) === "1",
    peopleIds: peopleIds ?? {}, offset: parseExploreQuery({ offset: search.offset }).offset, source: first(search.source) === "ai" ? "ai" : "local" };
  const explicitKeyword = first(search.mode) === "keyword" && query.length <= 200;
  let resolution: DiscoveryResolution | null = null;
  if (query && !explicitKeyword) {
    if (search.p !== undefined && !plan || peopleIds === null) resolution = discoveryFailure("invalid_request");
    else if (plan) resolution = await getDiscoveryResolution(query, locale, { plan, person_id: state.personId ?? null,
      people_ids: state.peopleIds, edited: state.edited, offset: state.offset });
    else if (["unsupported", "clarify", "unavailable", "needs_ai"].includes(first(search.state) ?? "")) {
      resolution = { ...discoveryFailure(discoveryReason(first(search.reason))), status: first(search.state) as DiscoveryResolution["status"] };
    } else resolution = await getDiscoveryResolution(query, locale);
    if (resolution.plan && !plan) {
      state.plan = resolution.plan; state.personId = resolution.person_id;
      state.peopleIds = resolution.people_ids ?? {};
      resolution = await getDiscoveryResolution(query, locale, { plan: state.plan, person_id: state.personId,
        people_ids: state.peopleIds, edited: false, offset: state.offset });
    }
  }
  let snapshot = null;
  if (query && (explicitKeyword || resolution?.status === "keyword")) {
    try {
      const keywords = discoveryKeywords(query);
      const [films, people, collections] = await Promise.all([
        getLibraryFilmPage(new URLSearchParams({ q: keywords, rank_exact: "true", limit: String(FILM_PAGE_SIZE), offset: String((page - 1) * FILM_PAGE_SIZE) })),
        getLocalPeople(keywords, peopleOffset), getCollectionCatalog({ query: keywords, offset: collectionOffset, limit: 12 }),
      ]);
      snapshot = { films, people, collections }; resolution = null;
    } catch { resolution = discoveryFailure("unavailable"); }
  }
  return <DiscoverySearch key={query} snapshot={snapshot} resolution={resolution} state={state} explicitKeyword={explicitKeyword}
    query={query} page={page} peopleOffset={peopleOffset} collectionOffset={collectionOffset} locale={locale} />;
}

export async function generateMetadata() {
  const t = await getTranslations("Collections");
  return { title: `${t("searchTitle")} — 5X49` };
}
