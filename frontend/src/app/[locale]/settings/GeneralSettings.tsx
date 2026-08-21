"use client";

import { useEffect } from "react";
import { ChevronDown, Loader2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { usePathname, useRouter } from "@/i18n/routing";
import {
  InlineStatus,
  SectionIntro,
  SettingRow,
  SettingsPanel,
} from "@/components/settings/SettingsPrimitives";
import { useLanguageSetting, useUpdateLanguage } from "@/hooks/useSettings";

export default function GeneralSettings() {
  const t = useTranslations("Settings");
  const router = useRouter();
  const pathname = usePathname();
  const { data: languageData } = useLanguageSetting();
  const {
    trigger: updateLanguage,
    isMutating: languageSaving,
    data: languageSaveResult,
    error: languageError,
    reset: resetLanguageSave,
  } = useUpdateLanguage();

  useEffect(() => {
    if (!languageSaveResult) return;
    const timer = window.setTimeout(() => resetLanguageSave(), 3000);
    return () => window.clearTimeout(timer);
  }, [languageSaveResult, resetLanguageSave]);

  const handleLanguageChange = async (language: "zh" | "en") => {
    if (language === languageData?.language) return;
    try {
      await updateLanguage(language);
      router.replace({ pathname }, { locale: language });
    } catch {
      // Mutation state renders the localized error in the row.
    }
  };

  const roadmapItems = [
    [t("roadmapAnimations"), t("roadmapAnimationsDesc")],
    [t("roadmapCompactMode"), t("roadmapCompactModeDesc")],
    [t("roadmapDefaultSort"), t("roadmapDefaultSortDesc")],
    [t("roadmapPosterQuality"), t("roadmapPosterQualityDesc")],
    [t("autoAnalyze"), t("autoAnalyzeDesc")],
  ];

  return (
    <div className="space-y-8">
      <SectionIntro
        eyebrow={t("generalEyebrow")}
        title={t("general")}
        description={t("generalDesc")}
      />

      <SettingsPanel title={t("preferences")}>
        <SettingRow
          title={t("languagePref")}
          description={t("languageDesc")}
          control={
            <div className="flex items-center gap-3">
              <div className="flex border border-neutral-800 bg-neutral-900 p-1">
                {(["zh", "en"] as const).map((language) => (
                  <button
                    key={language}
                    type="button"
                    onClick={() => handleLanguageChange(language)}
                    disabled={languageSaving}
                    className={`min-w-12 px-3 py-2 text-xs font-bold uppercase tracking-widest transition-colors ${
                      languageData?.language === language
                        ? "bg-white text-black"
                        : "text-neutral-500 hover:text-white"
                    } disabled:cursor-not-allowed disabled:opacity-50`}
                  >
                    {language}
                  </button>
                ))}
              </div>
              {languageSaving && <Loader2 className="h-4 w-4 animate-spin text-neutral-500" />}
            </div>
          }
          feedback={
            languageError ? (
              <InlineStatus tone="error">{t("languageSaveFailed")}</InlineStatus>
            ) : languageSaveResult ? (
              <InlineStatus tone="success">{t("saved")}</InlineStatus>
            ) : null
          }
        />
      </SettingsPanel>

      <details className="group border border-neutral-900 bg-neutral-950/30">
        <summary className="flex cursor-pointer list-none items-center justify-between gap-4 px-5 py-5 sm:px-6">
          <span>
            <span className="block text-sm font-semibold text-neutral-100">{t("roadmap")}</span>
            <span className="mt-1 block text-xs leading-5 text-neutral-600">{t("roadmapDesc")}</span>
          </span>
          <span className="flex shrink-0 items-center gap-3 text-[10px] font-bold uppercase tracking-[0.2em] text-neutral-600 group-open:text-neutral-400">
            <span className="hidden sm:inline">{t("comingSoon")}</span>
            <ChevronDown className="h-4 w-4 transition-transform group-open:rotate-180" />
          </span>
        </summary>
        <div className="grid gap-px border-t border-neutral-900 bg-neutral-900 sm:grid-cols-2">
          {roadmapItems.map(([title, description]) => (
            <div key={title} className="bg-black px-5 py-5 sm:px-6">
              <p className="text-sm font-semibold text-neutral-300">{title}</p>
              <p className="mt-2 text-xs leading-5 text-neutral-600">{description}</p>
            </div>
          ))}
        </div>
      </details>
    </div>
  );
}
