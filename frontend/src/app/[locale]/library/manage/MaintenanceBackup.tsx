"use client";

import { Download, RefreshCw } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useCallback, useEffect, useRef, useState } from "react";
import useSWR from "swr";
import { Button } from "@/components/ui/Button";
import { API } from "@/lib/api";
import { fetcher } from "@/lib/fetcher";

interface Backup {
  id: string;
  status: "generating" | "succeeded" | "failed" | "interrupted";
  created_at: string;
  finished_at: string | null;
  expires_at: string | null;
  size_bytes: number | null;
  filename: string | null;
  download_triggered_at: string | null;
  available: boolean;
  error_code: string | null;
  artifact_state: string | null;
}
interface Status { last_attempt: Backup | null; last_success: Backup | null }
const PENDING = "5x49:pending-backup:v1";

export default function MaintenanceBackup() {
  const t = useTranslations("MaintenanceBackup");
  const locale = useLocale();
  const status = useSWR<Status>(API.backups(), fetcher, { refreshInterval: 3000 });
  const [pending, setPending] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const lock = useRef(false);
  const processed = useRef<string | null>(null);
  const noticeOwner = useRef<string | null>(null);
  const controller = useRef<AbortController | null>(null);
  const mounted = useRef(true);
  const forget = useCallback((expected?: string) => {
    try { if (!expected || sessionStorage.getItem(PENDING) === expected) sessionStorage.removeItem(PENDING); } catch { /* The server still retains the receipt. */ }
    if (mounted.current) setPending(current => !expected || current === expected ? null : current);
  }, []);
  useEffect(() => {
    mounted.current = true;
    const hydration = requestAnimationFrame(() => {
      try {
        const saved = sessionStorage.getItem(PENDING);
        if (saved && /^[0-9a-f]{32}$/.test(saved)) { noticeOwner.current = saved; setPending(saved); }
      } catch { /* Storage can be disabled. */ }
    });
    return () => { cancelAnimationFrame(hydration); mounted.current = false; controller.current?.abort(); };
  }, []);

  const download = useCallback(async (backup: Backup) => {
    if (lock.current) return;
    lock.current = true;
    noticeOwner.current = backup.id;
    setBusy(true);
    setNotice(null);
    const abort = new AbortController();
    controller.current = abort;
    try {
      const response = await fetch(`${API.backup(backup.id)}/download`, { cache: "no-store", signal: abort.signal });
      if (!response.ok) throw new Error("download");
      const blob = await response.blob();
      if (abort.signal.aborted) return;
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = backup.filename || "5x49-backup.zip";
      document.body.appendChild(anchor);
      try { anchor.click(); } finally { anchor.remove(); setTimeout(() => URL.revokeObjectURL(url), 30000); }
      // A browser trigger is the strongest fact we can observe. Disk saving is unknown.
      setNotice(t("triggered"));
      forget(backup.id);
      const receiptTimeout = setTimeout(() => abort.abort(), 15000);
      try {
        const acknowledgement = await fetch(`${API.backup(backup.id)}/download-triggered`, { method: "POST", signal: abort.signal });
        if (!acknowledgement.ok) throw new Error("receipt");
        void status.mutate().catch(() => {});
      } catch { if (mounted.current) setNotice(t("triggerUnrecorded")); }
      finally { clearTimeout(receiptTimeout); }
    } catch {
      if (!abort.signal.aborted) { setNotice(t("downloadFailed")); forget(backup.id); }
    } finally {
      lock.current = false;
      if (mounted.current) setBusy(false);
    }
  }, [forget, status, t]);

  const attempt = useSWR<Backup>(pending ? API.backup(pending) : null, fetcher, { refreshInterval: 1500, onSuccess(record) {
    if (!record || record.status === "generating" || processed.current === record.id || lock.current) return;
    processed.current = record.id;
    if (record.status === "succeeded" && record.available) void download(record);
    else {
      // A late receipt must not overwrite feedback for a newer user action.
      if (noticeOwner.current === record.id) setNotice(record.status === "succeeded" ? t("unavailable") : t(record.error_code === "backup_tasks_active" ? "tasksActive" : record.error_code === "backup_sensitive_content" ? "sensitive" : record.status === "interrupted" ? "interrupted" : "failed"));
      forget(record.id);
      void status.mutate().catch(() => {});
    }
  } });

  async function create() {
    if (lock.current) return;
    lock.current = true;
    setBusy(true);
    setNotice(null);
    const identifier = pending || Array.from(crypto.getRandomValues(new Uint8Array(16)), value => value.toString(16).padStart(2, "0")).join("");
    noticeOwner.current = identifier;
    try { sessionStorage.setItem(PENDING, identifier); } catch { /* Retry remains available in this tab. */ }
    setPending(identifier);
    const abort = new AbortController();
    controller.current = abort;
    const timeout = setTimeout(() => abort.abort(), 15000);
    try {
      const response = await fetch(API.backups(), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ request_id: identifier }), signal: abort.signal });
      if (response.status === 409) { forget(); setNotice(t("otherGeneration")); }
      else if (!response.ok) throw new Error("generation");
      // Revalidation must not hold the action lock: an unrelated GET can stall.
      void status.mutate().catch(() => {});
      void attempt.mutate().catch(() => {});
    } catch { if (mounted.current) setNotice(t("uncertain")); }
    finally { clearTimeout(timeout); lock.current = false; if (mounted.current) setBusy(false); }
  }

  const last = status.data?.last_attempt;
  const success = status.data?.last_success;
  const generating = last?.status === "generating";
  const date = (value: string | null) => value ? new Date(value).toLocaleString(locale) : "—";
  return (
    <section aria-labelledby="backup-heading" className="page-x pt-6">
      <div className="border border-white/10 px-5 py-5 sm:px-6">
        <div className="flex flex-col justify-between gap-4 xl:flex-row xl:items-start">
          <div className="min-w-0 max-w-3xl">
            <h2 id="backup-heading" className="text-lg font-semibold tracking-tight">{t("title")}</h2>
            <p className="mt-2 text-sm leading-6 text-neutral-400">{t("contents")}</p>
            <p className="mt-1 text-xs leading-5 text-neutral-500">{t("exclusions")}</p>
          </div>
          <div className="flex shrink-0 flex-wrap gap-2">
            <Button onClick={() => void create()} busy={busy} disabled={!status.data || Boolean(status.error) || Boolean(generating)} icon={<Download className="h-4 w-4" />}>
              {generating ? t("generating") : pending ? t("retry") : t("create")}
            </Button>
            {success?.available ? <Button variant="ghost" disabled={busy} onClick={() => void download(success)}>{t("redownload")}</Button> : null}
          </div>
        </div>
        <div aria-live="polite" className="mt-4 border-t border-white/10 pt-4 text-xs leading-6 text-neutral-400">
          {status.error ? <div className="flex flex-wrap items-center gap-3 text-amber-300">{t("loadFailed")}<Button size="sm" variant="ghost" onClick={() => void status.mutate().catch(() => {})} icon={<RefreshCw className="h-3 w-3" />}>{t("refresh")}</Button></div> : !status.data ? <p>{t("loading")}</p> : <>
            <p>{success ? t("lastSuccess", { date: date(success.finished_at), size: ((success.size_bytes || 0) / 1024 / 1024).toFixed(2) }) : t("never")}</p>
            {success ? <p>{success.available ? t("expires", { date: date(success.expires_at) }) : t("unavailable")}</p> : null}
            {last && last.status !== "succeeded" ? <p className={generating ? "text-cyan-300" : "text-amber-300"}>{t("lastAttempt", { date: date(last.created_at) })} {generating ? t("generating") : t(last.error_code === "backup_tasks_active" ? "tasksActive" : last.error_code === "backup_sensitive_content" ? "sensitive" : last.status === "interrupted" ? "interrupted" : "failed")}</p> : null}
            {success ? <p>{success.download_triggered_at ? t("lastTrigger", { date: date(success.download_triggered_at) }) : t("notTriggered")}</p> : null}
          </>}
          <p className="mt-1">{t("diskUnknown")}</p>
          {notice ? <p role="status" className="mt-2 text-amber-200">{notice}</p> : null}
        </div>
        <details className="mt-3 text-xs leading-6 text-neutral-500">
          <summary className="focus-ring w-fit cursor-pointer text-neutral-300">{t("restoreTitle")}</summary>
          <p className="mt-2 max-w-3xl">{t("restore")}</p>
        </details>
      </div>
    </section>
  );
}
