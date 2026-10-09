"use client";

import { useState } from "react";
import useSWR from "swr";
import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/Button";
import { InlineFeedback, StateMessage } from "@/components/ui/Feedback";
import { API } from "@/lib/api";
import { fetcher } from "@/lib/fetcher";

type Check = {state:string;status_code?:number|null};
type Diagnostics = {
  database: Check & {schema_version:number|null;expected_schema_version:number};
  projections: Array<Check & {name:string}>;
  media: Check & {writable:boolean};backup_space:Check;tmdb:Check;
};

export default function MaintenanceSettings() {
  const t = useTranslations("Maintenance");
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
  const commands = [
    ["backupCommand", "uv run python -m app.backup --database data/library.db --backup-dir data/backups/manual"],
    ["verifyCommand", "uv run python -m app.migrations.restore --manifest <backup.manifest.json>"],
    ["projectionsCommand", "uv run python -m app.projections verify"],
    ["exportCommand", "uv run python -m app.portability export --output data/exports/library-export.zip"],
  ] as const;
  return <div className="space-y-10">
    <section className="space-y-4">
      <h2 className="type-section-title">{t("diagnosticsTitle")}</h2>
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
    <section className="space-y-4 border-t border-line pt-8">
      <h2 className="type-section-title">{t("backupTitle")}</h2>
      <p className="text-sm leading-6 text-ink-subtle">{t("backupCoverage")}</p>
      <p className="text-sm leading-6 text-warning">{t("backupPrivacy")}</p>
      <p className="text-sm leading-6 text-ink-subtle">{t("commandsContext")}</p>
      {commands.map(([label,command]) => <div key={label} className="space-y-2"><h3 className="text-sm font-bold">{t(label)}</h3><pre className="overflow-x-auto border border-line bg-surface p-4 text-xs"><code>{command}</code></pre></div>)}
      <p className="text-sm leading-6 text-ink-subtle">{t("dockerBackup")}</p>
      <pre className="overflow-x-auto border border-line bg-surface p-4 text-xs"><code>docker compose run --rm --no-deps backend python -m app.backup --database data/library.db --backup-dir data/backups/manual</code></pre>
      <h3 className="text-sm font-bold">{t("restoreTitle")}</h3>
      <ol className="list-decimal space-y-3 pl-5 text-sm leading-6 text-ink-subtle">{(["restoreStop","restoreVerify","restoreReplace","restoreCheck"] as const).map(step => <li key={step}>{t(step)}</li>)}</ol>
      <p className="text-xs leading-5 text-ink-subtle">{t("runbook")}</p>
    </section>
  </div>;
}
