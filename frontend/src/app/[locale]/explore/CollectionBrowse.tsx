"use client";

import { useEffect, useOptimistic, useSyncExternalStore, useTransition } from "react";
import Image from "next/image";
import { Film } from "lucide-react";
import { useTranslations } from "next-intl";
import { Link, useRouter } from "@/i18n/routing";
import { ButtonLink } from "@/components/ui/Button";
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

function previewPosterSrc(film: LocalCollection["previews"][number]) {
  const artwork = film.primary_item.artwork;
  const local = artwork?.poster_thumb_local || artwork?.poster_local;
  return local ? API.mediaUrl(local) : artwork?.poster_provider ? API.providerArtworkUrl(artwork.poster_provider) : null;
}

export function CollectionDirectoryEntry({ item, locale }: { item: LocalCollection; locale: string }) {
  const t = useTranslations("Collections");
  const title = useCollectionTitle(locale);
  const posters = item.previews.slice(0, 3).map((film) => ({ id: film.id, src: previewPosterSrc(film) }));
  const lead = posters[0];
  const second = posters[1];
  const third = posters[2];
  return (
    <Link prefetch={false} href={collectionHref(item)} className="focus-ring group block min-w-0">
      <div
        aria-hidden="true"
        className={`relative transition-transform duration-standard group-hover:-translate-y-0.5 ${
          third ? "pt-2 pr-4" : second ? "pt-1.5 pr-2.5" : ""
        }`}
      >
        {third ? (
          <div className="duration-standard absolute top-0 right-0 bottom-3.5 left-4 overflow-hidden rounded-control border border-line-strong/60 bg-surface-raised opacity-45 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5">
            {third.src ? <Image src={third.src} alt="" fill sizes="(max-width: 640px) 42vw, 18vw" className="object-cover brightness-75" /> : null}
          </div>
        ) : null}
        {second ? (
          <div className={`duration-standard absolute top-1 bottom-1.5 left-2 overflow-hidden rounded-control border border-line-strong/80 bg-surface-raised opacity-75 transition-transform group-hover:translate-x-0.5 ${third ? "right-2" : "right-0"}`}>
            {second.src ? <Image src={second.src} alt="" fill sizes="(max-width: 640px) 42vw, 18vw" className="object-cover brightness-85" /> : null}
          </div>
        ) : null}
        <div className="relative aspect-[2/3] overflow-hidden rounded-control border border-line-strong bg-surface-raised shadow-[0_14px_32px_rgba(0,0,0,0.65)]">
          {lead?.src ? (
            <Image src={lead.src} alt="" fill sizes="(max-width: 640px) 44vw, (max-width: 1024px) 30vw, 18vw" className="duration-standard object-cover transition-transform group-hover:scale-[1.03]" />
          ) : (
            <Film className="absolute top-1/2 left-1/2 h-6 w-6 -translate-1/2 text-ink-disabled" />
          )}
        </div>
      </div>
      <div className="duration-standard mt-4 border-t border-line pt-3 transition-colors group-hover:border-line-strong">
        <p className="type-badge text-ink-subtle">{t(`categories.${item.kind}`)}</p>
        <h3 className="mt-1.5 break-words text-lg font-semibold tracking-tight text-ink">{title(item)}</h3>
        <p className="mt-1 text-xs leading-5 text-ink-subtle">{t("filmCount", { count: item.count })} · {t("unwatchedCount", { count: item.unwatched_count })}</p>
      </div>
    </Link>
  );
}

