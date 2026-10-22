import { getTranslations } from "next-intl/server";

import { parseExploreQuery } from "@/lib/explore";
import { collectionCategory, hasLegacyExploreQuery } from "@/lib/collections";
import { getCollectionCatalog } from "@/lib/server-api";
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
  const search = normalizeDiscoverySearch(resolvedSearchParams.q);
  if (search) redirect({ href: discoveryHref(search), locale });
  if (hasLegacyExploreQuery(resolvedSearchParams)) redirect({ href: "/explore", locale });
  const category = collectionCategory(resolvedSearchParams.category);
  const { offset } = parseExploreQuery({ offset: resolvedSearchParams.offset });
  return <CollectionBrowse catalog={await getCollectionCatalog({ category, offset })} locale={locale} category={category} offset={offset} />;
}

export async function generateMetadata() {
  const t = await getTranslations("Collections");
  return { title: `${t("homeTitle")} · 5X49` };
}
