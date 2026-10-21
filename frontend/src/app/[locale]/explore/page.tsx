import { getTranslations } from "next-intl/server";

import { parseExploreQuery } from "@/lib/explore";
import { hasLegacyExploreQuery } from "@/lib/collections";
import { getCollectionCatalog, getExploreFilms } from "@/lib/server-api";
import ExploreClient from "./ExploreClient";
import CollectionBrowse from "./CollectionBrowse";
import { redirect } from "@/i18n/routing";
import { discoveryHref, normalizeDiscoverySearch } from "@/lib/discovery-search";


interface ExplorePageProps {
  params: Promise<{ locale: string }>;
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
}

export default async function ExplorePage({ params, searchParams }: ExplorePageProps) {
  const { locale } = await params;
  const resolvedSearchParams = searchParams ? await searchParams : {};
  if (!hasLegacyExploreQuery(resolvedSearchParams)) {
    const search = normalizeDiscoverySearch(resolvedSearchParams.q);
    if (search) redirect({ href: discoveryHref(search), locale });
    return <CollectionBrowse catalog={await getCollectionCatalog({ featured: true, limit: 3 })} locale={locale} />;
  }
  const query = parseExploreQuery({
    genre: resolvedSearchParams.genre,
    person: resolvedSearchParams.person,
    person_match: resolvedSearchParams.person_match,
    country: resolvedSearchParams.country,
    decade: resolvedSearchParams.decade,
    view: resolvedSearchParams.view,
    sort: resolvedSearchParams.sort,
    dir: resolvedSearchParams.dir,
    offset: resolvedSearchParams.offset,
  });
  return <ExploreClient locale={locale} query={query} results={await getExploreFilms(query)} />;
}

export async function generateMetadata() {
  const t = await getTranslations("Explore");
  return { title: `${t("title")} · 5X49` };
}
