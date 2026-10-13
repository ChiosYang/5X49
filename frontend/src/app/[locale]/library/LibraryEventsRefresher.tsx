"use client";

import { shouldRefreshLibraryEvent } from "@/lib/library-interactions";
import { useLocale } from "next-intl";
import { useRouter } from "next/navigation";
import { useEffect, useRef } from "react";

export default function LibraryEventsRefresher() {
  const router = useRouter();
  const locale = useLocale();
  const refreshTimer = useRef<number | null>(null);

  useEffect(() => {
    const eventSource = new EventSource("/api/library/events");

    const scheduleRefresh = () => {
      if (refreshTimer.current) {
        window.clearTimeout(refreshTimer.current);
      }

      refreshTimer.current = window.setTimeout(() => {
        // A late prefetch from the previous locale can overwrite this cookie.
        // Match next-intl's session cookie and keep refresh on the rendered locale.
        document.cookie = `NEXT_LOCALE=${encodeURIComponent(locale)}; Path=/; SameSite=Lax`;
        router.refresh();
      }, 750);
    };

    const handleLibraryChange = (event: Event) => {
      try {
        const data = JSON.parse((event as MessageEvent<string>).data);
        if (shouldRefreshLibraryEvent(data.reason)) scheduleRefresh();
      } catch { /* Ignore malformed invalidations. */ }
    };

    // Reconcile changes between the server-rendered read and subscription,
    // including updates missed while the stream was reconnecting.
    eventSource.addEventListener("connected", scheduleRefresh);
    eventSource.addEventListener("library_changed", handleLibraryChange);

    return () => {
      if (refreshTimer.current) {
        window.clearTimeout(refreshTimer.current);
      }
      eventSource.removeEventListener("connected", scheduleRefresh);
      eventSource.removeEventListener("library_changed", handleLibraryChange);
      eventSource.close();
    };
  }, [router, locale]);

  return null;
}
