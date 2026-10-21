import { getTranslations } from "next-intl/server";
import { normalizeLibrarySearch } from "@/lib/library-search";
import { normalizeFilmPage, FILM_PAGE_SIZE } from "@/lib/film-pagination";
import { parseExploreQuery } from "@/lib/explore";
import { getCollectionCatalog, getLibraryFilmPage, getLocalPeople } from "@/lib/server-api";
import DiscoverySearch from "./DiscoverySearch";

export default async function ExploreSearchPage({ params, searchParams }: {
  params: Promise<{ locale: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { locale } = await params;
  const search = await searchParams;
  const query = normalizeLibrarySearch(search.q).slice(0, 100);
  const page = normalizeFilmPage(search.page);
  const peopleOffset = parseExploreQuery({ offset: search.people_offset }).offset;
  const collectionOffset = parseExploreQuery({ offset: search.collection_offset }).offset;
  const [films, people, collections] = query ? await Promise.all([
    getLibraryFilmPage(new URLSearchParams({ q: query, limit: String(FILM_PAGE_SIZE), offset: String((page - 1) * FILM_PAGE_SIZE) })),
    getLocalPeople(query, peopleOffset),
    getCollectionCatalog({ query, offset: collectionOffset, limit: 12 }),
  ]) : [null, null, null];
  return <DiscoverySearch key={query} snapshot={films && people && collections ? { films, people, collections } : null}
    query={query} page={page} peopleOffset={peopleOffset} collectionOffset={collectionOffset} locale={locale} />;
}

export async function generateMetadata() {
  const t = await getTranslations("Collections");
  return { title: `${t("searchTitle")} — 5X49` };
}
