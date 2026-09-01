import { getTranslations } from "next-intl/server";

import { hasExploreFilters, parseExploreQuery } from "@/lib/explore";
import { getExploreContext, getExploreFilms, getExploreOverview } from "@/lib/server-api";
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
    country: resolvedSearchParams.country,
    decade: resolvedSearchParams.decade,
    view: resolvedSearchParams.view,
    sort: resolvedSearchParams.sort,
    dir: resolvedSearchParams.dir,
    offset: resolvedSearchParams.offset,
  });
  const [overview, context, results] = await Promise.all([
    getExploreOverview(),
    getExploreContext(query),
    hasExploreFilters(query) ? getExploreFilms(query) : Promise.resolve(null),
  ]);
  return <ExploreClient context={context} locale={locale} overview={overview} query={query} results={results} />;
}

export async function generateMetadata() {
  const t = await getTranslations("Explore");
  return { title: `${t("title")} · 5X49` };
}
