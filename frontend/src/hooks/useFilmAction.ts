"use client";

import { useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { useSWRConfig } from "swr";
import { useRouter } from "@/i18n/routing";
import { invalidateViewingCaches } from "@/hooks/useFilm";
import { API } from "@/lib/api";
import { executeFilmAction } from "@/lib/viewing-write";

export function useFilmAction(filmId: string) {
  const t = useTranslations("FilmDetail");
  const router = useRouter();
  const { cache } = useSWRConfig();
  const guard = useRef(false);
  const [pending, setPending] = useState(false);
  const [feedback, setFeedback] = useState<{ kind: "saved" | "refreshFailed" | "failed"; message: string } | null>(null);

  const refreshViews = async () => {
    const keys = new Set(cache.keys());
    keys.add(API.libraryFilm(filmId));
    await invalidateViewingCaches(filmId, keys);
    router.refresh();
  };

  const run = async <T,>(write: () => Promise<T>, failure: string,
    committed: (value: T) => void = () => {}, success: string = t("saved")) => {
    if (guard.current) return;
    guard.current = true;
    setPending(true);
    setFeedback(null);
    try {
      const result = await executeFilmAction(write, committed, refreshViews);
      if (result.status === "failed") {
        setFeedback({ kind: "failed", message: `${failure} ${t(`actionReason_${result.reason}`)}` });
        return;
      }
      setFeedback({ kind: result.status, message: result.status === "refreshFailed" ? t("savedRefreshFailed") : success });
      return result.value;
    } finally { guard.current = false; setPending(false); }
  };

  const retryRefresh = async () => {
    if (guard.current) return false;
    guard.current = true;
    setPending(true);
    try { await refreshViews(); setFeedback({ kind: "saved", message: t("refreshed") }); return true; }
    catch { setFeedback({ kind: "refreshFailed", message: t("savedRefreshFailed") }); return false; }
    finally { guard.current = false; setPending(false); }
  };
  return { run, pending, feedback, retryRefresh, clear: () => setFeedback(null) };
}
