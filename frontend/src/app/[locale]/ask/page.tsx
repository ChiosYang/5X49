import { redirect } from "@/i18n/routing";
import { discoveryHref, normalizeDiscoverySearch } from "@/lib/discovery-search";

export default async function AskPage({ params, searchParams }: {
  params: Promise<{ locale: string }>;
  searchParams: Promise<{ q?: string | string[] }>;
}) {
  const { locale } = await params;
  const search = await searchParams;
  redirect({ href: discoveryHref(normalizeDiscoverySearch(search.q)), locale });
}
