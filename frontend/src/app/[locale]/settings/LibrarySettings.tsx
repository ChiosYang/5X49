"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import FileBrowser from "@/components/FileBrowser";
import {
  DisclosurePanel,
  InlineStatus,
  SectionIntro,
  SettingRow,
  SettingsPanel,
  ToggleSwitch,
} from "@/components/settings/SettingsPrimitives";
import {
  type ArtworkLanguage,
  useArtworkLanguageSetting,
  useAutoOrganizeRootSetting,
  useLibraryWatchSetting,
  useMediaDir,
  useScrapeConfirmationSetting,
  useUpdateArtworkLanguage,
  useUpdateAutoOrganizeRoot,
  useUpdateLibraryWatch,
  useUpdateMediaDir,
  useUpdateScrapeConfirmation,
} from "@/hooks/useSettings";

const inputClass =
  "focus-ring duration-standard min-h-11 w-full border border-line-strong bg-surface-raised px-4 text-sm text-ink placeholder:text-ink-disabled transition-colors hover:border-ink-disabled";
const primaryButtonClass =
  "focus-ring duration-fast min-h-11 shrink-0 bg-inverse px-5 text-xs font-bold tracking-[0.16em] text-inverse-ink uppercase transition-colors hover:bg-neutral-200 disabled:cursor-not-allowed disabled:opacity-40";
const secondaryButtonClass =
  "focus-ring duration-fast min-h-11 shrink-0 border border-line-strong bg-surface-raised px-5 text-xs font-bold tracking-[0.16em] text-ink uppercase transition-colors hover:border-ink-disabled hover:bg-surface-hover";

function useTransientMutationResult(result: unknown, reset: () => void) {
  useEffect(() => {
    if (!result) return;
    const timer = window.setTimeout(() => reset(), 3000);
    return () => window.clearTimeout(timer);
  }, [result, reset]);
}

