"use client";

import { useEffect, useId, useRef, useState, useSyncExternalStore, type FormEvent } from "react";
import { useLocale, useTranslations } from "next-intl";
import { X } from "lucide-react";
import { Link } from "@/i18n/routing";
import { Button, IconButton } from "@/components/ui/Button";
import { TextInput } from "@/components/ui/FormControls";
import { API } from "@/lib/api";
import { collectionHref } from "@/lib/collections";
import { discoveryHref, hasPrivateDiscoveryInput, normalizeDiscoverySearch } from "@/lib/discovery-search";
import { rememberFilmReturn } from "@/lib/navigation-context";
import type { CollectionCatalog, ExploreFacetPage, LibraryFilmPage } from "@/types/movie";
import { useDiscoverySearchSession } from "./DiscoverySearchSession";

const subscribe = () => () => {};
type Suggestion = { href: string; label: string; kind: "film" | "person" | "collection"; filmId?: string };

export default function UnifiedSearchInput({ query = "" }: { query?: string }) {
  const t = useTranslations("Discovery");
  const locale = useLocale();
  const id = useId();
  const hydrated = useSyncExternalStore(subscribe, () => true, () => false);
  const session = useDiscoverySearchSession();
  const draft = session.draft ?? query, busy = session.pending, error = session.error;
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [suggestionsOpen, setSuggestionsOpen] = useState(false);
  const [suggestionsFailed, setSuggestionsFailed] = useState(false);
  const [imeActive, setImeActive] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const composing = useRef(false);

  useEffect(() => {
    const q = normalizeDiscoverySearch(draft);
    if (!suggestionsOpen || imeActive || q.length < 2 || q.length > 100 || q === query || hasPrivateDiscoveryInput(q)) return;
    const abort = new AbortController();
    const timer = setTimeout(async () => {
      try {
        const params = new URLSearchParams({ q, limit: "3" });
        const responses = await Promise.all([
          fetch(API.libraryFilmPage(params), { signal: abort.signal }),
          fetch(API.exploreFacets("person", { q, limit: 3 }), { signal: abort.signal }),
          fetch(`${API.baseUrl}/explore/catalog?${params}`, { signal: abort.signal }),
        ]);
        if (responses.some(response => !response.ok)) throw new Error("suggestions");
        const [films, people, collections] = await Promise.all(responses.map(response => response.json())) as [LibraryFilmPage, ExploreFacetPage, CollectionCatalog];
        if (abort.signal.aborted) return;
        setSuggestions([
          ...films.items.map(film => ({ href: `/library/${film.id}`, label: film.title, kind: "film" as const, filmId: film.id })),
          ...people.items.map(person => ({ href: collectionHref({ kind: "person", key: person.key }), label: person.label, kind: "person" as const })),
          ...collections.items.map(item => ({ href: collectionHref(item), label: item.kind === "country" ? new Intl.DisplayNames([locale], { type: "region" }).of(item.key) ?? item.label : item.label, kind: "collection" as const })),
        ]);
        setSuggestionsFailed(false);
      } catch {
        if (!abort.signal.aborted) { setSuggestions([]); setSuggestionsFailed(true); }
      }
    }, 220);
    return () => { clearTimeout(timer); abort.abort(); };
  }, [draft, imeActive, locale, query, suggestionsOpen]);

  function submit(event: FormEvent) {
    event.preventDefault();
    if (composing.current || !hydrated) return;
    setSuggestionsOpen(false); setSuggestions([]);
    void session.submit(draft, locale);
  }
  return <div className="mt-6 w-full max-w-2xl" onBlur={event => { if (!event.currentTarget.contains(event.relatedTarget)) setSuggestionsOpen(false); }}>
    <form role="search" aria-label={t("label")} onSubmit={submit} aria-busy={busy}>
      <label htmlFor={id} className="sr-only">{t("label")}</label>
      <div className="flex min-w-0 gap-2">
        <div className="relative min-w-0 flex-1">
          <TextInput ref={input} id={id} name="q" type="search" value={draft} maxLength={600} disabled={!hydrated}
            placeholder={t("placeholder")} autoComplete="off" enterKeyHint="search" className="min-w-0 pr-10 [&::-webkit-search-cancel-button]:appearance-none"
            aria-describedby={`${id}-hint${error ? ` ${id}-error` : ""}`} aria-controls={suggestionsOpen ? `${id}-suggestions` : undefined}
            onFocus={() => setSuggestionsOpen(true)}
            onChange={event => { session.change(event.target.value); setSuggestions([]); setSuggestionsOpen(true); setSuggestionsFailed(false); }}
            onCompositionStart={() => { composing.current = true; setImeActive(true); }} onCompositionEnd={() => { composing.current = false; setImeActive(false); session.change(input.current?.value ?? ""); }}
            onKeyDown={event => {
              const ime = composing.current || event.nativeEvent.isComposing || event.keyCode === 229;
              if ((event.key === "Enter" || event.key === "Escape") && ime) event.preventDefault();
              if (event.key === "Escape" && !ime) { event.preventDefault(); session.cancel(false, true); setSuggestionsOpen(false); }
            }} />
          {draft ? <IconButton variant="ghost" onClick={() => { setSuggestions([]); setSuggestionsOpen(false); if (query) session.clear(); else { session.change(""); input.current?.focus(); } }} aria-label={t("clear")} icon={<X className="h-4 w-4" />} className="absolute top-0 right-0 h-11 w-10 min-w-0 p-0" /> : null}
        </div>
        <Button type="submit" variant="primary" disabled={!hydrated}>{t(busy ? "searching" : "submit")}</Button>
      </div>
      <p id={`${id}-hint`} className="mt-3 text-xs leading-5 text-ink-subtle">{t("privacy")}</p>
      {busy ? <Button variant="ghost" size="sm" className="mt-2" onClick={() => session.cancel(false, true)}>{t("cancel")}</Button> : null}
      {error ? <div id={`${id}-error`} role="alert" className="mt-3 text-sm text-warning"><p>{t(`reasons.${error}`)}</p>
        {error !== "ask_private_input" && draft.trim().length <= 200 ? <Link prefetch={false} href={`${discoveryHref(draft)}&mode=keyword`} className="focus-ring mt-2 inline-block underline">{t("keywordFallback")}</Link> : null}</div> : null}
    </form>
    {suggestionsOpen && (suggestions.length > 0 || suggestionsFailed) ? <div id={`${id}-suggestions`} className="mt-3 border-y border-line py-3">
      <p className="type-label mb-2 text-ink-muted">{t("suggestions")}</p>
      {suggestionsFailed ? <p className="text-xs text-ink-muted">{t("suggestionsFailed")}</p> : <ul className="grid gap-1">
        {suggestions.map((item, index) => <li key={`${item.href}:${index}`}><Link prefetch={false} href={item.href} onClick={() => item.filmId && rememberFilmReturn(item.filmId)} className="focus-ring flex min-h-11 min-w-0 items-center justify-between gap-3 py-2 text-sm hover:text-ink-muted">
          <span className="min-w-0 break-words">{item.label}</span><span className="shrink-0 text-xs text-ink-subtle">{t(`kinds.${item.kind}`)}</span>
        </Link></li>)}
      </ul>}
    </div> : null}
  </div>;
}
