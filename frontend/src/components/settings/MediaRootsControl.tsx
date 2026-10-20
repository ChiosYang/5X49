"use client";

import { useRef, useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import { useTranslations } from "next-intl";
import { AlertTriangle, CheckCircle2, Pencil, Unplug, X } from "lucide-react";
import { API } from "@/lib/api";
import { fetcher, responseError } from "@/lib/fetcher";
import { Button, IconButton } from "@/components/ui/Button";
import { TextInput } from "@/components/ui/FormControls";
import { useSettingsSession } from "./SettingsSession";

export interface MediaRoots {
  media_dirs: string[];
  roots: { id: string; path: string; state: string }[];
}

export default function MediaRootsControl() {
  const t = useTranslations("MediaRoots");
  const { data, error, mutate } = useSWR<MediaRoots>(API.settingsMediaDirs(), fetcher, { refreshInterval: 5000 });
  const { mutate: refresh } = useSWRConfig();
  const { rootsDraft: draft, setRootsDraft: setDraft, rootsSaving: busy, setRootsSaving: setBusy } = useSettingsSession();
  const [notice, setNotice] = useState<string | null>(null);
  const lock = useRef(false);
  const values = draft ?? data?.media_dirs ?? [];
  const edit = (next: string[]) => { setDraft(next); setNotice(null); };
  async function save() {
    if (lock.current) return;
    lock.current = true; setBusy(true); setNotice(null);
    try {
      const response = await fetch(API.settingsMediaDirs(), { method: "PUT", signal: AbortSignal.timeout(15000), headers: { "Content-Type": "application/json" }, body: JSON.stringify({ media_dirs: values.map(value => value.trim()) }) });
      if (!response.ok) {
        const message = (await responseError(response, "saveFailed")).message;
        throw new Error(message.includes("overlap") ? "overlap" : message.includes("absolute") ? "absolute" : "saveFailed");
      }
      await mutate(await response.json(), false);
      setDraft(null); setNotice("saved");
      void refresh(API.settingsMediaDir());
    } catch (failure) {
      setNotice(failure instanceof Error && ["overlap", "absolute"].includes(failure.message) ? failure.message : "saveFailed");
    } finally { lock.current = false; setBusy(false); }
  }
  return <div className="min-w-0 space-y-4" aria-label={t("title")}>
    {error ? <p role="alert" className="text-sm text-danger">{t("loadFailed")}</p> : null}
    {values.map((value, index) => {
      const state = draft ? "unsaved" : data?.roots[index]?.state ?? "unavailable";
      const StatusIcon = state === "unsaved" ? Pencil : state === "accessible" ? CheckCircle2 : state === "offline" ? Unplug : AlertTriangle;
      const statusLabel = t(state);
      return <div key={index} className="min-w-0 space-y-2">
        <label htmlFor={`media-root-${index}`} className="text-xs text-ink-muted">{t("directory", { number: index + 1 })}</label>
        <div className="relative">
          <TextInput id={`media-root-${index}`} className="pr-24" value={value} disabled={busy} onChange={event => edit(values.map((old, i) => i === index ? event.target.value : old))} />
          <div className="absolute inset-y-0 right-1 flex items-center gap-1">
            <span className="group/status relative inline-flex">
              <span role="img" tabIndex={0} aria-label={statusLabel} aria-describedby={`media-root-status-${index}`} className={`focus-ring inline-flex h-11 w-8 items-center justify-center ${state === "accessible" ? "text-success" : state === "unsaved" ? "text-ink-muted" : "text-warning"}`}>
                <StatusIcon aria-hidden="true" className="h-4 w-4" />
              </span>
              <span id={`media-root-status-${index}`} role="tooltip" className="pointer-events-none invisible absolute right-0 top-full z-20 mt-2 w-max max-w-56 border border-line-strong bg-surface-raised px-3 py-2 text-xs text-ink group-hover/status:visible group-focus-within/status:visible">{statusLabel}</span>
            </span>
            <IconButton variant="ghost" disabled={busy} aria-label={t("removeDirectory", { number: index + 1 })} icon={<X aria-hidden="true" className="h-4 w-4" />} onClick={() => edit(values.filter((_, i) => i !== index))} />
          </div>
        </div>
        {index > 0 ? <Button size="sm" variant="ghost" disabled={busy} onClick={() => edit([value, ...values.filter((_, i) => i !== index)])}>{t("makePrimary")}</Button> : null}
      </div>;
    })}
    {!values.length ? <p className="text-sm text-ink-muted">{t("noRoots")}</p> : null}
    <div className="flex flex-wrap gap-2">
      <Button disabled={busy || !data || values.length >= 32} onClick={() => edit([...values, ""])}>{t("add")}</Button>
      <Button variant="primary" busy={busy} disabled={busy || draft === null || values.some(value => !value.trim())} onClick={() => void save()}>{t("save")}</Button>
      {draft ? <Button variant="ghost" disabled={busy} onClick={() => { setDraft(null); setNotice(null); }}>{t("discard")}</Button> : null}
    </div>
    {notice ? <p role={notice === "saved" ? "status" : "alert"} className={`text-sm ${notice === "saved" ? "text-success" : "text-danger"}`}>{t(notice)}</p> : null}
  </div>;
}
