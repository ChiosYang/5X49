"use client";

import { createContext, useCallback, useContext, useEffect, useLayoutEffect, useMemo, useRef, useState, useTransition, type ReactNode } from "react";
import { useSearchParams } from "next/navigation";
import { usePathname, useRouter } from "@/i18n/routing";
import { API } from "@/lib/api";
import { discoveryHref, discoveryReason, hasPrivateDiscoveryInput, normalizeDiscoverySearch, resolutionHref, type DiscoveryResolution, type DiscoverySubmission } from "@/lib/discovery-search";

interface Session {
  draft: string | null; error: string; pending: boolean;
  change: (value: string) => void;
  cancel: (reset?: boolean, cancelNavigation?: boolean) => void;
  clear: () => void;
  submit: (value: string, locale: string, options?: DiscoverySubmission) => Promise<void>;
}
const Context = createContext<Session | null>(null);
const NavigationContext = createContext<(Pick<Session, "pending" | "cancel"> & { browseHref: string }) | null>(null);
export function useDiscoveryNavigation() {
  const navigation = useContext(NavigationContext);
  if (!navigation) throw new Error("Explore search navigation is missing");
  return navigation;
}
export function useDiscoverySearchSession() {
  const session = useContext(Context);
  if (!session) throw new Error("Explore search session is missing");
  return session;
}

// The owner survives an older RSC result committing while a newer submission is
// still interpreting. Leaving Explore, a Link or Back cancels that ownership.
export default function DiscoverySearchSession({ children }: { children: ReactNode }) {
  const router = useRouter(), pathname = usePathname(), params = useSearchParams();
  const href = `${pathname}${params.size ? `?${params}` : ""}`;
  const current = useRef(href), navigation = useRef<string | null>(null);
  const [browseHref, setBrowseHref] = useState("/explore");
  if (pathname === "/explore" && browseHref !== href) setBrowseHref(href);
  const ticket = useRef(0), controller = useRef<AbortController | null>(null);
  const requestId = useRef<string | null>(null);
  const [draft, setDraft] = useState<string | null>(null), [error, setError] = useState("");
  const [previousHref, setPreviousHref] = useState(href), [submittedHref, setSubmittedHref] = useState<string | null>(null);
  const [requesting, setRequesting] = useState(false), [navigating, startNavigation] = useTransition();
  if (previousHref !== href) {
    setPreviousHref(href);
    // Once our submitted result commits, its URL owns the input. Keeping that
    // completed draft would mask an older query when Next restores cached Back.
    // A newer edit cancels submittedHref and remains visible during stale RSC.
    if (submittedHref === href) { setDraft(null); setSubmittedHref(null); }
  }
  useLayoutEffect(() => {
    current.current = href;
    if (navigation.current === href) navigation.current = null;
  }, [href, pathname]);
  const abort = useCallback(() => {
    ticket.current++;
    const owner = requestId.current;
    requestId.current = null;
    if (owner) void fetch(`${API.baseUrl}/explore/search/cancel`, { method: "POST", keepalive: true,
      headers: { "Content-Type": "application/json" }, body: JSON.stringify({ request_id: owner }) }).catch(() => {});
    controller.current?.abort(); controller.current = null;
  }, []);
  const cancel = useCallback((reset = false, cancelNavigation = false) => {
    abort(); setRequesting(false); setError(""); setSubmittedHref(null);
    if (reset) setDraft(null);
    const queued = navigation.current; navigation.current = null;
    if (cancelNavigation && queued && queued !== current.current) {
      startNavigation(() => router.replace(current.current, { scroll: false }));
    }
  }, [abort, router]);
  const navigate = useCallback((target: string) => {
    navigation.current = target;
    if (target === current.current) { setDraft(null); setSubmittedHref(null); }
    else setSubmittedHref(target);
    startNavigation(() => router.push(target, { scroll: false }));
  }, [router]);
  useEffect(() => {
    const leave = (event: MouseEvent) => {
      if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      const link = event.target instanceof Element ? event.target.closest("a[href]") : null;
      if (link instanceof HTMLAnchorElement && (!link.target || link.target === "_self") && !link.hasAttribute("download")) cancel(true);
    };
    const history = () => cancel(true);
    document.addEventListener("click", leave, true); window.addEventListener("popstate", history);
    return () => { abort(); document.removeEventListener("click", leave, true); window.removeEventListener("popstate", history); };
  }, [abort, cancel]);
  async function submit(value: string, locale: string, options: DiscoverySubmission = {}) {
    cancel(false, true);
    const question = normalizeDiscoverySearch(value); setDraft(question);
    if (!question) { setDraft(null); navigate(browseHref); return; }
    if (hasPrivateDiscoveryInput(question)) { setError("ask_private_input"); return; }
    const requestTicket = ++ticket.current;
    const owner = `rq_${crypto.randomUUID().replaceAll("-", "")}`; requestId.current = owner;
    const request = new AbortController(); controller.current = request; setRequesting(true);
    try {
      const response = await fetch(`${API.baseUrl}/explore/search/interpret`, { method: "POST", signal: request.signal,
        headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question, locale, allow_ai: true, ...options, request_id: owner }) });
      const result = await response.json().catch(() => null);
      if (request.signal.aborted || ticket.current !== requestTicket) return;
      if (!response.ok) {
        const reason = discoveryReason(result?.detail?.code);
        if (reason === "ask_private_input") { setError(reason); return; }
        navigate(discoveryHref(question, { status: "unavailable", reason })); return;
      }
      navigate(resolutionHref(question, result as DiscoveryResolution));
    } catch {
      if (!request.signal.aborted && ticket.current === requestTicket) setError("unavailable");
    } finally {
      if (ticket.current === requestTicket) { setRequesting(false); controller.current = null; requestId.current = null; }
    }
  }
  const pending = requesting || navigating;
  const navigationValue = useMemo(() => ({ pending, cancel, browseHref }), [pending, cancel, browseHref]);
  return <NavigationContext value={navigationValue}><Context value={{ draft, error, pending, cancel, submit,
    change: value => { cancel(false, true); setDraft(value); },
    clear: () => { cancel(true, true); navigate(browseHref); },
  }}>{children}</Context></NavigationContext>;
}
