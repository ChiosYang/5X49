"use client";

import { useTranslations } from "next-intl";
import { useBaseUrlAutosave } from "@/hooks/useBaseUrlAutosave";
import { ConnectionControlGrid, SettingRow } from "./SettingsPrimitives";
import { Button } from "@/components/ui/Button";
import { InlineFeedback } from "@/components/ui/Feedback";
import { TextInput } from "@/components/ui/FormControls";
export default function BaseUrlSetting({ onEdit }: { onEdit?: () => void }) {
  const t = useTranslations("Settings");
  const { autosave, state, data } = useBaseUrlAutosave();
  return <SettingRow title={t("baseUrl")} saveStatus={state.notice === "saved" ? t("saved") : ""} feedback={state.saving ? <InlineFeedback>{t("saving")}</InlineFeedback> : state.notice && state.notice !== "saved" ?
    <div role="alert"><InlineFeedback tone="error">{t(state.notice)}</InlineFeedback></div> : null}>
    <ConnectionControlGrid><div className="min-w-0">
    <TextInput type="url" aria-label={t("baseUrl")} value={state.draft ?? state.result?.base_url ?? data?.base_url ?? ""} placeholder="https://openrouter.ai/api/v1"
      onChange={event => { onEdit?.(); autosave.edit(event.target.value); }}
      onBlur={event => { if (!(event.relatedTarget instanceof Element && event.relatedTarget.closest('[data-base-url-action]'))) void autosave.commit(); }}
      onKeyDown={event => { if (event.key === "Enter" && !event.nativeEvent.isComposing) { event.preventDefault(); void autosave.commit(); } }} />
    </div></ConnectionControlGrid>
    {state.notice === "baseUrlSaveFailed" ? <Button data-base-url-action size="sm" className="mt-3" onClick={() => void autosave.commit()}>{t("retrySave")}</Button> : null}
  </SettingRow>;
}
