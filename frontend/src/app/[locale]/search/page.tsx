import { redirect } from "@/i18n/routing";
import { librarySearchHref } from "@/lib/library-search";
import { normalizeFilmPage } from "@/lib/film-pagination";

export default async function SearchPage({ params, searchParams }: {
  params: Promise<{ locale: string }>;
  searchParams: Promise<{ q?: string | string[]; page?: string | string[] }>;
}) {
  const { locale } = await params;
  const search = await searchParams;
  redirect({ href: librarySearchHref(search.q, normalizeFilmPage(search.page)), locale });
}
