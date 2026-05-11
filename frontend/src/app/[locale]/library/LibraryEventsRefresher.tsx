"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef } from "react";

export default function LibraryEventsRefresher() {
  const router = useRouter();
  const refreshTimer = useRef<number | null>(null);

  useEffect(() => {
    const eventSource = new EventSource("/api/library/events");

    const scheduleRefresh = () => {
      if (refreshTimer.current) {
        window.clearTimeout(refreshTimer.current);
      }

      refreshTimer.current = window.setTimeout(() => {
        router.refresh();
      }, 750);
    };

    eventSource.addEventListener("library_changed", scheduleRefresh);

    return () => {
      if (refreshTimer.current) {
        window.clearTimeout(refreshTimer.current);
      }
      eventSource.removeEventListener("library_changed", scheduleRefresh);
      eventSource.close();
    };
  }, [router]);

  return null;
}
