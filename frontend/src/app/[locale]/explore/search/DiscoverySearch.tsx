"use client";

import { useEffect, useOptimistic, useRef, useState, useTransition, type FormEvent } from "react";
import { useTranslations } from "next-intl";
import { Link, useRouter } from "@/i18n/routing";
import { Button, ButtonLink } from "@/components/ui/Button";
import { TextInput } from "@/components/ui/FormControls";
import { Spinner } from "@/components/ui/Feedback";
import LibraryMovieCard from "@/app/[locale]/library/LibraryMovieCard";
import { useExploreRefresh } from "@/hooks/useExploreRefresh";
import { collectionHref, discoverySearchHref } from "@/lib/collections";
import { normalizeLibrarySearch } from "@/lib/library-search";
import type { CollectionCatalog, ExploreFacetPage, LibraryFilmPage } from "@/types/movie";
import { CollectionDirectoryEntry } from "../CollectionBrowse";

export interface DiscoverySnapshot {
  films: LibraryFilmPage;
  people: ExploreFacetPage;
  collections: CollectionCatalog;
}

export default function DiscoverySearch({ snapshot, query, page, peopleOffset, collectionOffset, locale }: {
  snapshot: DiscoverySnapshot | null; query: string; page: number; peopleOffset: number; collectionOffset: number; locale: string;
}) {
  const t = useTranslations("Collections");
  const searchT = useTranslations("LibrarySearch");
  const router = useRouter();
  const href = discoverySearchHref(query, page, peopleOffset, collectionOffset);
  const [activeHref, setActiveHref] = useOptimistic(href);
  const [pending, startTransition] = useTransition();
  const [draft, setDraft] = useState(query);
  const composing = useRef(false);
  useExploreRefresh(snapshot, pending, activeHref, href);
  function navigate(target: string) {
    startTransition(() => { setActiveHref(target); router.push(target, { scroll: false }); });
  }
  function submit(event: FormEvent) {
    event.preventDefault();
    if (!composing.current) navigate(discoverySearchHref(normalizeLibrarySearch(draft).slice(0, 100)));
  }
  useEffect(() => {
    if (!snapshot || pending || activeHref !== href || snapshot.films.total === 0) return;
    const lastPage = Math.max(1, Math.ceil(snapshot.films.total / snapshot.films.limit));
    if (page > lastPage) startTransition(() => router.replace(discoverySearchHref(query, lastPage, peopleOffset, collectionOffset), { scroll: false }));
  }, [activeHref, collectionOffset, href, page, pending, peopleOffset, query, router, snapshot]);
  return <div className="page-x min-h-screen bg-canvas pb-24 pt-38 text-ink md:pt-44">
    <nav aria-label={t("breadcrumb")} className="mb-5 text-sm text-ink-muted"><Link prefetch={false} href="/explore" scroll={false} className="focus-ring hover:text-ink">{t("homeTitle")}</Link></nav>
    <header className="border-b border-line pb-8">
      <h1 className="type-display-editorial">{t("searchTitle")}</h1>
      <p className="mt-4 max-w-2xl text-sm leading-6 text-ink-muted">{t("searchDescription")}</p>
      <form role="search" aria-label={t("searchTitle")} onSubmit={submit} className="mt-6 flex max-w-2xl gap-2">
        <label htmlFor="collection-search" className="sr-only">{searchT("query")}</label>
        <TextInput id="collection-search" type="search" value={draft} maxLength={100} autoFocus
          onChange={event => setDraft(event.target.value)} placeholder={t("searchPlaceholder")}
          onCompositionStart={() => { composing.current = true; }} onCompositionEnd={() => { composing.current = false; }}
          onKeyDown={event => { if (event.key === "Enter" && (composing.current || event.nativeEvent.isComposing || event.keyCode === 229)) event.preventDefault(); }} />
        <Button type="submit" variant="primary">{searchT("submit")}</Button>
      </form>
      <ButtonLink prefetch={false} href="/explore/filter" className="mt-4" variant="ghost" size="sm">{t("filterTitle")}</ButtonLink>
    </header>
    {!snapshot ? <p className="py-10 text-sm text-ink-muted">{t("searchInitial")}</p> : <div className="space-y-12 pt-8" aria-busy={pending}>
      <section aria-labelledby="search-collections-title">
        <h2 id="search-collections-title" className="font-serif text-2xl">{t("collectionResults", { count: snapshot.collections.total })}</h2>
        {snapshot.collections.items.length ? <div className="mt-5 grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">{snapshot.collections.items.map(item => <CollectionDirectoryEntry key={item.id} item={item} locale={locale} />)}</div> : <p className="mt-3 text-sm text-ink-muted">{t("noCollections")}</p>}
        <SearchPages label={t("collectionPages")} previous={collectionOffset > 0 ? discoverySearchHref(query, page, peopleOffset, Math.max(0, collectionOffset - snapshot.collections.limit)) : null}
          next={snapshot.collections.next_offset !== null ? discoverySearchHref(query, page, peopleOffset, snapshot.collections.next_offset) : null} navigate={navigate} />
      </section>
      <section aria-labelledby="search-people-title">
        <h2 id="search-people-title" className="font-serif text-2xl">{t("peopleResults", { count: snapshot.people.total })}</h2>
        {snapshot.people.items.length ? <div className="mt-4 grid gap-x-6 sm:grid-cols-2 lg:grid-cols-3">{snapshot.people.items.map(person => <Link prefetch={false} key={person.key} href={collectionHref({ kind: "person", key: person.key })} className="focus-ring min-w-0 border-b border-line py-4">
          <span className="block break-words text-sm font-medium">{person.label}</span>
          <span className="mt-1 block text-xs text-ink-muted">{t("personWorks", { count: person.owned_count })}</span>
        </Link>)}</div> : <p className="mt-3 text-sm text-ink-muted">{t("noPeople")}</p>}
        <SearchPages label={t("peoplePages")} previous={peopleOffset > 0 ? discoverySearchHref(query, page, Math.max(0, peopleOffset - snapshot.people.limit), collectionOffset) : null}
          next={snapshot.people.next_offset !== null ? discoverySearchHref(query, page, snapshot.people.next_offset, collectionOffset) : null} navigate={navigate} />
      </section>
      <section aria-labelledby="search-films-title">
        <h2 id="search-films-title" className="font-serif text-2xl">{t("filmCount", { count: snapshot.films.total })}</h2>
        {snapshot.films.items.length ? <div className="mt-5 grid grid-cols-2 gap-x-3 gap-y-6 sm:grid-cols-3 lg:grid-cols-4">{snapshot.films.items.map(film => <LibraryMovieCard key={film.id} movie={film} />)}</div>
          : snapshot.films.total > 0 ? <Spinner className="my-10" /> : <p className="mt-3 text-sm text-ink-muted">{searchT("empty", { query })}</p>}
        <SearchPages label={t("filmPages")} previous={page > 1 ? discoverySearchHref(query, page - 1, peopleOffset, collectionOffset) : null}
          next={snapshot.films.offset + snapshot.films.items.length < snapshot.films.total ? discoverySearchHref(query, page + 1, peopleOffset, collectionOffset) : null} navigate={navigate} />
      </section>
    </div>}
  </div>;
}

function SearchPages({ label, previous, next, navigate }: { label: string; previous: string | null; next: string | null; navigate: (href: string) => void }) {
  const t = useTranslations("Collections");
  if (!previous && !next) return null;
  return <nav aria-label={label} className="mt-6 flex justify-between gap-4">
    {previous ? <ButtonLink prefetch={false} href={previous} onNavigate={event => { event.preventDefault(); navigate(previous); }}>{t("previous")}</ButtonLink> : <span />}
    {next ? <ButtonLink prefetch={false} href={next} onNavigate={event => { event.preventDefault(); navigate(next); }}>{t("next")}</ButtonLink> : <span />}
  </nav>;
}
