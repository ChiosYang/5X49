import { getTranslations } from "next-intl/server";

import { hasExploreFilters, parseExploreQuery } from "@/lib/explore";
import { getExploreCollections, getExploreFilms } from "@/lib/server-api";
import ExploreClient from "./ExploreClient";


interface ExplorePageProps {
  params: Promise<{ locale: string }>;
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
}

export default async function ExplorePage({ params, searchParams }: ExplorePageProps) {
  const { locale } = await params;
  const resolvedSearchParams = searchParams ? await searchParams : {};
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
  const [collections, results] = await Promise.all([
    hasExploreFilters(query) ? Promise.resolve(null) : getExploreCollections(query.view),
    getExploreFilms(query),
  ]);
  return <ExploreClient collections={collections} locale={locale} query={query} results={results} />;
}

export async function generateMetadata() {
  const t = await getTranslations("Explore");
  return { title: `${t("title")} · 5X49` };
}
