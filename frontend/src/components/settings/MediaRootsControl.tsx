"use client";

import { useRef, useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import { useTranslations } from "next-intl";
import { API } from "@/lib/api";
import { fetcher, responseError } from "@/lib/fetcher";
import { Button } from "@/components/ui/Button";
import { TextInput } from "@/components/ui/FormControls";
import FileBrowser from "@/components/FileBrowser";
import MediaScanResults from "./MediaScanResults";

export interface MediaRoots {
  media_dirs: string[];
  roots: { id: string; path: string; state: string }[];
}

export default function MediaRootsControl() {
  const t = useTranslations("MediaRoots");
  const { data, error, mutate } = useSWR<MediaRoots>(API.settingsMediaDirs(), fetcher, { refreshInterval: 5000 });
  const { mutate: refresh } = useSWRConfig();
  const [draft, setDraft] = useState<string[] | null>(null);
  const [browse, setBrowse] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
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
    <p className="text-sm leading-6 text-ink-subtle">{t("help")}</p>
    {error ? <p role="alert" className="text-sm text-danger">{t("loadFailed")}</p> : null}
    {values.map((value, index) => <div key={index} className="min-w-0 space-y-2 border-b border-line pb-4">
      <label htmlFor={`media-root-${index}`} className="text-xs text-ink-muted">{t("directory", { number: index + 1 })}{index === 0 ? ` · ${t("primary")}` : ""}</label>
      <TextInput id={`media-root-${index}`} value={value} disabled={busy} onChange={event => edit(values.map((old, i) => i === index ? event.target.value : old))} />
      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" variant="ghost" disabled={busy} onClick={() => setBrowse(index)}>{t("browse")}</Button>
        <Button size="sm" variant="ghost" disabled={busy} onClick={() => edit(values.filter((_, i) => i !== index))}>{t("remove")}</Button>
        {index > 0 ? <Button size="sm" variant="ghost" disabled={busy} onClick={() => edit([value, ...values.filter((_, i) => i !== index)])}>{t("makePrimary")}</Button> : null}
        <span className="text-xs text-ink-muted">{draft ? t("unsaved") : t(data?.roots[index]?.state ?? "unavailable")}</span>
      </div>
    </div>)}
    {!values.length ? <p className="text-sm text-ink-muted">{t("noRoots")}</p> : null}
    <div className="flex flex-wrap gap-2">
      <Button disabled={busy || !data || values.length >= 32} onClick={() => edit([...values, ""])}>{t("add")}</Button>
      <Button variant="primary" busy={busy} disabled={busy || draft === null || values.some(value => !value.trim())} onClick={() => void save()}>{t("save")}</Button>
      {draft ? <Button variant="ghost" disabled={busy} onClick={() => { setDraft(null); setNotice(null); }}>{t("discard")}</Button> : null}
    </div>
    <p className="text-xs leading-6 text-ink-muted">{t("removal")}</p>
    <p className="text-xs leading-6 text-ink-muted">{t("docker")}</p>
    {notice ? <p role="status" className="text-sm text-amber-200">{t(notice)}</p> : null}
    <MediaScanResults disabled={busy || draft !== null} />
    {browse !== null ? <FileBrowser isOpen initialPath={values[browse] || "/"} onSelect={path => { edit(values.map((value, i) => i === browse ? path : value)); setBrowse(null); }} onCancel={() => setBrowse(null)} /> : null}
  </div>;
}
