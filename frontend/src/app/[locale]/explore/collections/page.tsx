import { getTranslations } from "next-intl/server";
import { catalogHref, collectionCategory } from "@/lib/collections";
import { parseExploreQuery } from "@/lib/explore";
import { redirect } from "@/i18n/routing";

export default async function CollectionsPage({ params, searchParams }: {
  params: Promise<{ locale: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { locale } = await params;
  const search = await searchParams;
  const category = collectionCategory(search.category);
  const { offset } = parseExploreQuery(search);
  redirect({ href: catalogHref(category, offset), locale });
}

export async function generateMetadata() {
  const t = await getTranslations("Collections");
  return { title: `${t("directoryTitle")} — 5X49` };
}
