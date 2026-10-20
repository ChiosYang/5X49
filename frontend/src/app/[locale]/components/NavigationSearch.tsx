"use client";

import { useEffect, useId, useRef, useState, useSyncExternalStore, type FormEvent, type ReactNode } from "react";
import { useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { Search, X } from "lucide-react";
import { Link, usePathname, useRouter } from "@/i18n/routing";
import { librarySearchHref, normalizeLibrarySearch } from "@/lib/library-search";
import NavigationMenu from "./NavigationMenu";

const subscribe = () => () => {};

export default function NavigationSearch({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const params = useSearchParams();
  // Remount drafts when navigation commits, including browser Back/Forward.
  return <NavigationBar key={`${pathname}?${params}`} query={pathname === "/library" ? normalizeLibrarySearch(params.get("q") ?? "") : ""}>{children}</NavigationBar>;
}

function NavigationBar({ query, children }: { query: string; children: ReactNode }) {
  const t = useTranslations("Navigation");
  const searchT = useTranslations("LibrarySearch");
  const router = useRouter();
  const id = useId();
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState(query);
  const input = useRef<HTMLInputElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const composing = useRef(false);
  const hydrated = useSyncExternalStore(subscribe, () => true, () => false);

  useEffect(() => {
    if (!open) return;
    // Run after the menu dialog restores its own focus and background.
    const frame = requestAnimationFrame(() => input.current?.focus({ preventScroll: true }));
    return () => cancelAnimationFrame(frame);
  }, [open]);

  function close() {
    setOpen(false);
    setDraft(query);
    composing.current = false;
    requestAnimationFrame(() => trigger.current?.focus({ preventScroll: true }));
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (composing.current) return;
    const href = librarySearchHref(draft);
    close();
    router.push(href);
  }

  return (
    <nav data-search-open={open} className="navigation-bar z-navigation fixed top-0 right-0 left-0 flex items-center justify-between p-8 pr-0 text-ink sm:pr-8">
      <div className="navigation-menu"><NavigationMenu /></div>
      <Link href="/" className="navigation-logo focus-ring z-navigation absolute left-1/2 -translate-x-1/2 font-serif text-2xl font-bold tracking-tighter drop-shadow-lg">5X49</Link>
      <div className="navigation-tools flex min-w-0 items-center gap-0 sm:gap-4">
        <div className="navigation-search" data-open={open}>
          <form id={id} role="search" aria-label={searchT("title")} onSubmit={submit}
            className="navigation-search-form flex h-11 min-w-0 items-center rounded-control border border-line-strong bg-canvas/90"
            inert={!open} aria-hidden={!open}
            onKeyDown={event => {
              const ime = composing.current || event.nativeEvent.isComposing || event.keyCode === 229;
              // Also suppress the search input's native Escape-to-clear while
              // the IME is handling a candidate, so its draft stays intact.
              if ((event.key === "Enter" || event.key === "Escape") && ime) event.preventDefault();
              if (event.key === "Escape" && !ime) { event.preventDefault(); close(); }
            }}>
            <button type="submit" aria-label={searchT("submit")} className="focus-ring inline-flex h-11 w-11 shrink-0 items-center justify-center"><Search className="h-5 w-5" aria-hidden="true" /></button>
            <label htmlFor={`${id}-query`} className="sr-only">{searchT("query")}</label>
            <input ref={input} id={`${id}-query`} name="q" type="search" maxLength={200} value={draft}
              onChange={event => setDraft(event.target.value)} onCompositionStart={() => { composing.current = true; }}
              onCompositionEnd={() => { composing.current = false; }}
              placeholder={searchT("placeholder")} autoComplete="off" enterKeyHint="search"
              className="focus-ring h-full min-w-0 flex-1 bg-transparent text-sm text-ink outline-none" />
            <button type="button" onClick={close} aria-label={searchT("close")} className="focus-ring inline-flex h-11 w-11 shrink-0 items-center justify-center"><X className="h-4 w-4" aria-hidden="true" /></button>
          </form>
          <button ref={trigger} type="button" disabled={!hydrated} aria-label={t("search")} aria-expanded={open} aria-controls={id}
            onClick={() => setOpen(true)} inert={open} aria-hidden={open}
            className="navigation-search-trigger focus-ring absolute top-0 right-0 inline-flex h-11 w-11 items-center justify-center">
            <Search className="h-5 w-5 drop-shadow-lg" aria-hidden="true" />
          </button>
        </div>
        <div className="navigation-status flex items-center gap-0 sm:gap-4">{children}</div>
      </div>
    </nav>
  );
}