export default function LibrarySettings() {
  const t = useTranslations("Settings");
  const { data: mediaDirData, mutate: refreshMediaDir } = useMediaDir();
  const { data: artworkLanguageData } = useArtworkLanguageSetting();
  const { data: libraryWatchData, mutate: refreshLibraryWatch } = useLibraryWatchSetting();
  const { data: autoOrganizeData, mutate: refreshAutoOrganize } = useAutoOrganizeRootSetting();
  const { data: scrapeConfirmationData, mutate: refreshScrapeConfirmation } =
    useScrapeConfirmationSetting();

  const {
    trigger: updateMediaDir,
    isMutating: mediaDirSaving,
    data: mediaDirSaveResult,
    error: mediaDirSaveError,
    reset: resetMediaDirSave,
  } = useUpdateMediaDir();
  const {
    trigger: updateArtworkLanguage,
    isMutating: artworkLanguageSaving,
    data: artworkLanguageSaveResult,
    error: artworkLanguageError,
    reset: resetArtworkLanguageSave,
  } = useUpdateArtworkLanguage();
  const {
    trigger: updateLibraryWatch,
    isMutating: watchSaving,
    data: watchSaveResult,
    error: watchError,
    reset: resetWatchSave,
  } = useUpdateLibraryWatch();
  const {
    trigger: updateAutoOrganize,
    isMutating: autoOrganizeSaving,
    data: autoOrganizeSaveResult,
    error: autoOrganizeError,
    reset: resetAutoOrganizeSave,
  } = useUpdateAutoOrganizeRoot();
  const {
    trigger: updateScrapeConfirmation,
    isMutating: scrapeConfirmationSaving,
    data: scrapeConfirmationSaveResult,
    error: scrapeConfirmationError,
    reset: resetScrapeConfirmationSave,
  } = useUpdateScrapeConfirmation();

  const [mediaDirDraft, setMediaDirDraft] = useState<string>();
  const [fileBrowserOpen, setFileBrowserOpen] = useState(false);

  useTransientMutationResult(mediaDirSaveResult, resetMediaDirSave);
  useTransientMutationResult(artworkLanguageSaveResult, resetArtworkLanguageSave);
  useTransientMutationResult(watchSaveResult, resetWatchSave);
  useTransientMutationResult(autoOrganizeSaveResult, resetAutoOrganizeSave);
  useTransientMutationResult(scrapeConfirmationSaveResult, resetScrapeConfirmationSave);

  const mediaDirValue = mediaDirDraft ?? mediaDirData?.media_dir ?? "";
  const mediaDirDirty =
    mediaDirDraft !== undefined && mediaDirDraft.trim() !== (mediaDirData?.media_dir ?? "");
  const artworkLanguageOptions: Array<{ value: ArtworkLanguage; label: string }> = [
    { value: "metadata", label: t("artworkLanguageMetadata") },
    { value: "zh", label: t("artworkLanguageZh") },
    { value: "en", label: t("artworkLanguageEn") },
    { value: "none", label: t("artworkLanguageNone") },
  ];

  const handleMediaDirSave = async () => {
    try {
      await updateMediaDir(mediaDirValue.trim());
      await refreshMediaDir();
      setMediaDirDraft(undefined);
    } catch {
      // Mutation state renders the localized error in the row.
    }
  };

  const handleArtworkLanguageChange = async (language: ArtworkLanguage) => {
    if (language === (artworkLanguageData?.artwork_language ?? "metadata")) return;
    try {
      await updateArtworkLanguage(language);
    } catch {
      // Mutation state renders the localized error in the row.
    }
  };

  const handleLibraryWatchChange = async () => {
    try {
      await updateLibraryWatch(!libraryWatchData?.watch_library);
      await refreshLibraryWatch();
    } catch {
      // Mutation state renders the localized error in the row.
    }
  };

  const handleAutoOrganizeChange = async () => {
    try {
      await updateAutoOrganize(!autoOrganizeData?.auto_organize_root_videos);
      await refreshAutoOrganize();
    } catch {
      // Mutation state renders the localized error in the row.
    }
  };

  const handleScrapeConfirmationChange = async () => {
    try {
      await updateScrapeConfirmation(!scrapeConfirmationData?.scrape_require_confirmation);
      await refreshScrapeConfirmation();
    } catch {
      // Mutation state renders the localized error in the row.
    }
  };

  const enabledLabel = (enabled: boolean | undefined) =>
    enabled ? t("enabled") : t("disabled");
  const advancedSummary = `${t("autoOrganizeRoot")}: ${enabledLabel(
    autoOrganizeData?.auto_organize_root_videos,
  )} · ${t("scrapeRequireConfirmation")}: ${enabledLabel(
    scrapeConfirmationData?.scrape_require_confirmation,
  )}`;

  return (
    <div className="space-y-8">
      <SectionIntro
        eyebrow={t("libraryEyebrow")}
        title={t("librarySettings")}
        description={t("librarySettingsDesc")}
      />

      <SettingsPanel title={t("librarySource")} description={t("librarySourceDesc")}>
        <SettingRow
          title={t("mediaDir")}
          description={t("mediaDirDesc")}
          feedback={
            mediaDirSaveError ? (
              <InlineStatus tone="error">{t("mediaDirSaveFailed")}</InlineStatus>
            ) : mediaDirSaveResult ? (
              <InlineStatus tone="success">{t("saved")}</InlineStatus>
            ) : (
              <InlineStatus>{t("noteRestart")}</InlineStatus>
            )
          }
        >
          <div className="flex flex-col gap-3 md:flex-row">
            <input
              type="text"
              value={mediaDirValue}
              onChange={(event) => setMediaDirDraft(event.target.value)}
              aria-label={t("mediaDir")}
              placeholder="/path/to/movies"
              className={inputClass}
            />
            <button
              type="button"
              onClick={() => setFileBrowserOpen(true)}
              className={secondaryButtonClass}
            >
              {t("browse")}
            </button>
            <button
              type="button"
              onClick={handleMediaDirSave}
              disabled={!mediaDirDirty || !mediaDirValue.trim() || mediaDirSaving}
              className={primaryButtonClass}
            >
              {mediaDirSaving ? t("saving") : t("save")}
            </button>
          </div>
          <p className="mt-3 text-xs leading-5 text-ink-disabled">{t("noteDocker")}</p>
        </SettingRow>
      </SettingsPanel>

      {fileBrowserOpen && (
        <FileBrowser
          isOpen={fileBrowserOpen}
          initialPath={mediaDirValue}
          onSelect={(path) => {
            setMediaDirDraft(path);
            setFileBrowserOpen(false);
          }}
          onCancel={() => setFileBrowserOpen(false)}
        />
      )}

      <SettingsPanel title={t("metadataPreferences")} description={t("metadataPreferencesDesc")}>
        <SettingRow
          title={t("artworkLanguage")}
          description={t("artworkLanguageDesc")}
          feedback={
            artworkLanguageError ? (
              <InlineStatus tone="error">{t("artworkLanguageSaveFailed")}</InlineStatus>
            ) : artworkLanguageSaveResult ? (
              <InlineStatus tone="success">{t("saved")}</InlineStatus>
            ) : null
          }
        >
          <div className="inline-flex max-w-full flex-wrap border border-line-strong bg-surface-raised p-1">
            {artworkLanguageOptions.map((option) => (
              <button
                key={option.value}
                type="button"
                onClick={() => handleArtworkLanguageChange(option.value)}
                disabled={artworkLanguageSaving}
                className={`focus-ring duration-standard px-3 py-2 text-xs font-bold tracking-widest uppercase transition-colors ${
                  (artworkLanguageData?.artwork_language ?? "metadata") === option.value
                    ? "bg-inverse text-inverse-ink"
                    : "text-ink-subtle hover:text-ink"
                } disabled:cursor-not-allowed disabled:opacity-50`}
              >
                {option.label}
              </button>
            ))}
          </div>
        </SettingRow>
      </SettingsPanel>

      <SettingsPanel title={t("automation")} description={t("automationDesc")}>
        <SettingRow
          title={t("autoScan")}
          description={t("autoScanDesc")}
          control={
            <ToggleSwitch
              checked={Boolean(libraryWatchData?.watch_library)}
              disabled={watchSaving}
              label={t("autoScan")}
              onChange={handleLibraryWatchChange}
            />
          }
          feedback={
            watchError ? (
              <InlineStatus tone="error">{t("autoScanSaveFailed")}</InlineStatus>
            ) : watchSaveResult ? (
              <InlineStatus tone="success">{t("saved")}</InlineStatus>
            ) : (
              <InlineStatus>
                {libraryWatchData?.watch_library ? t("watching") : t("notWatching")}
              </InlineStatus>
            )
          }
        />
      </SettingsPanel>

      <DisclosurePanel
        title={t("advanced")}
        description={t("advancedLibraryDesc")}
        summary={advancedSummary}
      >
        <SettingRow
          title={t("autoOrganizeRoot")}
          description={t("autoOrganizeRootDesc")}
          control={
            <ToggleSwitch
              checked={Boolean(autoOrganizeData?.auto_organize_root_videos)}
              disabled={autoOrganizeSaving}
              label={t("autoOrganizeRoot")}
              onChange={handleAutoOrganizeChange}
            />
          }
          feedback={
            autoOrganizeError ? (
              <InlineStatus tone="error">{t("autoOrganizeSaveFailed")}</InlineStatus>
            ) : autoOrganizeSaveResult ? (
              <InlineStatus tone="success">{t("saved")}</InlineStatus>
            ) : null
          }
        />
        <SettingRow
          title={t("scrapeRequireConfirmation")}
          description={t("scrapeRequireConfirmationDesc")}
          control={
            <ToggleSwitch
              checked={Boolean(scrapeConfirmationData?.scrape_require_confirmation)}
              disabled={scrapeConfirmationSaving}
              label={t("scrapeRequireConfirmation")}
              onChange={handleScrapeConfirmationChange}
            />
          }
          feedback={
            scrapeConfirmationError ? (
              <InlineStatus tone="error">{t("scrapeConfirmationSaveFailed")}</InlineStatus>
            ) : scrapeConfirmationSaveResult ? (
              <InlineStatus tone="success">{t("saved")}</InlineStatus>
            ) : null
          }
        />
      </DisclosurePanel>
    </div>
  );
}
