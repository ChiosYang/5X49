"use client";

import { useEffect, useState, useSyncExternalStore } from "react";
import useSWR, { mutate as updateCache } from "swr";
import { useTranslations } from "next-intl";
import { AlertTriangle, CheckCircle2, Pencil, Plus, Unplug, X } from "lucide-react";
import { API } from "@/lib/api";
import { fetcher, responseError } from "@/lib/fetcher";
import { Button, IconButton } from "@/components/ui/Button";
import { TextInput } from "@/components/ui/FormControls";
import { createMediaRootsAutosave, type RootsNotice } from "@/lib/settings-autosave";
import { createAutosaveSessionRegistry } from "@/lib/settings-autosave-session";
import { createSettingsScanGuard } from "@/lib/settings-scan-guard";

export interface MediaRoots {
  media_dirs: string[];
  roots: { id: string; path: string; state: string }[];
}
const sessions = createAutosaveSessionRegistry<string[], Exclude<RootsNotice, "saved" | null>, MediaRoots>();

export default function MediaRootsControl() {
  const t = useTranslations("MediaRoots");
  const { data, error } = useSWR<MediaRoots>(API.settingsMediaDirs(), fetcher, { refreshInterval: 5000 });
  const [autosave] = useState(() => sessions.get(() => {
    const guard = createSettingsScanGuard();
    return {
    initial: data ?? null, value: result => result.media_dirs, create: createMediaRootsAutosave,
    active: active => { if (active) guard.acquire(); else guard.release(); },
    changed: state => { guard.setDraft(state.draft !== null); guard.setSaving(state.saving); },
    write: async paths => {
      const response = await fetch(API.settingsMediaDirs(), { method: "PUT", signal: AbortSignal.timeout(15000), headers: { "Content-Type": "application/json" }, body: JSON.stringify({ media_dirs: paths }) });
      if (!response.ok) {
        const message = (await responseError(response, "saveFailed")).message;
        throw new Error(message.includes("overlap") ? "overlap" : message.includes("absolute") ? "absolute" : "saveFailed");
      }
      const result = await response.json() as MediaRoots;
      // The app uses SWR's default cache. Publish before completing this shared
      // write, independent of mounted components, to discard older in-flight GETs.
      await updateCache(API.settingsMediaDirs(), result, false);
      void updateCache(API.settingsMediaDir());
      return result;
    },
  }; }, typeof window !== "undefined"));
  const { draft, saving: busy, notice, result } = useSyncExternalStore(autosave.subscribe, autosave.getSnapshot, autosave.getSnapshot);
  useEffect(() => { if (data) autosave.syncSaved(data); }, [autosave, data]);
  const values = draft ?? result?.media_dirs ?? data?.media_dirs ?? [];
  const change = (next: string[]) => { autosave.edit(next); void autosave.commit(); };
  return <div className="min-w-0 space-y-4 border-b border-line pb-6" aria-label={t("title")}>
    <div className="flex items-center justify-between gap-4">
      <h3 className="text-sm font-medium tracking-widest uppercase">{t("title")}</h3>
      <span className="group/add relative inline-flex">
        <IconButton data-roots-action variant="ghost" aria-label={t("addDirectory")} aria-describedby="add-directory-tooltip" disabled={!data || values.length >= 32} icon={<Plus aria-hidden className="h-4 w-4" />} onClick={() => { autosave.edit([...values, ""]); requestAnimationFrame(() => document.getElementById(`media-root-${values.length}`)?.focus()); }} />
        <span id="add-directory-tooltip" role="tooltip" className="pointer-events-none invisible absolute right-0 top-full z-20 mt-2 w-max max-w-56 border border-line-strong bg-surface-raised px-3 py-2 text-xs group-hover/add:visible group-focus-within/add:visible">{t("addDirectory")}</span>
      </span>
    </div>
    {error ? <p role="alert" className="text-sm text-danger">{t("loadFailed")}</p> : null}
    {values.map((value, index) => {
      const state = draft ? "unsaved" : (result ?? data)?.roots[index]?.state ?? "unavailable";
      const StatusIcon = state === "unsaved" ? Pencil : state === "accessible" ? CheckCircle2 : state === "offline" ? Unplug : AlertTriangle;
      const statusLabel = t(state);
      return <div key={index} className="min-w-0 space-y-2">
        <label htmlFor={`media-root-${index}`} className="text-xs text-ink-muted">{t("directory", { number: index + 1 })}</label>
        <div className="relative">
          <TextInput id={`media-root-${index}`} className="pr-24" value={value} onChange={event => autosave.edit(values.map((old, i) => i === index ? event.target.value : old))}
            onBlur={event => { if (!(event.relatedTarget instanceof Element && event.relatedTarget.closest('[data-roots-action]'))) void autosave.commit(); }}
            onKeyDown={event => { if (event.key === "Enter" && !event.nativeEvent.isComposing) { event.preventDefault(); void autosave.commit(); } }} />
          <div className="absolute inset-y-0 right-1 flex items-center gap-1">
            <span className="group/status relative inline-flex">
              <span role="img" tabIndex={0} aria-label={statusLabel} aria-describedby={`media-root-status-${index}`} className={`focus-ring inline-flex h-11 w-8 items-center justify-center ${state === "accessible" ? "text-success" : state === "unsaved" ? "text-ink-muted" : "text-warning"}`}>
                <StatusIcon aria-hidden="true" className="h-4 w-4" />
              </span>
              <span id={`media-root-status-${index}`} role="tooltip" className="pointer-events-none invisible absolute right-0 top-full z-20 mt-2 w-max max-w-56 border border-line-strong bg-surface-raised px-3 py-2 text-xs text-ink group-hover/status:visible group-focus-within/status:visible">{statusLabel}</span>
            </span>
            <IconButton data-roots-action variant="ghost" aria-label={t("removeDirectory", { number: index + 1 })} icon={<X aria-hidden="true" className="h-4 w-4" />} onClick={() => change(values.filter((_, i) => i !== index))} />
          </div>
        </div>
        {index > 0 ? <Button data-roots-action size="sm" variant="ghost" onClick={() => change([value, ...values.filter((_, i) => i !== index)])}>{t("makePrimary")}</Button> : null}
      </div>;
    })}
    {!values.length ? <p className="text-sm text-ink-muted">{t("noRoots")}</p> : null}
    {notice === "saveFailed" || draft !== null ? <div className="flex flex-wrap gap-2">
      {notice === "saveFailed" ? <Button data-roots-action size="sm" disabled={busy} onClick={() => void autosave.commit()}>{t("retry")}</Button> : null}
      {draft !== null ? <Button data-roots-action variant="ghost" disabled={busy} onClick={() => autosave.discard()}>{t("discard")}</Button> : null}
    </div> : null}
    {busy ? <p role="status" className="text-sm text-ink-muted">{t("saving")}</p> : notice ? <p role={notice === "saved" ? "status" : "alert"} className={`text-sm ${notice === "saved" ? "text-success" : "text-danger"}`}>{t(notice)}</p> : null}
  </div>;
}
