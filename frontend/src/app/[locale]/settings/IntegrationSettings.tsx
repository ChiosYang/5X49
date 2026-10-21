"use client";

import { useEffect, useMemo, useState } from "react";
import { PlugZap, Search } from "lucide-react";
import { useTranslations } from "next-intl";
import {
  SettingRow,
  SettingsPanel,
} from "@/components/settings/SettingsPrimitives";
import { IconButton } from "@/components/ui/Button";
import { InlineFeedback } from "@/components/ui/Feedback";
import { InputButton, TextInput } from "@/components/ui/FormControls";
import BaseUrlSetting from "@/components/settings/BaseUrlSetting";
import TmdbConnectionSetting from "@/components/settings/TmdbConnectionSetting";
import { ConnectionTestResult } from "@/components/settings/ConnectionTestResult";
import { useConnectionTest } from "@/hooks/useConnectionTest";
import { useBaseUrlAutosave } from "@/hooks/useBaseUrlAutosave";
import {
  useModelSettings,
  useTestApiKey,
  useUpdateModel,
} from "@/hooks/useSettings";

export default function IntegrationSettings() {
  const t = useTranslations("Settings");
  const { data: modelData, mutate: refreshModels } = useModelSettings();
  const baseUrl = useBaseUrlAutosave();

  const {
    trigger: updateModel,
    isMutating: modelSaving,
    data: modelSaveResult,
    error: modelSaveError,
    reset: resetModelSave,
  } = useUpdateModel();
  const { trigger: testApi } = useTestApiKey();
  const apiTest = useConnectionTest(() => testApi());

  const [modelMenuOpen, setModelMenuOpen] = useState(false);
  const [modelSearch, setModelSearch] = useState("");

  useEffect(() => {
    if (!modelSaveResult) return;
    const timer = window.setTimeout(() => resetModelSave(), 3000);
    return () => window.clearTimeout(timer);
  }, [modelSaveResult, resetModelSave]);


  const currentModel = modelData?.current_model ?? "";
  const availableModels = useMemo(
    () => modelData?.available_models ?? [],
    [modelData?.available_models],
  );
  const filteredModels = useMemo(() => {
    const query = modelSearch.trim().toLowerCase();
    if (!query) return availableModels;
    return availableModels.filter((model) => model.toLowerCase().includes(query));
  }, [availableModels, modelSearch]);

  const handleModelChange = async (model: string) => {
    setModelMenuOpen(false);
    setModelSearch("");
    if (model === currentModel) return;
    apiTest.invalidate();
    try {
      await updateModel(model);
      await refreshModels();
    } catch {
      // Mutation state renders the localized error in the row.
    }
  };

  const handleApiTest = () => {
    const current = baseUrl.autosave.getSnapshot();
    if (current.saving || current.draft !== null || modelSaving || !modelData) return;
    void apiTest.run();
  };

  return (
    <div className="space-y-8">
      <SettingsPanel title={t("aiProvider")}>
        <SettingRow
          title={t("model")}
          feedback={
            modelSaving ? (
              <InlineFeedback>{t("saving")}</InlineFeedback>
            ) : modelSaveError ? (
              <InlineFeedback tone="error">{t("modelSaveFailed")}</InlineFeedback>
            ) : modelSaveResult ? (
              <InlineFeedback tone="success">{t("saved")}</InlineFeedback>
            ) : null
          }
        >
          <div role="group" aria-label={t("model")} className="flex min-w-0 max-w-xl items-start gap-2">
          <div className="relative min-w-0 flex-1">
            <InputButton
              aria-expanded={modelMenuOpen}
              onClick={() => setModelMenuOpen((open) => !open)}
              disabled={modelSaving}
              className="flex items-center justify-between gap-4 text-left"
            >
              <span className="truncate">{currentModel || t("selectModel")}</span>
              <span className="text-ink-subtle">▾</span>
            </InputButton>
            {modelMenuOpen && (
              <>
                <button
                  type="button"
                  aria-label={t("closeModelMenu")}
                  className="z-overlay fixed inset-0 cursor-default"
                  onClick={() => setModelMenuOpen(false)}
                />
                <div className="liquid-glass-popover z-popover absolute mt-2 flex max-h-72 w-full flex-col border border-line/80">
                  <div className="relative border-b border-line-strong p-2">
                    <Search className="pointer-events-none absolute top-1/2 left-5 h-3.5 w-3.5 -translate-y-1/2 text-ink-disabled" />
                    <TextInput
                      type="search"
                      value={modelSearch}
                      onChange={(event) => setModelSearch(event.target.value)}
                      placeholder={t("searchModels")}
                      aria-label={t("searchModels")}
                      className="min-h-0 border-0 bg-surface py-2 pr-3 pl-9 text-xs hover:border-0"
                      autoFocus
                    />
                  </div>
                  <div className="scrollbar-minimal overflow-y-auto">
                    {filteredModels.length > 0 ? (
                      filteredModels.map((model) => (
                        <button
                          key={model}
                          type="button"
                          onClick={() => handleModelChange(model)}
                          className={`focus-ring duration-standard w-full break-words px-4 py-3 text-left text-sm transition-colors hover:bg-surface-hover ${
                            currentModel === model ? "bg-inverse font-medium text-inverse-ink" : "text-ink"
                          }`}
                        >
                          {model}
                        </button>
                      ))
                    ) : (
                      <p className="px-4 py-8 text-center text-sm text-ink-disabled">{t("noModelsFound")}</p>
                    )}
                  </div>
                </div>
              </>
            )}
          </div>
          <span className="group/api-test relative inline-flex shrink-0">
            <IconButton variant="ghost" aria-label={t("testConnection")} aria-describedby="api-test-tooltip" busy={apiTest.busy} disabled={modelSaving || !modelData || !baseUrl.data || baseUrl.state.saving || baseUrl.state.draft !== null} onClick={handleApiTest} icon={<PlugZap aria-hidden className="h-4 w-4" />} />
            <span id="api-test-tooltip" role="tooltip" className="pointer-events-none invisible absolute right-0 top-full z-20 mt-2 w-max max-w-56 border border-line-strong bg-surface-raised px-3 py-2 text-xs group-hover/api-test:visible group-focus-within/api-test:visible">{t("testConnection")}</span>
          </span>
          <ConnectionTestResult outcome={apiTest.outcome} />
          </div>

        </SettingRow>

        <BaseUrlSetting onEdit={apiTest.invalidate} />
      </SettingsPanel>

      <SettingsPanel title={t("tmdbIntegration")}>
        <TmdbConnectionSetting />
      </SettingsPanel>


    </div>
  );
}
