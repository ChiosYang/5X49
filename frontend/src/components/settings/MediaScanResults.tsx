"use client";

import { useRef, useState } from "react";
import useSWR from "swr";
import { useLocale, useTranslations } from "next-intl";
import { API } from "@/lib/api";
import { fetcher } from "@/lib/fetcher";
import { Button } from "@/components/ui/Button";
import type { MediaRoots } from "./MediaRootsControl";

interface ScanStatus {
  sync: { state: string; last_finished_at: string | null; last_result: {
    scanned: number; added: number; missing: number; complete: boolean;
    roots: { id: string; state: string; scanned: number; errors: number; skipped_links: number }[];
  } | null };
}

export default function MediaScanResults({ disabled = false }: { disabled?: boolean }) {
  const t = useTranslations("MediaRoots");
  const locale = useLocale();
  const roots = useSWR<MediaRoots>(API.settingsMediaDirs(), fetcher, { refreshInterval: 5000 });
  const scan = useSWR<ScanStatus>(API.librarySyncStatus(), fetcher, { refreshInterval: 2000 });
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const lock = useRef(false);
  async function start() {
    if (lock.current) return;
    lock.current = true; setBusy(true); setNotice(null);
    try {
      const response = await fetch(`${API.baseUrl}/library/scan`, { method: "POST", signal: AbortSignal.timeout(15000) });
      if (!response.ok) throw new Error();
      setNotice("queued"); void scan.mutate();
    } catch { setNotice("scanFailed"); }
    finally { lock.current = false; setBusy(false); }
  }
  const status = scan.data?.sync;
  const result = status?.last_result;
  return <div className="min-w-0 border border-line p-4 sm:p-5" aria-label={t("scanTitle")}>
    <div className="flex flex-wrap items-center justify-between gap-3">
      <h3 className="text-base font-semibold">{t("scanTitle")}</h3>
      <Button size="sm" busy={busy} disabled={disabled || busy || status?.state === "running" || !roots.data?.media_dirs.length} onClick={() => void start()}>{t("scanAll")}</Button>
    </div>
    <p className="mt-2 text-xs leading-6 text-ink-muted">{t("scanHelp")}</p>
    <div aria-live="polite" className="mt-3 space-y-2 text-xs leading-6 text-ink-subtle">
      {scan.error ? <p role="alert">{t("scanStatusFailed")}</p> : status?.state === "running" ? <p>{t("running")}</p> : result ? <>
        <p>{t(result.complete ? "complete" : "partial")} · {t("counts", { scanned: result.scanned, added: result.added, missing: result.missing })}</p>
        {status?.last_finished_at ? <p>{new Date(status.last_finished_at).toLocaleString(locale)}</p> : null}
        {(result.roots ?? []).map(row => <div key={row.id} className="min-w-0 border-t border-line pt-2">
          <p className="break-all">{roots.data?.roots.find(root => root.id === row.id)?.path ?? t("removedRoot")}</p>
          <p>{t(row.state)} · {t("rootCounts", { scanned: row.scanned, errors: row.errors, links: row.skipped_links })}</p>
        </div>)}
        {(roots.data?.roots ?? []).filter(root => !result.roots?.some(row => row.id === root.id)).map(root => <div key={root.id} className="min-w-0 border-t border-line pt-2">
          <p className="break-all">{root.path}</p>
          <p>{t("not_scanned")}</p>
        </div>)}
      </> : <p>{t("neverScanned")}</p>}
      {status && ["interrupted", "error"].includes(status.state) ? <p className="text-amber-200">{t("interrupted")}</p> : null}
      {notice ? <p role="status">{t(notice)}</p> : null}
    </div>
  </div>;
}
