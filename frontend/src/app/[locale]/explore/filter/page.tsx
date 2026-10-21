import { getTranslations } from "next-intl/server";
import { parseExploreQuery } from "@/lib/explore";
import { getExploreFilms } from "@/lib/server-api";
import ExploreClient from "../ExploreClient";

export default async function ExploreFilterPage({ params, searchParams }: {
  params: Promise<{ locale: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { locale } = await params;
  const query = parseExploreQuery(await searchParams);
  return <ExploreClient basePath="/explore/filter" locale={locale} query={query} results={await getExploreFilms(query)} />;
}

export async function generateMetadata() {
  const t = await getTranslations("Collections");
  return { title: `${t("filterTitle")} — 5X49` };
}
