"use client";

import { useEffect, useMemo, useState } from "react";
import { Search } from "lucide-react";
import { useTranslations } from "next-intl";
import {
  DisclosurePanel,
  SectionIntro,
  SettingRow,
  SettingsPanel,
} from "@/components/settings/SettingsPrimitives";
import { Button } from "@/components/ui/Button";
import { InlineFeedback } from "@/components/ui/Feedback";
import { InputButton, TextInput } from "@/components/ui/FormControls";
import {
  useBaseUrl,
  useModelSettings,
  useTestApiKey,
  useTestTmdbKey,
  useTmdbSettings,
  useUpdateBaseUrl,
  useUpdateModel,
  useUpdateTmdbKey,
} from "@/hooks/useSettings";

function isValidHttpUrl(value: string) {
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:";
  } catch {
    return false;
  }
}

export default function IntegrationSettings() {
  const t = useTranslations("Settings");
  const { data: modelData, mutate: refreshModels } = useModelSettings();
  const { data: baseUrlData, mutate: refreshBaseUrl } = useBaseUrl();
  const { data: tmdbData } = useTmdbSettings();

  const {
    trigger: updateModel,
    isMutating: modelSaving,
    data: modelSaveResult,
    error: modelSaveError,
    reset: resetModelSave,
  } = useUpdateModel();
  const {
    trigger: updateBaseUrl,
    isMutating: baseUrlSaving,
    data: baseUrlSaveResult,
    error: baseUrlSaveError,
    reset: resetBaseUrlSave,
  } = useUpdateBaseUrl();
  const {
    trigger: updateTmdbKey,
    isMutating: tmdbSaving,
    data: tmdbSaveResult,
    error: tmdbSaveError,
    reset: resetTmdbSave,
  } = useUpdateTmdbKey();
  const {
    trigger: testTmdbKey,
    data: tmdbTestResult,
    isMutating: tmdbTesting,
    error: tmdbTestError,
    reset: resetTmdbTest,
  } = useTestTmdbKey();
  const {
    trigger: testApi,
    data: apiTestResult,
    isMutating: apiTesting,
    error: apiTestError,
    reset: resetApiTest,
  } = useTestApiKey();

  const [modelMenuOpen, setModelMenuOpen] = useState(false);
  const [modelSearch, setModelSearch] = useState("");
  const [baseUrlDraft, setBaseUrlDraft] = useState<string>();
  const [tmdbKeyDraft, setTmdbKeyDraft] = useState("");
  const [tmdbKeyTouched, setTmdbKeyTouched] = useState(false);

  useEffect(() => {
    if (!modelSaveResult) return;
    const timer = window.setTimeout(() => resetModelSave(), 3000);
    return () => window.clearTimeout(timer);
  }, [modelSaveResult, resetModelSave]);

  useEffect(() => {
    if (!baseUrlSaveResult) return;
    const timer = window.setTimeout(() => resetBaseUrlSave(), 3000);
    return () => window.clearTimeout(timer);
  }, [baseUrlSaveResult, resetBaseUrlSave]);

  useEffect(() => {
    if (!tmdbSaveResult) return;
    const timer = window.setTimeout(() => resetTmdbSave(), 3000);
    return () => window.clearTimeout(timer);
  }, [tmdbSaveResult, resetTmdbSave]);

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

  const baseUrlValue = baseUrlDraft ?? baseUrlData?.base_url ?? "";
  const baseUrlDirty =
    baseUrlDraft !== undefined && baseUrlDraft.trim() !== (baseUrlData?.base_url ?? "");
  const baseUrlValid = isValidHttpUrl(baseUrlValue.trim());
  const tmdbStatus = tmdbSaveResult ?? tmdbData;
  const tmdbCanSave = tmdbStatus?.source !== "environment";
  const tmdbSourceLabel =
    tmdbStatus?.source === "environment"
      ? t("tmdbSourceEnvironment")
      : tmdbStatus?.source === "settings"
        ? t("tmdbSourceSettings")
        : t("tmdbSourceMissing");

  const handleModelChange = async (model: string) => {
    setModelMenuOpen(false);
    setModelSearch("");
    if (model === currentModel) return;
    try {
      await updateModel(model);
      await refreshModels();
    } catch {
      // Mutation state renders the localized error in the row.
    }
  };

  const handleBaseUrlSave = async () => {
    try {
      await updateBaseUrl(baseUrlValue.trim());
      await refreshBaseUrl();
      setBaseUrlDraft(undefined);
    } catch {
      // Mutation state renders the localized error in the row.
    }
  };

  const handleTmdbSave = async () => {
    try {
      await updateTmdbKey(tmdbKeyDraft.trim());
      setTmdbKeyDraft("");
      setTmdbKeyTouched(false);
    } catch {
      // Mutation state renders the localized error in the row.
    }
  };

  const handleApiTest = async () => {
    resetApiTest();
    try {
      await testApi();
    } catch {
      // Mutation state renders the localized error in the row.
    }
  };

  const handleTmdbTest = async () => {
    resetTmdbTest();
    try {
      await testTmdbKey();
    } catch {
      // Mutation state renders the localized error in the row.
    }
  };

  return (
    <div className="space-y-8">
      <SectionIntro
        eyebrow={t("integrationsEyebrow")}
        title={t("integrations")}
        description={t("integrationsDesc")}
      />

      <SettingsPanel title={t("aiProvider")} description={t("aiProviderDesc")}>
        <SettingRow
          title={t("model")}
          description={t("modelDesc")}
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
          <div className="relative max-w-xl">
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
                          className={`focus-ring duration-standard w-full px-4 py-3 text-left text-sm transition-colors hover:bg-surface-hover ${
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
        </SettingRow>

        <SettingRow
          title={t("apiKey")}
          description={t("apiDesc")}
          control={
            <Button
              onClick={handleApiTest}
              busy={apiTesting}
            >
              {apiTesting ? t("testingBtn") : t("testBtn")}
            </Button>
          }
          feedback={
            apiTesting ? (
              <InlineFeedback>{t("testingBtn")}</InlineFeedback>
            ) : apiTestError ? (
              <InlineFeedback tone="error">{t("apiTestFailed")}</InlineFeedback>
            ) : apiTestResult ? (
              <InlineFeedback tone={apiTestResult.status === "success" ? "success" : "error"}>
                {apiTestResult.message}
              </InlineFeedback>
            ) : null
          }
        />
      </SettingsPanel>

      <SettingsPanel title={t("tmdbIntegration")}>
        <SettingRow
          title={t("tmdbApiKey")}
          description={t("tmdbApiKeyDesc")}
          feedback={
            tmdbSaveError ? (
              <InlineFeedback tone="error">
                {tmdbSaveError instanceof Error ? tmdbSaveError.message : t("tmdbSaveFailed")}
              </InlineFeedback>
            ) : tmdbTestError ? (
              <InlineFeedback tone="error">
                {tmdbTestError instanceof Error ? tmdbTestError.message : t("tmdbTestFailed")}
              </InlineFeedback>
            ) : tmdbSaveResult ? (
              <InlineFeedback tone="success">{t("saved")}</InlineFeedback>
            ) : tmdbTestResult ? (
              <InlineFeedback tone={tmdbTestResult.status === "success" ? "success" : "error"}>
                {tmdbTestResult.message}
              </InlineFeedback>
            ) : null
          }
        >
          <div className="flex flex-col gap-3 lg:flex-row">
            <div className="relative min-w-0 flex-1">
              <TextInput
                type="password"
                value={tmdbKeyDraft}
                onChange={(event) => {
                  setTmdbKeyDraft(event.target.value);
                  setTmdbKeyTouched(true);
                }}
                disabled={!tmdbCanSave}
                aria-label={t("tmdbApiKey")}
                placeholder={tmdbCanSave ? t("tmdbApiKeyPlaceholder") : t("tmdbApiKeyEnvironment")}
                className="pr-28"
              />
              <span
                className={`pointer-events-none absolute top-1/2 right-3 -translate-y-1/2 text-[10px] font-bold tracking-widest uppercase ${
                  tmdbStatus?.configured ? "text-success" : "text-ink-disabled"
                }`}
              >
                {tmdbSourceLabel}
              </span>
            </div>
            <Button
              onClick={handleTmdbSave}
              disabled={!tmdbCanSave || !tmdbKeyTouched || tmdbSaving}
              busy={tmdbSaving}
              variant="primary"
            >
              {tmdbSaving ? t("saving") : t("save")}
            </Button>
            <Button
              onClick={handleTmdbTest}
              disabled={tmdbTesting || !tmdbStatus?.configured}
              busy={tmdbTesting}
            >
              {tmdbTesting ? t("testingBtn") : t("tmdbTestBtn")}
            </Button>
          </div>
        </SettingRow>
      </SettingsPanel>

      <DisclosurePanel
        title={t("advanced")}
        description={t("advancedIntegrationsDesc")}
        summary={baseUrlData?.base_url ?? t("notConfigured")}
      >
        <SettingRow
          title={t("baseUrl")}
          description={t("baseUrlDesc")}
          feedback={
            baseUrlSaveError ? (
              <InlineFeedback tone="error">{t("baseUrlSaveFailed")}</InlineFeedback>
            ) : baseUrlDraft !== undefined && !baseUrlValid ? (
              <InlineFeedback tone="warning">{t("invalidBaseUrl")}</InlineFeedback>
            ) : baseUrlSaveResult ? (
              <InlineFeedback tone="success">{t("saved")}</InlineFeedback>
            ) : null
          }
        >
          <div className="flex flex-col gap-3 sm:flex-row">
            <TextInput
              type="url"
              value={baseUrlValue}
              onChange={(event) => setBaseUrlDraft(event.target.value)}
              aria-label={t("baseUrl")}
              placeholder="https://openrouter.ai/api/v1"
            />
            <Button
              onClick={handleBaseUrlSave}
              disabled={!baseUrlDirty || !baseUrlValid || baseUrlSaving}
              busy={baseUrlSaving}
              variant="primary"
            >
              {baseUrlSaving ? t("saving") : t("save")}
            </Button>
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            {[
              ["OpenRouter", "https://openrouter.ai/api/v1"],
              ["OpenAI", "https://api.openai.com/v1"],
              ["Anthropic", "https://api.anthropic.com/v1"],
            ].map(([label, value]) => (
              <Button
                key={label}
                onClick={() => setBaseUrlDraft(value)}
                size="sm"
                variant="ghost"
                className="border border-line text-ink-subtle hover:border-line-strong"
              >
                {label}
              </Button>
            ))}
          </div>
        </SettingRow>
      </DisclosurePanel>
    </div>
  );
}
