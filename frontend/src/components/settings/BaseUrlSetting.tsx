"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { useBaseUrl, useUpdateBaseUrl } from "@/hooks/useSettings";
import { createBaseUrlAutosave, type BaseUrlSaveState } from "@/lib/settings-autosave";
import { SettingRow } from "./SettingsPrimitives";
import { Button } from "@/components/ui/Button";
import { InlineFeedback } from "@/components/ui/Feedback";
import { TextInput } from "@/components/ui/FormControls";

export default function BaseUrlSetting() {
  const t = useTranslations("Settings");
  const { data, mutate: cacheBaseUrl } = useBaseUrl();
  const { trigger: updateBaseUrl } = useUpdateBaseUrl();
  const [state, setState] = useState<BaseUrlSaveState>({ draft: null, saving: false, notice: null });
  const [autosave] = useState(() => createBaseUrlAutosave({ initial: data?.base_url ?? null, changed: setState,
    write: async value => {
      const result = await updateBaseUrl(value);
      const saved = typeof result.base_url === "string" ? result.base_url : value;
      await cacheBaseUrl({ base_url: saved }, false);
      return saved;
    },
  }));
  useEffect(() => { if (data) autosave.syncSaved(data.base_url); }, [autosave, data]);
  return <SettingRow title={t("baseUrl")} feedback={state.saving ? <InlineFeedback>{t("saving")}</InlineFeedback> : state.notice ?
    <div role={state.notice === "saved" ? "status" : "alert"}><InlineFeedback tone={state.notice === "saved" ? "success" : "error"}>{t(state.notice)}</InlineFeedback></div> : null}>
    <TextInput type="url" aria-label={t("baseUrl")} value={state.draft ?? data?.base_url ?? ""} placeholder="https://openrouter.ai/api/v1"
      onChange={event => autosave.edit(event.target.value)}
      onBlur={event => { if (!(event.relatedTarget instanceof Element && event.relatedTarget.closest('[data-base-url-action]'))) void autosave.commit(); }}
      onKeyDown={event => { if (event.key === "Enter" && !event.nativeEvent.isComposing) { event.preventDefault(); void autosave.commit(); } }} />
    {state.notice === "baseUrlSaveFailed" ? <Button data-base-url-action size="sm" className="mt-3" onClick={() => void autosave.commit()}>{t("retrySave")}</Button> : null}
  </SettingRow>;
}
