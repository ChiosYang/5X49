"use client";

import { useEffect, useState, useSyncExternalStore } from "react";
import { useTranslations } from "next-intl";
import { useBaseUrl, writeBaseUrl } from "@/hooks/useSettings";
import { createBaseUrlAutosave, type BaseUrlSaveState } from "@/lib/settings-autosave";
import { SettingRow } from "./SettingsPrimitives";
import { Button } from "@/components/ui/Button";
import { InlineFeedback } from "@/components/ui/Feedback";
import { TextInput } from "@/components/ui/FormControls";
import { createAutosaveSessionRegistry } from "@/lib/settings-autosave-session";
import { mutate as updateCache } from "swr";
import { API } from "@/lib/api";

const sessions = createAutosaveSessionRegistry<string, Exclude<BaseUrlSaveState["notice"], "saved" | null>, { base_url: string }>();

export default function BaseUrlSetting() {
  const t = useTranslations("Settings");
  const { data } = useBaseUrl();
  const [autosave] = useState(() => sessions.get(() => ({ initial: data ?? null, value: result => result.base_url, create: createBaseUrlAutosave,
    write: async value => {
      const result = await writeBaseUrl(value);
      const saved = typeof result.base_url === "string" ? result.base_url : value;
      await updateCache(API.settingsBaseUrl(), { base_url: saved }, false);
      return { base_url: saved };
    },
  }), typeof window !== "undefined"));
  const state = useSyncExternalStore(autosave.subscribe, autosave.getSnapshot, autosave.getSnapshot);
  useEffect(() => { if (data) autosave.syncSaved(data); }, [autosave, data]);
  return <SettingRow title={t("baseUrl")} feedback={state.saving ? <InlineFeedback>{t("saving")}</InlineFeedback> : state.notice ?
    <div role={state.notice === "saved" ? "status" : "alert"}><InlineFeedback tone={state.notice === "saved" ? "success" : "error"}>{t(state.notice)}</InlineFeedback></div> : null}>
    <TextInput type="url" aria-label={t("baseUrl")} value={state.draft ?? state.result?.base_url ?? data?.base_url ?? ""} placeholder="https://openrouter.ai/api/v1"
      onChange={event => autosave.edit(event.target.value)}
      onBlur={event => { if (!(event.relatedTarget instanceof Element && event.relatedTarget.closest('[data-base-url-action]'))) void autosave.commit(); }}
      onKeyDown={event => { if (event.key === "Enter" && !event.nativeEvent.isComposing) { event.preventDefault(); void autosave.commit(); } }} />
    {state.notice === "baseUrlSaveFailed" ? <Button data-base-url-action size="sm" className="mt-3" onClick={() => void autosave.commit()}>{t("retrySave")}</Button> : null}
  </SettingRow>;
}
