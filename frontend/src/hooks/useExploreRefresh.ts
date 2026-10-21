"use client";

import { useCallback, useEffect, useLayoutEffect, useRef, useTransition } from "react";
import useSWR from "swr";
import { usePathname, useRouter } from "@/i18n/routing";
import { EXPLORE_REFRESH_KEY, initialExploreRefresh } from "@/lib/explore-refresh";

export function useExploreRefresh<T>(baseline: T, pending: boolean, activeHref: string, committedHref = activeHref) {
  const router = useRouter();
  const pathname = usePathname();
  const { data = initialExploreRefresh, mutate } = useSWR<typeof initialExploreRefresh>(
    EXPLORE_REFRESH_KEY, null, { fallbackData: initialExploreRefresh },
  );
  const [refreshing, startRefresh] = useTransition();
  const active = useRef<string | null>(null);
  const attempt = useRef<{ revision: number; baseline: T; key: string; x: number; y: number } | null>(null);
  const read = useRef<{ href: string; revision: number; baseline: T } | null>(null);
  const linkPending = useRef(false);
  const beginRead = useCallback((href: string) => {
    read.current = { href, revision: data.revision, baseline };
  }, [baseline, data.revision]);
  useLayoutEffect(() => { linkPending.current = false; }, [committedHref, pathname]);
  useEffect(() => {
    // Native Next Links (including shared Film cards) keep their own scroll,
    // history and modifier-key behavior. Only observe the outgoing navigation.
    const observeLink = (event: MouseEvent) => {
      if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      const anchor = event.target instanceof Element ? event.target.closest("a[href]") : null;
      if (!(anchor instanceof HTMLAnchorElement) || anchor.hasAttribute("download") || (anchor.target && anchor.target !== "_self")) return;
      const target = new URL(anchor.href);
      if (target.origin === location.origin && `${target.pathname}${target.search}` !== `${location.pathname}${location.search}`) linkPending.current = true;
    };
    document.addEventListener("click", observeLink, true);
    const observeHistory = () => { read.current = null; };
    window.addEventListener("popstate", observeHistory);
    return () => {
      document.removeEventListener("click", observeLink, true);
      window.removeEventListener("popstate", observeHistory);
    };
  }, []);
  useLayoutEffect(() => {
    active.current = activeHref;
    return () => { active.current = null; attempt.current = null; };
  }, [activeHref]);
  useEffect(() => {
    if (baseline === null || !active.current || !/^\/explore(?:\/|$)/.test(pathname)
        || window.location.pathname.replace(/^\/(?:en|zh)(?=\/|$)/, "") !== pathname) return;
    // A late write waits for the user's newer query instead of canceling it.
    if (pending || refreshing || linkPending.current || active.current !== committedHref) return;
    const key = `${pathname}|${committedHref}`;
    const navigation = read.current;
    // A new dynamic read begun after the latest write is already fresh. Back has
    // no such ticket; its cached snapshot must still acknowledge its own refresh.
    if (navigation?.href === committedHref && navigation.baseline !== baseline) {
      read.current = null;
      if (navigation.revision === data.revision) {
        attempt.current = null;
        void mutate(current => ({ ...(current ?? initialExploreRefresh),
          acknowledged: { ...(current?.acknowledged ?? {}), [key]: navigation.revision },
        }), { revalidate: false });
        return;
      }
    }
    const previous = attempt.current;
    if (previous && previous.key === key) {
      if (baseline === previous.baseline) return;
      attempt.current = null;
      window.scrollTo(previous.x, previous.y);
      void mutate(current => ({
        ...(current ?? initialExploreRefresh),
        acknowledged: { ...(current?.acknowledged ?? {}),
          [key]: Math.max(current?.acknowledged[key] ?? 0, previous.revision) },
      }), { revalidate: false });
      return;
    }
    if (data.revision <= (data.acknowledged[key] ?? 0)) return;
    attempt.current = { revision: data.revision, baseline, key, x: window.scrollX, y: window.scrollY };
    startRefresh(() => router.refresh());
  }, [activeHref, baseline, committedHref, data, mutate, pathname, pending, refreshing, router]);
  return beginRead;
}

const positions = new Map<string, { x: number; y: number }>();
export function useExploreBrowsePosition(href: string) {
  useLayoutEffect(() => {
    const position = positions.get(href);
    const frame = position ? requestAnimationFrame(() => window.scrollTo(position.x, position.y)) : null;
    return () => {
      if (frame !== null) cancelAnimationFrame(frame);
      positions.set(href, { x: window.scrollX, y: window.scrollY });
    };
  }, [href]);
}
