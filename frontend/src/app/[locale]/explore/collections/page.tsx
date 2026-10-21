import { getTranslations } from "next-intl/server";
import { collectionCategory } from "@/lib/collections";
import { parseExploreQuery } from "@/lib/explore";
import { getCollectionCatalog } from "@/lib/server-api";
import CollectionBrowse from "../CollectionBrowse";

export default async function CollectionsPage({ params, searchParams }: {
  params: Promise<{ locale: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { locale } = await params;
  const search = await searchParams;
  const category = collectionCategory(search.category);
  const { offset } = parseExploreQuery(search);
  const catalog = await getCollectionCatalog({ category, offset });
  return <CollectionBrowse directory catalog={catalog} locale={locale} category={category} offset={offset} />;
}

export async function generateMetadata() {
  const t = await getTranslations("Collections");
  return { title: `${t("directoryTitle")} — 5X49` };
}
