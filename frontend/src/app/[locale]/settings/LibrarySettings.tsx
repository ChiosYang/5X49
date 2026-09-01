"use client";

import { ArrowUpRight } from "lucide-react";
import { useEffect } from "react";
import { useTranslations } from "next-intl";
import MediaDirectoryControl from "@/components/settings/MediaDirectoryControl";
import {
  DisclosurePanel,
  SectionIntro,
  SettingRow,
  SettingsPanel,
} from "@/components/settings/SettingsPrimitives";
import { InlineFeedback } from "@/components/ui/Feedback";
import { ToggleSwitch } from "@/components/ui/FormControls";
import { Link } from "@/i18n/routing";
import {
  type ArtworkLanguage,
  useArtworkLanguageSetting,
  useAutoOrganizeRootSetting,
  useLibraryWatchSetting,
  useScrapeConfirmationSetting,
  useUpdateArtworkLanguage,
  useUpdateAutoOrganizeRoot,
  useUpdateLibraryWatch,
  useUpdateScrapeConfirmation,
} from "@/hooks/useSettings";
import LibraryDangerZone from "./LibraryDangerZone";

function useTransientMutationResult(result: unknown, reset: () => void) {
  useEffect(() => {
    if (!result) return;
    const timer = window.setTimeout(() => reset(), 3000);
    return () => window.clearTimeout(timer);
  }, [result, reset]);
}

export default function LibrarySettings() {
  const t = useTranslations("Settings");
  const { data: artworkLanguageData } = useArtworkLanguageSetting();
  const { data: libraryWatchData, mutate: refreshLibraryWatch } = useLibraryWatchSetting();
  const { data: autoOrganizeData, mutate: refreshAutoOrganize } = useAutoOrganizeRootSetting();
  const { data: scrapeConfirmationData, mutate: refreshScrapeConfirmation } =
    useScrapeConfirmationSetting();

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

  useTransientMutationResult(artworkLanguageSaveResult, resetArtworkLanguageSave);
  useTransientMutationResult(watchSaveResult, resetWatchSave);
  useTransientMutationResult(autoOrganizeSaveResult, resetAutoOrganizeSave);
  useTransientMutationResult(scrapeConfirmationSaveResult, resetScrapeConfirmationSave);

  const artworkLanguageOptions: Array<{ value: ArtworkLanguage; label: string }> = [
    { value: "metadata", label: t("artworkLanguageMetadata") },
    { value: "zh", label: t("artworkLanguageZh") },
    { value: "en", label: t("artworkLanguageEn") },
    { value: "none", label: t("artworkLanguageNone") },
  ];

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
        >
          <MediaDirectoryControl showDockerNote />
        </SettingRow>
      </SettingsPanel>

      <SettingsPanel title={t("metadataPreferences")} description={t("metadataPreferencesDesc")}>
        <SettingRow
          title={t("artworkLanguage")}
          description={t("artworkLanguageDesc")}
          feedback={
            artworkLanguageError ? (
              <InlineFeedback tone="error">{t("artworkLanguageSaveFailed")}</InlineFeedback>
            ) : artworkLanguageSaveResult ? (
              <InlineFeedback tone="success">{t("saved")}</InlineFeedback>
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
              <InlineFeedback tone="error">{t("autoScanSaveFailed")}</InlineFeedback>
            ) : watchSaveResult ? (
              <InlineFeedback tone="success">{t("saved")}</InlineFeedback>
            ) : (
              <InlineFeedback>
                {libraryWatchData?.watch_library ? t("watching") : t("notWatching")}
              </InlineFeedback>
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
              <InlineFeedback tone="error">{t("autoOrganizeSaveFailed")}</InlineFeedback>
            ) : autoOrganizeSaveResult ? (
              <InlineFeedback tone="success">{t("saved")}</InlineFeedback>
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
              <InlineFeedback tone="error">{t("scrapeConfirmationSaveFailed")}</InlineFeedback>
            ) : scrapeConfirmationSaveResult ? (
              <InlineFeedback tone="success">{t("saved")}</InlineFeedback>
            ) : null
          }
        />
        <SettingRow
          title={t("librarySystemStatus")}
          description={t("librarySystemStatusDesc")}
        >
          <Link
            href="/library/manage"
            className="focus-ring inline-flex min-h-10 items-center gap-2 border border-line-strong px-4 type-label text-ink-muted hover:border-ink-disabled hover:text-ink"
          >
            {t("openLibrarySystemStatus")}
            <ArrowUpRight className="h-3.5 w-3.5" />
          </Link>
        </SettingRow>
      </DisclosurePanel>

      <LibraryDangerZone />
    </div>
  );
}
