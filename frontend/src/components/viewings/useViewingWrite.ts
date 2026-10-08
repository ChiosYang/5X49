"use client";

import { useEffect, useRef, useState } from "react";
import { useSWRConfig } from "swr";
import { useTranslations } from "next-intl";
import { invalidateViewingCaches, useCreateFilmViewing, useUpdateViewing, useDeleteViewing } from "@/hooks/useFilm";
import { commitViewingWrite } from "@/lib/viewing-write";
import type { ViewingView } from "@/types/movie";

export function useViewingWrite(filmId: string, viewing: ViewingView | null | undefined, onSaved?: () => void | Promise<void>) {
  const t = useTranslations("Diary");
  const { cache } = useSWRConfig();
  const [receipt, setReceipt] = useState<ViewingView | null>(null);
  const [completed, setCompleted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<{ tone: "success" | "error"; text: string } | null>(null);
  const [refreshFailed, setRefreshFailed] = useState(false);
  const locked = useRef(false);
  const committedRef = useRef(false);
  const receiptRef = useRef<ViewingView | null>(null);
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const create = useCreateFilmViewing(filmId);
  const update = useUpdateViewing(viewing?.id);
  const remove = useDeleteViewing(viewing?.id);
  const undo = useDeleteViewing(receipt?.id);
  const refresh = async () => {
    await invalidateViewingCaches(filmId, cache.keys());
    await onSaved?.();
  };
  const run = async <T,>(write: () => Promise<T>, message: string, committed: (value: T) => void) => {
    if (locked.current) return;
    locked.current = true;
    setBusy(true);
    setFeedback(null);
    setRefreshFailed(false);
    try {
      const result = await commitViewingWrite(write, value => {
        if (!mounted.current) return;
        committed(value);
        committedRef.current = true;
        setCompleted(true);
        setFeedback({ tone: "success", text: message });
      }, refresh);
      if (mounted.current) setRefreshFailed(result.refreshFailed);
    } catch (error) {
      if (mounted.current) setFeedback({ tone: "error", text: error instanceof Error ? error.message : t("saveFailed") });
    } finally {
      locked.current = false;
      if (mounted.current) setBusy(false);
    }
  };
  return {
    receipt, completed, busy, feedback, refreshFailed,
    save: (watched_at: string | null) => {
      if (committedRef.current) return;
      return viewing
        ? run(() => update.trigger({ watched_at }), t("updated"), () => {})
        : run(() => create.trigger({ watched_at }), t("created"), value => { receiptRef.current = value; setReceipt(value); });
    },
    remove: () => { if (!committedRef.current) return run(() => remove.trigger(), t("deleted"), () => {}); },
    undo: () => { if (receiptRef.current) return run(() => undo.trigger(), t("undone"), () => { receiptRef.current = null; setReceipt(null); }); },
    reset: () => { if (!locked.current) { committedRef.current = false; receiptRef.current = null; setCompleted(false); setReceipt(null); setFeedback(null); setRefreshFailed(false); } },
    retryRefresh: async () => {
      if (locked.current) return;
      locked.current = true;
      setBusy(true);
      try { await refresh(); if (mounted.current) setRefreshFailed(false); }
      catch { if (mounted.current) setRefreshFailed(true); }
      finally { locked.current = false; if (mounted.current) setBusy(false); }
    },
  };
}