export default function CollectionBrowse({ catalog, locale, category = "all", offset = 0 }: {
  catalog: CollectionCatalog; locale: string; category?: CollectionCategory; offset?: number;
}) {
  const t = useTranslations("Collections");
  const router = useRouter();
  const href = catalogHref(category, offset);
  const [activeHref, setActiveHref] = useOptimistic(href);
  const [pending, startTransition] = useTransition();
  const searchSession = useDiscoveryNavigation();
  const beginRead = useExploreRefresh(catalog, pending || searchSession.pending, activeHref, href);
  useExploreBrowsePosition(href);
  useEffect(() => {
    if (pending || activeHref !== href) return;
    const corrected = correctedExploreOffset(offset, catalog.total, catalog.limit);
    if (corrected !== offset) startTransition(() => {
      const target = catalogHref(category, corrected);
      beginRead(target); setActiveHref(target); router.replace(target, { scroll: false });
    });
  }, [activeHref, beginRead, catalog.limit, catalog.total, category, href, offset, pending, router, setActiveHref]);
  function navigate(target: string) {
    searchSession.cancel();
    startTransition(() => { beginRead(target); setActiveHref(target); router.push(target); });
  }
  return <div className="page-x min-h-screen bg-canvas pb-24 pt-32 text-ink md:pt-36">
    <header className="flex flex-col gap-4 border-b border-line pb-8 lg:flex-row lg:items-start lg:justify-between lg:gap-8">
      <h1 className="type-display-editorial shrink-0">{t("homeTitle")}</h1>
      <div className="w-full lg:max-w-xl lg:pt-3">
        <UnifiedSearchInput />
      </div>
    </header>
    <section aria-labelledby="collection-directory-title" className="pt-8">
    <div className="flex flex-col gap-4 border-b border-line pb-4 sm:flex-row sm:items-end sm:justify-between">
      <h2 id="collection-directory-title" className="type-section-title text-ink">{t("directoryTitle")}</h2>
      <nav aria-label={t("categoryLabel")} className="flex flex-wrap items-center gap-x-5 gap-y-2">
        {COLLECTION_CATEGORIES.map(kind => {
          const active = category === kind;
          return (
            <Link
              prefetch={false}
              key={kind}
              href={catalogHref(kind)}
              aria-current={active ? "page" : undefined}
              onNavigate={event => { event.preventDefault(); navigate(catalogHref(kind)); }}
              className={`focus-ring duration-fast inline-flex min-h-9 items-center border-b-2 text-xs font-medium tracking-wider transition-colors ${
                active ? "border-ink text-ink" : "border-transparent text-ink-subtle hover:text-ink"
              }`}
            >
              {t(`categories.${kind}`)}{kind !== "all" ? ` (${catalog.categories[kind]})` : ""}
            </Link>
          );
        })}
      </nav>
    </div>
    {catalog.items.length === 0 ? <section className="py-14">
      <h3 className="text-2xl font-semibold text-ink">{t(catalog.total_films === 0 ? "emptyTitle" : "sparseTitle")}</h3>
      <p className="mt-3 max-w-xl text-sm leading-6 text-ink-muted">{t(catalog.total_films === 0 ? "emptyDescription" : "sparseDescription")}</p>
      <ButtonLink prefetch={false} href="/library" className="mt-6">{t("openLibrary")}</ButtonLink>
    </section> : <div className="mt-8 grid min-w-0 grid-cols-2 gap-x-5 gap-y-10 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 xl:gap-x-7 xl:gap-y-12" aria-busy={pending}>
      {catalog.items.map(item => <CollectionDirectoryEntry key={item.id} item={item} locale={locale} />)}
    </div>}
    {(offset > 0 || catalog.next_offset !== null) ? <nav aria-label={t("directoryPages")} className="mt-10 flex flex-wrap items-center justify-between gap-4 border-t border-line pt-5">
      {offset > 0 ? <ButtonLink prefetch={false} href={catalogHref(category, Math.max(0, offset - catalog.limit))} onNavigate={event => { event.preventDefault(); navigate(catalogHref(category, Math.max(0, offset - catalog.limit))); }}>{t("previous")}</ButtonLink> : <span />}
      <span className="text-sm text-ink-muted">{Math.min(offset + 1, catalog.total)}–{Math.min(offset + catalog.items.length, catalog.total)} / {catalog.total}</span>
      {catalog.next_offset !== null ? <ButtonLink prefetch={false} href={catalogHref(category, catalog.next_offset)} onNavigate={event => { event.preventDefault(); navigate(catalogHref(category, catalog.next_offset!)); }}>{t("next")}</ButtonLink> : <span />}
    </nav> : null}
    </section>
  </div>;
}
