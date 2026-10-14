"use client";

import { useRef, useState } from "react";
import useSWR from "swr";
import { useTranslations } from "next-intl";
import { Link } from "@/i18n/routing";
import { API } from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { healthStates, minuteTime, parseTime, type HealthConfig, type HealthStatus } from "@/lib/video-health";

async function write(url: string, body?: object, method = "POST") {
  const response = await fetch(url, { method, headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined, signal: AbortSignal.timeout(15000) });
  if (!response.ok) throw new Error("health_write_failed");
}

function Schedule({ config, save, busy }: { config: HealthConfig; save: (values: object) => Promise<void>; busy: boolean }) {
  const t = useTranslations("VideoHealth");
  const [start, setStart] = useState(minuteTime(config.start_minute));
  const [end, setEnd] = useState(minuteTime(config.end_minute));
  const [budget, setBudget] = useState(String(config.daily_budget_minutes));
  const valid = parseTime(start) !== null && parseTime(end) !== null && /^\d+$/.test(budget) && Number(budget) >= 1 && Number(budget) <= 1440;
  return <form onSubmit={event => { event.preventDefault(); if (valid) void save({ start_minute: parseTime(start), end_minute: parseTime(end), daily_budget_minutes: Number(budget) }); }} className="mt-5 space-y-3">
    <div className="flex flex-wrap gap-4">
      <label className="flex min-w-0 flex-col gap-2 text-xs">{t("start")}<input type="time" value={start} onChange={event => setStart(event.target.value)} required className="focus-ring border border-line bg-surface p-2 text-ink" /></label>
      <label className="flex min-w-0 flex-col gap-2 text-xs">{t("end")}<input type="time" value={end} onChange={event => setEnd(event.target.value)} required className="focus-ring border border-line bg-surface p-2 text-ink" /></label>
      <label className="flex min-w-0 flex-col gap-2 text-xs">{t("budget")}<input type="number" min={1} max={1440} value={budget} onChange={event => setBudget(event.target.value)} required className="focus-ring w-32 border border-line bg-surface p-2 text-ink" /></label>
    </div>
    <p className="max-w-3xl text-xs leading-6 text-ink-subtle">{t("scheduleHelp")}</p>
    <Button type="submit" size="sm" busy={busy} disabled={!valid}>{t("save")}</Button>
  </form>;
}

export default function VideoHealthSettings() {
  const t = useTranslations("VideoHealth");
  const query = useSWR<HealthStatus>(API.videoHealth(), { refreshInterval: 5000 });
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const lock = useRef(false);
  async function perform(url: string, body?: object, method = "POST") {
    if (lock.current) return;
    lock.current = true; setBusy(true); setNotice(null);
    try { await write(url, body, method); await query.mutate(); setNotice(t("accepted")); }
    catch { setNotice(t("writeFailed")); }
    finally { lock.current = false; setBusy(false); }
  }
  const data = query.data;
  return <section aria-labelledby="video-health-settings" className="min-w-0 border-t border-line pt-8">
    <h2 id="video-health-settings" className="type-section-title">{t("title")}</h2>
    <p className="mt-3 max-w-3xl text-sm leading-7 text-ink-subtle">{t("description")}</p>
    {query.error ? <p role="alert" className="mt-3 text-warning">{t("loadFailed")}</p> : null}
    {!data && !query.error ? <p className="mt-3 text-sm">{t("loading")}</p> : null}
    {data ? <>
      <div className="mt-5 flex flex-wrap items-center gap-3">
        <label className="inline-flex min-h-11 items-center gap-3 text-sm"><input type="checkbox" checked={data.config.enabled} disabled={busy} onChange={event => void perform(API.videoHealthConfig(), { enabled: event.target.checked }, "PUT")} />{t("automatic")}</label>
        <Button size="sm" busy={busy} onClick={() => void perform(API.videoHealthQueue())}>{t("queue")}</Button>
        <Button size="sm" disabled={busy} onClick={() => void perform(API.videoHealthConfig(), { paused: !data.config.paused }, "PUT")}>{t(data.config.paused ? "resume" : "pause")}</Button>
        <Button size="sm" disabled={busy} onClick={() => void perform(API.videoHealthCancel())}>{t("cancel")}</Button>
      </div>
      <Schedule key={`${data.config.start_minute}:${data.config.end_minute}:${data.config.daily_budget_minutes}`} config={data.config} busy={busy} save={values => perform(API.videoHealthConfig(), values, "PUT")} />
      <div className="mt-5 text-xs leading-6" aria-live="polite">
        <p>{t(`reason_${data.reason}`)} · {t("used", { minutes: Math.round(data.used_seconds / 60) })}</p>
        {data.active_progress ? <p>{t("progress", { seconds: Math.round(data.active_progress.decoded_seconds) })}</p> : null}
        {data.queue_sweep_pending ? <p>{t("batchPending")}</p> : null}
        <dl className="mt-3 flex flex-wrap gap-x-5 gap-y-2">{healthStates.map(state => <div key={state} className="flex gap-2"><dt>{t(`state_${state}`)}</dt><dd>{data.counts[state]}</dd></div>)}</dl>
        <p className="mt-3 text-ink-subtle">{t(data.load.observable ? "loadObservable" : "loadLimited")}</p>
      </div>
    </> : null}
    <p className="mt-4 max-w-3xl text-xs leading-6 text-ink-subtle">{t("limits")}</p>
    <Link href="/library/manage#video-health" className="focus-ring mt-3 inline-flex min-h-11 items-center text-sm underline underline-offset-4">{t("maintenanceLink")}</Link>
    {notice ? <p role="status" className="mt-3 text-xs text-warning">{notice}</p> : null}
  </section>;
}
