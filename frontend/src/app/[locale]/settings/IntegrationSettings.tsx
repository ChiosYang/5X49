"use client";

import { useEffect, useMemo, useState } from "react";
import { Search } from "lucide-react";
import { useTranslations } from "next-intl";
import {
  DisclosurePanel,
  InlineStatus,
  SectionIntro,
  SettingRow,
  SettingsPanel,
} from "@/components/settings/SettingsPrimitives";
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

const inputClass =
  "focus-ring duration-standard min-h-11 w-full border border-line-strong bg-surface-raised px-4 text-sm text-ink placeholder:text-ink-disabled transition-colors hover:border-ink-disabled disabled:cursor-not-allowed disabled:opacity-50";
const primaryButtonClass =
  "focus-ring duration-fast min-h-11 shrink-0 bg-inverse px-5 text-xs font-bold tracking-[0.16em] text-inverse-ink uppercase transition-colors hover:bg-neutral-200 disabled:cursor-not-allowed disabled:opacity-40";
const secondaryButtonClass =
  "focus-ring duration-fast min-h-11 shrink-0 border border-line-strong bg-surface-raised px-5 text-xs font-bold tracking-[0.16em] text-ink uppercase transition-colors hover:border-ink-disabled hover:bg-surface-hover disabled:cursor-not-allowed disabled:opacity-40";

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
              <InlineStatus>{t("saving")}</InlineStatus>
            ) : modelSaveError ? (
              <InlineStatus tone="error">{t("modelSaveFailed")}</InlineStatus>
            ) : modelSaveResult ? (
              <InlineStatus tone="success">{t("saved")}</InlineStatus>
            ) : null
          }
        >
          <div className="relative max-w-xl">
            <button
              type="button"
              aria-expanded={modelMenuOpen}
              onClick={() => setModelMenuOpen((open) => !open)}
              disabled={modelSaving}
              className={`${inputClass} flex items-center justify-between gap-4 text-left`}
            >
              <span className="truncate">{currentModel || t("selectModel")}</span>
              <span className="text-ink-subtle">▾</span>
            </button>
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
                    <input
                      type="search"
                      value={modelSearch}
                      onChange={(event) => setModelSearch(event.target.value)}
                      placeholder={t("searchModels")}
                      aria-label={t("searchModels")}
                      className="focus-ring w-full bg-surface py-2 pr-3 pl-9 text-xs text-ink placeholder:text-ink-disabled"
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
            <button
              type="button"
              onClick={handleApiTest}
              disabled={apiTesting}
              className={secondaryButtonClass}
            >
              {apiTesting ? t("testingBtn") : t("testBtn")}
            </button>
          }
          feedback={
            apiTesting ? (
              <InlineStatus>{t("testingBtn")}</InlineStatus>
            ) : apiTestError ? (
              <InlineStatus tone="error">{t("apiTestFailed")}</InlineStatus>
            ) : apiTestResult ? (
              <InlineStatus tone={apiTestResult.status === "success" ? "success" : "error"}>
                {apiTestResult.message}
              </InlineStatus>
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
              <InlineStatus tone="error">
                {tmdbSaveError instanceof Error ? tmdbSaveError.message : t("tmdbSaveFailed")}
              </InlineStatus>
            ) : tmdbTestError ? (
              <InlineStatus tone="error">
                {tmdbTestError instanceof Error ? tmdbTestError.message : t("tmdbTestFailed")}
              </InlineStatus>
            ) : tmdbSaveResult ? (
              <InlineStatus tone="success">{t("saved")}</InlineStatus>
            ) : tmdbTestResult ? (
              <InlineStatus tone={tmdbTestResult.status === "success" ? "success" : "error"}>
                {tmdbTestResult.message}
              </InlineStatus>
            ) : null
          }
        >
          <div className="flex flex-col gap-3 lg:flex-row">
            <div className="relative min-w-0 flex-1">
              <input
                type="password"
                value={tmdbKeyDraft}
                onChange={(event) => {
                  setTmdbKeyDraft(event.target.value);
                  setTmdbKeyTouched(true);
                }}
                disabled={!tmdbCanSave}
                aria-label={t("tmdbApiKey")}
                placeholder={tmdbCanSave ? t("tmdbApiKeyPlaceholder") : t("tmdbApiKeyEnvironment")}
                className={`${inputClass} pr-28`}
              />
              <span
                className={`pointer-events-none absolute top-1/2 right-3 -translate-y-1/2 text-[10px] font-bold tracking-widest uppercase ${
                  tmdbStatus?.configured ? "text-success" : "text-ink-disabled"
                }`}
              >
                {tmdbSourceLabel}
              </span>
            </div>
            <button
              type="button"
              onClick={handleTmdbSave}
              disabled={!tmdbCanSave || !tmdbKeyTouched || tmdbSaving}
              className={primaryButtonClass}
            >
              {tmdbSaving ? t("saving") : t("save")}
            </button>
            <button
              type="button"
              onClick={handleTmdbTest}
              disabled={tmdbTesting || !tmdbStatus?.configured}
              className={secondaryButtonClass}
            >
              {tmdbTesting ? t("testingBtn") : t("tmdbTestBtn")}
            </button>
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
              <InlineStatus tone="error">{t("baseUrlSaveFailed")}</InlineStatus>
            ) : baseUrlDraft !== undefined && !baseUrlValid ? (
              <InlineStatus tone="warning">{t("invalidBaseUrl")}</InlineStatus>
            ) : baseUrlSaveResult ? (
              <InlineStatus tone="success">{t("saved")}</InlineStatus>
            ) : null
          }
        >
          <div className="flex flex-col gap-3 sm:flex-row">
            <input
              type="url"
              value={baseUrlValue}
              onChange={(event) => setBaseUrlDraft(event.target.value)}
              aria-label={t("baseUrl")}
              placeholder="https://openrouter.ai/api/v1"
              className={inputClass}
            />
            <button
              type="button"
              onClick={handleBaseUrlSave}
              disabled={!baseUrlDirty || !baseUrlValid || baseUrlSaving}
              className={primaryButtonClass}
            >
              {baseUrlSaving ? t("saving") : t("save")}
            </button>
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            {[
              ["OpenRouter", "https://openrouter.ai/api/v1"],
              ["OpenAI", "https://api.openai.com/v1"],
              ["Anthropic", "https://api.anthropic.com/v1"],
            ].map(([label, value]) => (
              <button
                key={label}
                type="button"
                onClick={() => setBaseUrlDraft(value)}
                className="focus-ring duration-standard border border-line px-3 py-2 text-[11px] text-ink-subtle transition-colors hover:border-line-strong hover:text-ink"
              >
                {label}
              </button>
            ))}
          </div>
        </SettingRow>
      </DisclosurePanel>
    </div>
  );
}
