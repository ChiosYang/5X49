import { getTranslations } from "next-intl/server";
import { Link } from "@/i18n/routing";
import { filmPageHref } from "@/lib/film-pagination";
import type { LibraryFilmPage } from "@/types/movie";

export default async function FilmPagination({ data, href }: {data: LibraryFilmPage; href: string}) {
  const t = await getTranslations("Pagination");
  const page = Math.floor(data.offset / data.limit) + 1;
  const pages = Math.max(1, Math.ceil(data.total / data.limit));
  if (pages === 1) return null;
  return <nav aria-label={t("label")} className="mt-12 flex flex-wrap items-center justify-between gap-4 border-t border-line pt-6">
    {page > 1 ? <Link className="focus-ring inline-flex min-h-11 items-center border border-line px-4" href={filmPageHref(href,page-1)}>{t("previous")}</Link> : <span />}
    <p className="text-sm text-ink-subtle" role="status">{t("position", {page,pages,total:data.total})}</p>
    {page < pages ? <Link className="focus-ring inline-flex min-h-11 items-center border border-line px-4" href={filmPageHref(href,page+1)}>{t("next")}</Link> : <span />}
  </nav>;
}
