"use client";

import { useRef, useState } from "react";
import useSWR from "swr";
import { useTranslations } from "next-intl";
import { Link } from "@/i18n/routing";
import { API } from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { ToggleSwitch } from "@/components/ui/FormControls";
import type { HealthStatus } from "@/lib/video-health";
import { settingsHref } from "@/lib/settings-navigation";

async function write(url: string, body?: object, method = "POST") {
  const response = await fetch(url, { method, headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined, signal: AbortSignal.timeout(15000) });
  if (!response.ok) throw new Error("health_write_failed");
}

export default function VideoHealthSettings({ mode = "automatic" }: { mode?: "automatic" | "controls" }) {
  const t = useTranslations("VideoHealth");
  const query = useSWR<HealthStatus>(API.videoHealth(), { refreshInterval: 5000 });
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<"accepted" | "writeFailed" | null>(null);
  const lock = useRef(false);
  async function perform(url: string, body?: object, method = "POST") {
    if (lock.current) return;
    lock.current = true; setBusy(true); setNotice(null);
    try { await write(url, body, method); await query.mutate(); setNotice("accepted"); }
    catch { setNotice("writeFailed"); }
    finally { lock.current = false; setBusy(false); }
  }
  const data = query.data;
  const automatic = mode === "automatic";
  const headingId = automatic ? "video-health-settings" : "video-health-controls";
  return <section aria-labelledby={headingId} className="min-w-0 scroll-mt-28">
    <div className={`flex items-start justify-between gap-4 ${automatic ? "border-b border-line pb-6" : ""}`}>
      <div className="min-w-0"><h3 id={headingId} className="text-sm font-medium tracking-widest text-ink uppercase">{t(automatic ? "automatic" : "controls")}</h3>
        {automatic ? <p className="mt-2 text-xs leading-5 text-ink-muted">{t("automaticDescription")}</p> : null}
      </div>
      {automatic && data ? <ToggleSwitch checked={data.config.enabled} disabled={busy} label={t("automatic")} onChange={() => void perform(API.videoHealthConfig(), { enabled: !data.config.enabled }, "PUT")} /> : null}
    </div>
    {query.error ? <p role="alert" className="mt-3 text-warning">{t("loadFailed")}</p> : null}
    {!data && !query.error ? <p className="mt-3 text-sm">{t("loading")}</p> : null}
    {data && !automatic ? <>
      <div className="mt-5 flex flex-wrap items-center gap-3">
        <Button className="max-w-full" size="sm" busy={busy} onClick={() => void perform(API.videoHealthQueue())}>{t("queue")}</Button>
        <Button className="max-w-full" size="sm" disabled={busy} onClick={() => void perform(API.videoHealthConfig(), { paused: !data.config.paused }, "PUT")}>{t(data.config.paused ? "resume" : "pause")}</Button>
        <Button className="max-w-full" size="sm" disabled={busy} onClick={() => void perform(API.videoHealthCancel())}>{t("cancel")}</Button>
      </div>
    </> : null}
    {automatic ? <Link href={settingsHref("video-checks", "video-health")} className="focus-ring mt-3 inline-flex min-h-11 items-center text-sm underline underline-offset-4">{t("maintenanceLink")}</Link> : null}
    {notice ? <p role={notice === "writeFailed" ? "alert" : "status"} className={`mt-3 text-xs ${notice === "writeFailed" ? "text-danger" : "text-success"}`}>{t(notice)}</p> : null}
  </section>;
}
