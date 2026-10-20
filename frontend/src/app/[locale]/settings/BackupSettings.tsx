"use client";

import { useTranslations } from "next-intl";
import { DisclosurePanel } from "@/components/settings/SettingsPrimitives";
import MaintenanceBackup from "../library/manage/MaintenanceBackup";

export default function BackupSettings() {
  const t = useTranslations("Maintenance"), area = useTranslations("SettingsArea");
  const commands = [
    ["backupCommand", "uv run python -m app.backup --database data/library.db --backup-dir data/backups/manual"],
    ["verifyCommand", "uv run python -m app.migrations.restore --manifest <backup.manifest.json>"],
    ["exportCommand", "uv run python -m app.portability export --output data/exports/library-export.zip"],
  ] as const;
  return <div className="space-y-8">
    <MaintenanceBackup />
    <section id="restore" className="scroll-mt-28 space-y-4">
      <h3 className="type-label text-ink-muted">{area("fullBackup")}</h3>
      <p className="text-sm leading-6 text-ink-subtle">{t("backupCoverage")}</p>
      <p className="text-sm leading-6 text-warning">{t("backupPrivacy")}</p>
      <DisclosurePanel title={t("advancedTitle")} description={t("advancedDescription")}>
      <p className="text-sm leading-6 text-ink-subtle">{t("commandsContext")}</p>
      {commands.map(([label,command]) => <div key={label} className="space-y-2"><h3 className="text-sm font-bold">{t(label)}</h3><pre className="overflow-x-auto border border-line bg-surface p-4 text-xs"><code>{command}</code></pre></div>)}
      <p className="text-sm leading-6 text-ink-subtle">{t("dockerBackup")}</p>
      <pre className="overflow-x-auto border border-line bg-surface p-4 text-xs"><code>docker compose run --rm --no-deps backend python -m app.backup --database data/library.db --backup-dir data/backups/manual</code></pre>
      <h3 className="text-sm font-bold">{t("restoreTitle")}</h3>
      <ol className="list-decimal space-y-3 pl-5 text-sm leading-6 text-ink-subtle">{(["restoreStop","restoreVerify","restoreReplace","restoreCheck"] as const).map(step => <li key={step}>{t(step)}</li>)}</ol>
      <p className="text-xs leading-5 text-ink-subtle">{t("runbook")}</p>
      </DisclosurePanel>
    </section>
  </div>;
}
