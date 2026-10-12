"use client";

import { useEffect, useRef, useState } from "react";
import { useSWRConfig } from "swr";
import { useTranslations } from "next-intl";
import { invalidateViewingCaches, useCreateFilmViewing, useUpdateViewing, useDeleteViewing } from "@/hooks/useFilm";
import { clearPendingViewingRequest, commitViewingWrite } from "@/lib/viewing-write";
import { ApiError } from "@/lib/fetcher";
import type { ViewingView, ViewingWriteRequest } from "@/types/movie";

export function useViewingWrite(filmId: string, viewing: ViewingView | null | undefined, onSaved?: () => void | Promise<void>) {
  const t = useTranslations("Diary");
  const { cache } = useSWRConfig();
  const [receipt, setReceipt] = useState<ViewingView | null>(null);
  const [completed, setCompleted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<{ tone: "success" | "error"; text: string } | null>(null);
  const [refreshFailed, setRefreshFailed] = useState(false);
  const [retryPending, setRetryPending] = useState(false);
  const [conflict, setConflict] = useState(false);
  const pending = useRef<ViewingWriteRequest | null>(null);
  const storageKey = `5x49:viewing-write:${filmId}:${viewing?.id || "new"}`;
  const remember = (request: ViewingWriteRequest) => {
    try { sessionStorage.setItem(storageKey, JSON.stringify(request)); }
    catch { /* Session storage may be disabled; the mounted form still retains its request. */ }
  };
  const forget = (requestKey?: string) => {
    try { clearPendingViewingRequest(sessionStorage, storageKey, requestKey); }
    catch { /* A late response must never clear a newer pending operation. */ }
  };
  const locked = useRef(false);
  const committedRef = useRef(false);
  const receiptRef = useRef<ViewingView | null>(null);
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => {
    try {
      const stored = sessionStorage.getItem(storageKey);
      if (stored) {
        const request = JSON.parse(stored) as ViewingWriteRequest;
        if (typeof request.idempotency_key === "string") {
          pending.current = request;
          queueMicrotask(() => { if (mounted.current) {
            setRetryPending(true);
            setFeedback({ tone: "error", text: t("retrySameRequest") });
          } });
        }
      }
    } catch { /* Ignore unavailable or corrupt session storage. */ }
  }, [storageKey, t]);
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
    const requestKey = pending.current?.idempotency_key;
    locked.current = true;
    setBusy(true);
    setFeedback(null);
    setRefreshFailed(false);
    try {
      const result = await commitViewingWrite(write, value => {
        forget(requestKey);
        pending.current = null;
        if (!mounted.current) return;
        committed(value);
        setRetryPending(false);
        committedRef.current = true;
        setCompleted(true);
        setFeedback({ tone: "success", text: message });
      }, refresh);
      if (mounted.current) setRefreshFailed(result.refreshFailed);
    } catch (error) {
      const uncertain = !(error instanceof ApiError) || error.status >= 500;
      if (!uncertain) { forget(requestKey); pending.current = null; }
      if (mounted.current) {
        const isConflict = error instanceof ApiError && (error.status === 409 || error.status === 404);
        setConflict(isConflict);
        setRetryPending(uncertain && pending.current !== null);
        setFeedback({ tone: "error", text: isConflict ? t("conflict") : uncertain ? t("retrySameRequest") : error instanceof Error ? error.message : t("saveFailed") });
      }
    } finally {
      locked.current = false;
      if (mounted.current) setBusy(false);
    }
  };
  return {
    receipt, completed, busy, feedback, refreshFailed, retryPending, conflict,
    save: (changes: ViewingWriteRequest) => {
      if (committedRef.current || locked.current || conflict) return;
      pending.current ??= { ...changes, revision: viewing?.revision,
        idempotency_key: Array.from(crypto.getRandomValues(new Uint8Array(16)), byte => byte.toString(16).padStart(2, "0")).join("") };
      const request = pending.current;
      remember(request);
      return viewing
        ? run(() => update.trigger(request), t("updated"), () => {})
        : run(() => create.trigger(request), t("created"), value => { receiptRef.current = value; setReceipt(value); });
    },
    remove: () => { if (!committedRef.current && viewing && !pending.current && !conflict) return run(() => remove.trigger({ revision: viewing.revision }), t("deleted"), () => {}); },
    undo: () => { if (receiptRef.current && !conflict) return run(() => undo.trigger({ revision: receiptRef.current!.revision }), t("undone"), () => { receiptRef.current = null; setReceipt(null); }); },
    reset: () => { if (!locked.current) { committedRef.current = false; receiptRef.current = null; pending.current = null; setConflict(false); setRetryPending(false); setCompleted(false); setReceipt(null); setFeedback(null); setRefreshFailed(false); } },
    retryRefresh: async () => {
      if (locked.current) return false;
      locked.current = true;
      setBusy(true);
      try { await refresh(); if (mounted.current) setRefreshFailed(false); return true; }
      catch { if (mounted.current) setRefreshFailed(true); return false; }
      finally { locked.current = false; if (mounted.current) setBusy(false); }
    },
  };
}
