"use client";

import { useRef, useState } from "react";
import useSWR from "swr";
import { useTranslations } from "next-intl";
import { useRouter } from "@/i18n/routing";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { TextInput, TextArea } from "@/components/ui/FormControls";
import { InlineFeedback } from "@/components/ui/Feedback";
import { API } from "@/lib/api";
import { responseError } from "@/lib/fetcher";
import { useFilmAction } from "@/hooks/useFilmAction";
import { metadataFields, metadataDraft, metadataModes, metadataChanges, metadataRequestKey, type MetadataView, type MetadataRequest } from "@/lib/film-metadata";

export default function FilmMetadataEditor({ filmId }: { filmId: string }) {
  const t = useTranslations("FilmMetadata");
  const router = useRouter();
  const { data, error: readError, mutate } = useSWR<MetadataView>(API.filmMetadata(filmId));
  const refresh = useFilmAction(filmId, { metadata: true });
  const [open, setOpen] = useState(false);
  const [baseline, setBaseline] = useState<MetadataView | null>(null);
  const [draft, setDraft] = useState<ReturnType<typeof metadataDraft> | null>(null);
  const [manual, setManual] = useState<ReturnType<typeof metadataModes> | null>(null);
  const [pending, setPending] = useState(false);
  const [loading, setLoading] = useState(false);
  const [failure, setFailure] = useState<"loadFailed" | "stale" | "failed" | null>(null);
  const [uncertain, setUncertain] = useState(false);
  const guard = useRef(false);
  const retry = useRef<MetadataRequest | null>(null);
  const readAbort = useRef<AbortController | null>(null);
  let changes: MetadataRequest["changes"] = {};
  let invalid: string | null = null;
  try { if (baseline && draft && manual) changes = metadataChanges(baseline, draft, manual); }
  catch (error) { invalid = error instanceof Error ? error.message : "title"; }

  const load = async () => {
    if (guard.current) return;
    const controller = new AbortController(); readAbort.current = controller;
    guard.current = true; setPending(true); setLoading(true); setFailure(null);
    try {
      const response = await fetch(API.filmMetadata(filmId), { signal: AbortSignal.any([controller.signal, AbortSignal.timeout(15000)]) });
      if (!response.ok) throw await responseError(response, t("loadFailed"));
      const latest = await response.json() as MetadataView;
      if (controller.signal.aborted) return;
      await mutate(latest, { revalidate: false });
      if (controller.signal.aborted) return;
      setBaseline(latest); setDraft(metadataDraft(latest)); setManual(metadataModes(latest));
      retry.current = null; setUncertain(false);
    } catch { if (!controller.signal.aborted) setFailure("loadFailed"); }
    finally { if (readAbort.current === controller) { readAbort.current = null; guard.current = false; setPending(false); setLoading(false); } }
  };
  const close = () => {
    if (guard.current && !readAbort.current) return;
    readAbort.current?.abort(); readAbort.current = null;
    guard.current = false; setPending(false); setLoading(false);
    setOpen(false);
    if (uncertain) { void mutate(); router.refresh(); }
    retry.current = null; setUncertain(false);
  };
  const save = async () => {
    if (guard.current || !baseline || invalid || failure === "stale" || !Object.keys(changes).length) return;
    guard.current = true; setPending(true); setFailure(null);
    let result: MetadataView;
    try {
      const request = retry.current ?? { revision: baseline.revision, idempotency_key: metadataRequestKey(), changes };
      retry.current = request;
      const response = await fetch(API.filmMetadata(filmId), { method: "PATCH",
        headers: { "Content-Type": "application/json" }, body: JSON.stringify(request), signal: AbortSignal.timeout(15000) });
      if (!response.ok) {
        if (response.status === 409) { setFailure("stale"); setUncertain(false); retry.current = null; return; }
        if (response.status >= 400 && response.status < 500) { retry.current = null; setUncertain(false); }
        else setUncertain(true);
        throw await responseError(response, t("failed"));
      }
      result = await response.json();
    } catch {
      setFailure("failed"); setUncertain(retry.current !== null); return;
    } finally { guard.current = false; setPending(false); }
    // A successful write must never be retried because a subsequent read failed.
    retry.current = null; setUncertain(false); setOpen(false);
    await mutate(result, { revalidate: false });
    await refresh.retryRefresh();
  };
  const source = (view: MetadataView, key: typeof metadataFields[number]) => {
    const kind = view.fields[key].automatic_source.source_kind;
    return t(kind === "nfo" ? "sourceNfo" : kind === "tmdb" ? "sourceTmdb" : kind === "filename" ? "sourceFilename" : "sourceLibrary");
  };

  return <section aria-label={t("heading")} className="space-y-5 border-b border-line-strong px-8 py-10 md:px-16">
    <div className="flex flex-wrap items-center justify-between gap-4">
      <h2 className="type-section-title">{t("heading")}</h2>
      <Button onClick={() => { setBaseline(null); setDraft(null); setManual(null); setOpen(true); refresh.clear(); void load(); }}>{t("edit")}</Button>
    </div>
    <p className="max-w-3xl text-sm text-ink-muted">{t("help")}</p>
    {data && <dl className="grid grid-cols-2 gap-4 lg:grid-cols-4">{metadataFields.map(key => <div key={key}>
      <dt className="type-label text-ink-subtle">{t(key)}</dt>
      <dd className="mt-2 text-sm text-ink-muted">{data.fields[key].manual ? t("manual") : source(data, key)}</dd>
    </div>)}</dl>}
    {readError && <InlineFeedback tone="error">{t("loadFailed")} <button className="focus-ring min-h-11 underline" onClick={() => void mutate()}>{t("retry")}</button></InlineFeedback>}
    {refresh.feedback && <InlineFeedback tone={refresh.feedback.kind === "refreshFailed" ? "warning" : "success"}>{refresh.feedback.kind === "refreshFailed" ? t("refreshFailed") : t("saved")}</InlineFeedback>}
    {refresh.feedback?.kind === "refreshFailed" && <Button disabled={refresh.pending} onClick={() => void refresh.retryRefresh()}>{t("refresh")}</Button>}
    <Dialog open={open} onClose={close} closeLabel={t("cancel")} ariaLabel={t("edit")} size="md" glass={false}
      closeOnBackdrop={false} closeOnEscape={!pending || loading} panelClassName="max-h-[90dvh] overflow-y-auto border border-line-strong">
      <form className="space-y-6 p-5 sm:p-8" onSubmit={event => { event.preventDefault(); void save(); }}>
        <h2 className="type-section-title">{t("edit")}</h2>
        <p className="text-sm text-ink-muted">{t("help")}</p>
        {pending && !baseline && <p role="status">{t("loading")}</p>}
        {baseline && draft && manual && metadataFields.map(key => <div key={key} className="space-y-2 border-b border-line pb-5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <label htmlFor={`metadata-${key}`} className="type-label text-ink-subtle">{t(key)}</label>
            <span className="text-xs text-ink-muted">{manual[key] ? t("manual") : t("automatic")}</span>
          </div>
          {key === "overview" ? <TextArea id={`metadata-${key}`} value={draft[key]} rows={4} disabled={pending || uncertain || failure === "stale"}
            onChange={event => { setDraft({ ...draft, [key]: event.target.value }); setManual({ ...manual, [key]: true }); }} />
            : <TextInput id={`metadata-${key}`} value={draft[key]} maxLength={key === "year" ? 4 : undefined} inputMode={key === "year" ? "numeric" : "text"}
              disabled={pending || uncertain || failure === "stale"} onChange={event => { setDraft({ ...draft, [key]: event.target.value }); setManual({ ...manual, [key]: true }); }} />}
          {key === "year" && <p className="text-xs text-ink-muted">{t("yearHelp")}</p>}
          <details className="text-xs text-ink-muted">
            <summary className="focus-ring min-h-8 cursor-pointer">{t("source", { source: source(baseline, key) })}</summary>
            <p className="mt-2 max-h-32 overflow-y-auto whitespace-pre-wrap break-words">{String(baseline.fields[key].automatic_value ?? t("unknown"))}</p>
            {baseline.fields[key].automatic_source.conflicted && <p>{t("sourceConflict")}</p>}
          </details>
          <button type="button" disabled={pending || uncertain || failure === "stale"} className="focus-ring min-h-9 text-xs underline disabled:opacity-50"
            onClick={() => { setManual({ ...manual, [key]: !manual[key] }); if (manual[key]) setDraft({ ...draft, [key]: String(baseline.fields[key].automatic_value ?? "") }); }}>
            {manual[key] ? t("reset", { field: t(key) }) : t("protect", { field: t(key) })}
          </button>
          {!manual[key] && baseline.fields[key].manual && <p className="text-xs text-ink-muted">{t("resetPending")}</p>}
        </div>)}
        {invalid && <InlineFeedback tone="error">{t(invalid === "year" ? "invalidYear" : "invalidText")}</InlineFeedback>}
        {failure && <InlineFeedback tone="error">{t(failure)}</InlineFeedback>}
        {uncertain && <p className="text-sm text-ink-muted">{t("retryHelp")}</p>}
        {(failure === "stale" || failure === "loadFailed") && <Button disabled={pending} onClick={() => void load()}>{t("reload")}</Button>}
        <div className="flex flex-wrap justify-end gap-3">
          <Button disabled={pending && !loading} onClick={close}>{t("cancel")}</Button>
          <Button type="submit" variant="primary" busy={pending} disabled={pending || !baseline || !!invalid || failure === "stale" || !Object.keys(changes).length}>{uncertain ? t("retry") : t("save")}</Button>
        </div>
      </form>
    </Dialog>
  </section>;
}
