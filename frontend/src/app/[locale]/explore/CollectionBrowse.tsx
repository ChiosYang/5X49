"use client";

import { useEffect, useOptimistic, useSyncExternalStore, useTransition } from "react";
import Image from "next/image";
import { Film, Search } from "lucide-react";
import { useTranslations } from "next-intl";
import { Link, useRouter } from "@/i18n/routing";
import { ButtonLink } from "@/components/ui/Button";
import LibraryMovieCard from "@/app/[locale]/library/LibraryMovieCard";
import { API } from "@/lib/api";
import { COLLECTION_CATEGORIES, catalogHref, collectionHref } from "@/lib/collections";
import { correctedExploreOffset, formatExploreFacetLabel } from "@/lib/explore";
import { useExploreBrowsePosition, useExploreRefresh } from "@/hooks/useExploreRefresh";
import type { CollectionCatalog, CollectionCategory, LocalCollection } from "@/types/movie";
import UnifiedSearchInput from "./UnifiedSearchInput";
import { useDiscoveryNavigation } from "./DiscoverySearchSession";

const subscribe = () => () => {};

export function useCollectionTitle(locale: string) {
  const t = useTranslations("Collections");
  const localized = useSyncExternalStore(subscribe, () => true, () => false);
  return (item: LocalCollection) => t(`titles.${item.kind}`, { label: formatExploreFacetLabel(
    item.kind === "director" || item.kind === "person" ? "person" : item.kind,
    item.key, item.label, locale, localized,
  ) });
}

export function CollectionDirectoryEntry({ item, locale }: { item: LocalCollection; locale: string }) {
  const t = useTranslations("Collections");
  const title = useCollectionTitle(locale);
  return <Link prefetch={false} href={collectionHref(item)} className="focus-ring duration-standard group block min-w-0 border-b border-line pb-5 transition-colors hover:border-ink-muted">
    <div className="mb-4 grid grid-cols-3 gap-2" aria-hidden="true">
      {item.previews.slice(0, 3).map(film => {
        const artwork = film.primary_item.artwork;
        const local = artwork?.poster_thumb_local || artwork?.poster_local;
        const src = local ? API.mediaUrl(local) : artwork?.poster_provider ? API.providerArtworkUrl(artwork.poster_provider) : null;
        return <div key={film.id} className="relative aspect-[2/3] overflow-hidden rounded-media bg-surface-raised">
          {src ? <Image src={src} alt="" fill sizes="(max-width: 640px) 28vw, 10vw" className="object-cover" /> : <Film className="absolute top-1/2 left-1/2 h-6 w-6 -translate-1/2 text-ink-disabled" />}
        </div>;
      })}
    </div>
    <p className="type-label text-ink-subtle">{t(`categories.${item.kind}`)}</p>
    <h2 className="mt-2 break-words font-serif text-2xl text-ink">{title(item)}</h2>
    <p className="mt-2 text-xs leading-5 text-ink-muted">{t("filmCount", { count: item.count })} · {t("unwatchedCount", { count: item.unwatched_count })}</p>
  </Link>;
}

