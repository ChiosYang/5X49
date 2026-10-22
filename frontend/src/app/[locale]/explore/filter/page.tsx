import { redirect } from "@/i18n/routing";
import { discoveryHref, normalizeDiscoverySearch } from "@/lib/discovery-search";

export default async function ExploreFilterPage({ params, searchParams }: {
  params: Promise<{ locale: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { locale } = await params;
  const query = normalizeDiscoverySearch((await searchParams).q);
  redirect({ href: query ? discoveryHref(query) : "/explore", locale });
}
