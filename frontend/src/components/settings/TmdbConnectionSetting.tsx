"use client";

import { PlugZap } from "lucide-react";
import { useTranslations } from "next-intl";
import { useTestTmdbKey } from "@/hooks/useSettings";
import { useTmdbKeyAutosave } from "@/hooks/useTmdbKeyAutosave";
import { useConnectionTest } from "@/hooks/useConnectionTest";
import { ConnectionControlGrid, SettingRow } from "./SettingsPrimitives";
import { ConnectionTestResult } from "./ConnectionTestResult";
import { Button, IconButton } from "@/components/ui/Button";
import { InlineFeedback, Spinner } from "@/components/ui/Feedback";
import { TextInput } from "@/components/ui/FormControls";

export default function TmdbConnectionSetting() {
  const t = useTranslations("Settings");
  const { autosave, state, data, error } = useTmdbKeyAutosave();
  const { trigger: testKey } = useTestTmdbKey();
  const test = useConnectionTest(() => testKey());
  const editable = Boolean(data) && data?.source !== "environment";
  const pending = state.saving || state.draft !== null;
  const sourceLabel = data?.source === "environment" ? t("tmdbSourceEnvironment") : data?.source === "settings" ? t("tmdbSourceSettings") : t("tmdbSourceMissing");
  const handleTest = () => {
    const current = autosave.getSnapshot();
    if (current.saving || current.draft !== null || !data?.configured) return;
    void test.run();
  };
  return <SettingRow title={t("tmdbApiKey")} saveStatus={state.notice === "saved" ? t("saved") : ""} feedback={
    state.notice && state.notice !== "saved" ? <div role="alert"><InlineFeedback tone="error">{t(state.notice)}</InlineFeedback></div> : error ? <div role="alert"><InlineFeedback tone="error">{t("tmdbLoadFailed")}</InlineFeedback></div> : null
  }>
    <ConnectionControlGrid>
      <div className="relative min-w-0">
        <TextInput type="password" value={state.draft ?? ""} disabled={!editable} aria-label={t("tmdbApiKey")} aria-busy={state.saving}
          autoComplete="off" aria-description={t(editable ? "tmdbApiKeyPlaceholder" : "tmdbApiKeyEnvironment")} placeholder={editable ? t("tmdbKeyInput") : ""}
          className="pr-28" onChange={event => { test.invalidate(); autosave.edit(event.target.value); }}
          onBlur={() => void autosave.commit()}
          onKeyDown={event => { if (event.key === "Enter" && !event.nativeEvent.isComposing) { event.preventDefault(); void autosave.commit(); } }} />
        <span className="pointer-events-none absolute inset-y-0 right-3 flex items-center gap-2">
          {state.saving ? <><Spinner className="h-3 w-3" /><span className="sr-only">{t("saving")}</span></> : null}
          <span className={`text-[10px] font-bold tracking-widest uppercase ${data?.configured ? "text-success" : "text-ink-disabled"}`}>{sourceLabel}</span>
        </span>
      </div>
      <span className="group/tmdb-test relative inline-flex shrink-0">
        <IconButton variant="ghost" aria-label={t("tmdbTestBtn")} aria-describedby="tmdb-test-tooltip" busy={test.busy} disabled={!data?.configured || pending}
          onClick={handleTest} icon={<PlugZap aria-hidden className="h-4 w-4" />} />
        <span id="tmdb-test-tooltip" role="tooltip" className="pointer-events-none invisible absolute right-0 top-full z-20 mt-2 w-max max-w-56 border border-line-strong bg-surface-raised px-3 py-2 text-xs group-hover/tmdb-test:visible group-focus-within/tmdb-test:visible">{t("tmdbTestBtn")}</span>
      </span>
      <ConnectionTestResult outcome={test.outcome} />
    </ConnectionControlGrid>
    {state.notice === "tmdbSaveFailed" ? <Button size="sm" className="mt-3" disabled={state.saving} onClick={() => void autosave.commit()}>{t("retrySave")}</Button> : null}
  </SettingRow>;
}
