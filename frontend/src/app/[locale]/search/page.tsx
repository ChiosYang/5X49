import { getTranslations } from "next-intl/server";
import { Link } from "@/i18n/routing";
import { getLibraryFilmPage } from "@/lib/server-api";
import { normalizeLibrarySearch } from "@/lib/library-search";
import { FILM_PAGE_SIZE, normalizeFilmPage } from "@/lib/film-pagination";
import FilmPagination from "@/components/FilmPagination";
import LibraryMovieCard from "../library/LibraryMovieCard";

export default async function SearchPage({ params, searchParams }: {
  params: Promise<{ locale: string }>;
  searchParams: Promise<{ q?: string | string[]; page?: string | string[] }>;
}) {
  const { locale } = await params;
  const search = await searchParams;
  const query = normalizeLibrarySearch(search.q);
  const page = normalizeFilmPage(search.page);
  const t = await getTranslations("LibrarySearch");
  const data = query ? await getLibraryFilmPage(new URLSearchParams({q:query,limit:String(FILM_PAGE_SIZE),offset:String((page-1)*FILM_PAGE_SIZE)})) : null;
  const films = data?.items ?? [];

  return (
    <main className="page-x min-h-screen bg-canvas pb-16 pt-36 text-ink">
      <h1 className="type-display-editorial">{t("title")}</h1>
      <p className="mt-4 text-ink-subtle">{t("description")}</p>
      <Link href="/ask" className="focus-ring mt-4 inline-block text-sm text-ink-muted underline">{t("askLink")}</Link>
      <form action={`/${locale}/search`} method="get" role="search" className="my-8 flex max-w-3xl flex-wrap gap-3">
        <label htmlFor="library-search" className="sr-only">{t("query")}</label>
        <input id="library-search" name="q" type="search" defaultValue={query} maxLength={200}
          placeholder={t("placeholder")} className="focus-ring min-h-12 min-w-0 flex-1 border border-line-strong bg-surface-raised px-4 text-base" />
        <button type="submit" className="focus-ring min-h-12 border border-line-strong bg-inverse px-6 font-bold text-inverse-ink">{t("submit")}</button>
        {query && <Link href="/search" className="focus-ring inline-flex min-h-12 items-center px-3 text-ink-muted">{t("clear")}</Link>}
      </form>
      <p className="mb-8 break-words text-ink-muted" role="status">
        {!query ? t("initial") : films.length ? t("results", { count: data!.total, query }) : t("empty", { query })}
      </p>
      <div className="grid grid-cols-2 gap-x-5 gap-y-10 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
        {films.map((film, index) => <LibraryMovieCard key={film.id} movie={film} priority={index === 0} />)}
      </div>
      {data && <FilmPagination data={data} href={`/search?${new URLSearchParams({q:query})}`} />}
    </main>
  );
}
