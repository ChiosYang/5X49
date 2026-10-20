"use client";

import { useState } from "react";
import useSWR from "swr";
import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/Button";
import { InlineFeedback, StateMessage } from "@/components/ui/Feedback";
import { API } from "@/lib/api";
import { fetcher } from "@/lib/fetcher";
import LibraryRuntimeStatus from "@/components/settings/LibraryRuntimeStatus";

type Check = {state:string;status_code?:number|null};
type Diagnostics = {
  database: Check & {schema_version:number|null;expected_schema_version:number};
  projections: Array<Check & {name:string}>;
  media: Check & {writable:boolean};backup_space:Check;tmdb:Check;
};

export default function DiagnosticsSettings() {
  const t = useTranslations("Maintenance");
  const area = useTranslations("SettingsArea");
  const diagnostic = useSWR<Diagnostics>(API.diagnostics());
  const [providers,setProviders] = useState<{tmdb:Check;artwork:Check}|null>(null);
  const [busy,setBusy] = useState(false);
  const [error,setError] = useState(false);
  const checkProviders = async () => {
    if (busy) return;
    setBusy(true);setError(false);setProviders(null);
    try { setProviders(await fetcher(API.providerDiagnostics())); }
    catch { setError(true); }
    finally { setBusy(false); }
  };
  return <div className="space-y-10">
    <section className="space-y-4">
      <h3 className="type-label text-ink-muted">{area("localChecks")}</h3>
      <p className="text-sm leading-6 text-ink-subtle">{t("diagnosticsDescription")}</p>
      {!diagnostic.data ? <StateMessage state={diagnostic.error ? "error" : "loading"}>{t(diagnostic.error ? "backendUnavailable" : "loading")}</StateMessage> : <dl className="divide-y divide-line border-y border-line">
        {([ ["database",diagnostic.data.database], ["media",diagnostic.data.media], ["backupSpace",diagnostic.data.backup_space], ["tmdbConfiguration",diagnostic.data.tmdb] ] as const).map(([name,check]) => <div key={name} className="flex flex-wrap justify-between gap-3 py-3 text-sm"><dt>{t(name)}</dt><dd className={check.state === "ready" || check.state === "configured" ? "text-success" : "text-warning"}>{t(`state_${check.state}`)}</dd></div>)}
        <div className="flex flex-wrap justify-between gap-3 py-3 text-sm"><dt>{t("schema")}</dt><dd>{diagnostic.data.database.schema_version ?? "—"} / {diagnostic.data.database.expected_schema_version}</dd></div>
        <div className="flex flex-wrap justify-between gap-3 py-3 text-sm"><dt>{t("mediaWriting")}</dt><dd>{t(diagnostic.data.media.writable ? "writable" : "readOnly")}</dd></div>
        <div className="flex flex-wrap justify-between gap-3 py-3 text-sm"><dt>{t("projections")}</dt><dd>{t(diagnostic.data.projections.length > 0 && diagnostic.data.projections.every(check => check.state === "ready") ? "state_ready" : "state_needs_attention")}</dd></div>
      </dl>}
      {diagnostic.error && diagnostic.data && <InlineFeedback tone="warning">{t("diagnosticRefreshFailed")}</InlineFeedback>}
      <div className="flex flex-wrap gap-3">
        <Button disabled={diagnostic.isValidating} busy={diagnostic.isValidating} onClick={() => void diagnostic.mutate().catch(() => undefined)}>{t("refreshDiagnostics")}</Button>
        <Button disabled={busy} busy={busy} onClick={() => void checkProviders()}>{t("checkProviders")}</Button>
      </div>
      <p className="text-xs leading-5 text-ink-subtle">{t("providerCheckDescription")}</p>
      <div role="status" aria-live="polite">
        {error && <InlineFeedback tone="error">{t("providerCheckFailed")}</InlineFeedback>}
        {providers && <div className="space-y-2 text-sm">{(["tmdb","artwork"] as const).map(name => <p key={name}>{t(name)}：{t(`state_${providers[name].state}`)}{providers[name].status_code != null ? ` · HTTP ${providers[name].status_code}` : ""}</p>)}</div>}
      </div>
    </section>
    <LibraryRuntimeStatus />
    <details className="border-b border-line pb-6">
      <summary className="focus-ring min-h-11 cursor-pointer py-3 text-sm font-medium">{t("projectionsCommand")}</summary>
      <pre className="mt-4 max-w-full overflow-x-auto border border-line bg-surface p-4 text-xs"><code>uv run python -m app.projections verify</code></pre>
    </details>
  </div>;
}
