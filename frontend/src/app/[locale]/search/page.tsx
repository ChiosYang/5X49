import { getTranslations } from "next-intl/server";
import { Link } from "@/i18n/routing";
import { getLibraryFilms } from "@/lib/server-api";
import { normalizeLibrarySearch } from "@/lib/library-search";
import LibraryMovieCard from "../library/LibraryMovieCard";

export default async function SearchPage({ params, searchParams }: {
  params: Promise<{ locale: string }>;
  searchParams: Promise<{ q?: string | string[] }>;
}) {
  const { locale } = await params;
  const query = normalizeLibrarySearch((await searchParams).q);
  const t = await getTranslations("LibrarySearch");
  const films = query ? await getLibraryFilms(query) : [];

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
        {!query ? t("initial") : films.length ? t("results", { count: films.length, query }) : t("empty", { query })}
      </p>
      <div className="grid grid-cols-2 gap-x-5 gap-y-10 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
        {films.map((film, index) => <LibraryMovieCard key={film.id} movie={film} priority={index === 0} />)}
      </div>
    </main>
  );
}