export default function CollectionBrowse({ catalog, locale, directory = false, category = "all", offset = 0 }: {
  catalog: CollectionCatalog; locale: string; directory?: boolean; category?: CollectionCategory; offset?: number;
}) {
  const t = useTranslations("Collections");
  const title = useCollectionTitle(locale);
  const router = useRouter();
  const href = directory ? catalogHref(category, offset) : "/explore";
  const [activeHref, setActiveHref] = useOptimistic(href);
  const [pending, startTransition] = useTransition();
  const searchSession = useDiscoveryNavigation();
  const beginRead = useExploreRefresh(catalog, pending || searchSession.pending, activeHref, href);
  useExploreBrowsePosition(href);
  useEffect(() => {
    if (!directory || pending || activeHref !== href) return;
    const corrected = correctedExploreOffset(offset, catalog.total, catalog.limit);
    if (corrected !== offset) startTransition(() => {
      beginRead(catalogHref(category, corrected)); router.replace(catalogHref(category, corrected), { scroll: false });
    });
  }, [activeHref, beginRead, catalog.limit, catalog.total, category, directory, href, offset, pending, router]);
  function navigate(target: string) {
    searchSession.cancel();
    startTransition(() => { beginRead(target); setActiveHref(target); router.push(target); });
  }
  return <div className="page-x min-h-screen bg-canvas pb-24 pt-38 text-ink md:pt-44">
    {directory ? <nav aria-label={t("breadcrumb")} className="mb-5 text-sm text-ink-muted"><Link prefetch={false} href="/explore" scroll={false} className="focus-ring hover:text-ink">{t("homeTitle")}</Link></nav> : null}
    <header className="flex flex-col gap-6 border-b border-line pb-8 lg:flex-row lg:items-end lg:justify-between">
      <div><h1 className="type-display-editorial">{t(directory ? "directoryTitle" : "homeTitle")}</h1>
        <p className="mt-4 max-w-2xl text-sm leading-6 text-ink-muted">{t(directory ? "directoryDescription" : "homeDescription")}</p></div>
      <div className="flex flex-wrap gap-2">
        {directory ? <ButtonLink prefetch={false} href="/explore/search" icon={<Search className="h-4 w-4" />}>{t("searchTitle")}</ButtonLink> : null}
        {!directory ? <ButtonLink prefetch={false} href="/explore/collections" variant="ghost" size="sm">{t("directoryTitle")}</ButtonLink> : null}
        <ButtonLink prefetch={false} href="/explore/filter" variant="ghost" size="sm">{t("filterTitle")}</ButtonLink>
      </div>
    </header>
    {!directory ? <UnifiedSearchInput /> : null}
    {directory ? <nav aria-label={t("categoryLabel")} className="mt-6 flex flex-wrap gap-2">
      {COLLECTION_CATEGORIES.map(kind => <ButtonLink prefetch={false} key={kind} href={catalogHref(kind)} aria-current={category === kind ? "page" : undefined} variant={category === kind ? "primary" : "ghost"} size="sm"
        onNavigate={event => { event.preventDefault(); navigate(catalogHref(kind)); }}>{t(`categories.${kind}`)}{kind !== "all" ? ` (${catalog.categories[kind]})` : ""}</ButtonLink>)}
    </nav> : null}
    {catalog.items.length === 0 ? <section className="py-14">
      <h2 className="font-serif text-2xl">{t(catalog.total_films === 0 ? "emptyTitle" : "sparseTitle")}</h2>
      <p className="mt-3 max-w-xl text-sm leading-6 text-ink-muted">{t(catalog.total_films === 0 ? "emptyDescription" : "sparseDescription")}</p>
      <ButtonLink prefetch={false} href="/library" className="mt-6">{t("openLibrary")}</ButtonLink>
    </section> : directory ? <div className="mt-8 grid min-w-0 grid-cols-1 gap-x-8 gap-y-10 sm:grid-cols-2 lg:grid-cols-3" aria-busy={pending}>
      {catalog.items.map(item => <CollectionDirectoryEntry key={item.id} item={item} locale={locale} />)}
    </div> : <div className="space-y-14 pt-8">
      {catalog.items.map(item => <section key={item.id} aria-labelledby={`collection-${item.id}`}>
        <div className="flex items-end justify-between gap-4 border-b border-line pb-4">
          <div className="min-w-0">
            <p className="type-label text-ink-subtle">{t(`categories.${item.kind}`)}</p>
            <h2 id={`collection-${item.id}`} className="mt-2 break-words font-serif text-2xl sm:text-3xl"><Link prefetch={false} href={collectionHref(item)} className="focus-ring">{title(item)}</Link></h2>
            <p className="mt-2 text-xs text-ink-muted">{t("filmCount", { count: item.count })} · {t("unwatchedCount", { count: item.unwatched_count })}</p>
          </div>
          <ButtonLink prefetch={false} href={collectionHref(item)} size="sm" variant="ghost" aria-label={t("viewCollection", { title: title(item) })}>{t("viewAll")}</ButtonLink>
        </div>
        <div className="mt-5 grid grid-cols-2 gap-x-3 gap-y-6 sm:grid-cols-4">
          {item.previews.map(film => <div key={film.id} className="min-w-0"><LibraryMovieCard movie={film} /></div>)}
        </div>
      </section>)}
      <ButtonLink prefetch={false} href="/explore/collections">{t("directoryTitle")}</ButtonLink>
    </div>}
    {directory && (offset > 0 || catalog.next_offset !== null) ? <nav aria-label={t("directoryPages")} className="mt-10 flex flex-wrap items-center justify-between gap-4 border-t border-line pt-5">
      {offset > 0 ? <ButtonLink prefetch={false} href={catalogHref(category, Math.max(0, offset - catalog.limit))}>{t("previous")}</ButtonLink> : <span />}
      <span className="text-sm text-ink-muted">{Math.min(offset + 1, catalog.total)}–{Math.min(offset + catalog.items.length, catalog.total)} / {catalog.total}</span>
      {catalog.next_offset !== null ? <ButtonLink prefetch={false} href={catalogHref(category, catalog.next_offset)}>{t("next")}</ButtonLink> : <span />}
    </nav> : null}
  </div>;
}
