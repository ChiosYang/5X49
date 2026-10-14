"use client";

import { useRef, useState } from "react";
import useSWR from "swr";
import { useLocale, useTranslations } from "next-intl";
import { API } from "@/lib/api";
import { Link } from "@/i18n/routing";
import { Button } from "@/components/ui/Button";
import { healthStates, type HealthFile, type HealthStatus } from "@/lib/video-health";

export default function VideoHealthMaintenance() {
  const t = useTranslations("VideoHealth");
  const locale = useLocale();
  const [filter, setFilter] = useState("abnormal");
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const lock = useRef(false);
  const status = useSWR<HealthStatus>(API.videoHealth(), { refreshInterval: 5000 });
  const files = useSWR<{ items: HealthFile[]; total: number }>(API.videoHealthFiles(filter, offset), { refreshInterval: 5000 });
  const detail = useSWR<HealthFile>(selected ? API.videoHealthFile(selected) : null, { refreshInterval: 5000 });
  async function action(id: string, action: string) {
    if (lock.current) return;
    lock.current = true; setBusy(true); setNotice(null);
    try {
      const response = await fetch(API.videoHealthFile(id), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action }), signal: AbortSignal.timeout(15000) });
      if (!response.ok) throw new Error();
      await Promise.all([files.mutate(), status.mutate(), detail.mutate()]); setNotice(t("accepted"));
    } catch { setNotice(t("writeFailed")); }
    finally { lock.current = false; setBusy(false); }
  }
  const current = detail.data;
  return <section id="video-health" aria-labelledby="video-health-maintenance" className="page-x min-w-0 scroll-mt-28 border-b border-line py-6 text-ink">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <h2 id="video-health-maintenance" className="type-section-title">{t("title")}</h2>
      <Link href="/settings?section=library" className="focus-ring inline-flex min-h-11 items-center text-xs underline underline-offset-4">{t("settingsLink")}</Link>
    </div>
    <p className="mt-2 max-w-3xl text-xs leading-6 text-ink-subtle">{t("limits")}</p>
    {status.data?.unread ? <p role="status" className="mt-3 text-sm text-warning">{t("notification", { count: status.data.unread })}</p> : null}
    <label className="mt-4 flex flex-wrap items-center gap-3 text-sm">{t("filter")}<select value={filter} onChange={event => { setFilter(event.target.value); setOffset(0); setSelected(null); }} className="focus-ring min-h-11 border border-line bg-canvas px-3">{["all", ...healthStates].map(state => <option key={state} value={state}>{t(state === "all" ? "all" : `state_${state}`)}</option>)}</select></label>
    {files.error || status.error ? <p role="alert" className="mt-3 text-warning">{t("loadFailed")}</p> : null}
    <div className="mt-4 space-y-2">
      {files.data?.items.map(file => <div key={file.asset_id} className="flex min-w-0 flex-wrap items-center justify-between gap-3 border-t border-line py-3">
        <div className="min-w-0"><p className="break-words text-sm">{file.title} · {file.filename}</p><p className="mt-1 text-xs text-ink-subtle">{t(`state_${file.status}`)}{file.error_code ? ` · ${t(`error_${file.error_code}`)}` : ""}</p>
          {file.status === "checking" ? <p className="text-xs">{t("progress", { seconds: Math.round(file.decoded_seconds) })}</p> : null}
        </div>
        {file.id ? <Button size="sm" onClick={() => setSelected(file.id)}>{t("details")}</Button> : null}
      </div>)}
      {files.data && !files.data.items.length ? <p className="text-xs text-ink-subtle">{t("empty")}</p> : null}
    </div>
    {files.data && files.data.total > 20 ? <div className="mt-3 flex items-center gap-3"><Button size="sm" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 20))}>{t("previous")}</Button><span className="text-xs">{offset + 1} / {files.data.total}</span><Button size="sm" disabled={offset + 20 >= files.data.total} onClick={() => setOffset(offset + 20)}>{t("next")}</Button></div> : null}
    {selected ? <div className="mt-5 min-w-0 border border-line p-4" aria-label={t("details")}>
      <div className="flex justify-between gap-3"><h3 className="text-sm font-semibold">{t("details")}</h3><Button size="sm" onClick={() => setSelected(null)}>{t("close")}</Button></div>
      {detail.error ? <p role="alert" className="text-warning">{t("loadFailed")}</p> : null}
      {current ? <div className="mt-3 space-y-2 text-xs leading-6">
        <p className="break-words">{current.title} · {current.filename}</p>
        {!current.current ? <p className="text-warning">{t("versionStale")}{current.unavailable_reason ? ` · ${t(`error_${current.unavailable_reason}`)}` : ""}</p> : null}
        <p>{t("container")}: {t(`state_${current.container_status}`)} · {t("deep")}: {t(`state_${current.decode_status}`)}</p>
        <p className="break-all">{t("version")}: {current.version_key}</p>
        <p>{t("size")}: {current.version?.size ?? "—"} B · {t("checked")}: {current.checked_at ? new Date(current.checked_at * 1000).toLocaleString(locale) : "—"}</p>
        {current.error_code ? <p>{t(`error_${current.error_code}`)}</p> : null}
        <p>{t("positionUnknown")}</p>
        <p>{t("progress", { seconds: Math.round(current.decoded_seconds) })} · {t("progressHelp")}</p>
        <div className="flex flex-wrap gap-3">
          {current.id && current.status === "abnormal" ? <Button size="sm" disabled={busy} onClick={() => void action(current.id!, "acknowledge")}>{t("acknowledge")}</Button> : null}
          {current.id && current.current && ["incomplete", "unsupported", "abnormal"].includes(current.status) ? <Button size="sm" disabled={busy} onClick={() => void action(current.id!, "retry")}>{t("retry")}</Button> : null}
          {current.id && ["unchecked", "queued", "checking"].includes(current.status) ? <Button size="sm" disabled={busy} onClick={() => void action(current.id!, "cancel")}>{t("cancelFile")}</Button> : null}
          {current.film_id ? <Link href={`/library/${current.film_id}`} className="focus-ring inline-flex min-h-11 items-center underline">{t("film")}</Link> : null}
        </div>
      </div> : null}
    </div> : null}
    {notice ? <p role="status" className="mt-3 text-xs text-warning">{notice}</p> : null}
  </section>;
}
