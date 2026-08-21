"use client";

import { useEffect } from "react";
import { ChevronDown } from "lucide-react";
import { useTranslations } from "next-intl";
import { usePathname, useRouter } from "@/i18n/routing";
import {
  SectionIntro,
  SettingRow,
  SettingsPanel,
} from "@/components/settings/SettingsPrimitives";
import { Button } from "@/components/ui/Button";
import { InlineFeedback, Spinner } from "@/components/ui/Feedback";
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
              <div className="flex border border-line-strong bg-surface-raised p-1">
                {(["zh", "en"] as const).map((language) => (
                  <Button
                    key={language}
                    onClick={() => handleLanguageChange(language)}
                    disabled={languageSaving}
                    size="sm"
                    variant={languageData?.language === language ? "primary" : "ghost"}
                    className="min-w-12"
                  >
                    {language}
                  </Button>
                ))}
              </div>
              {languageSaving && <Spinner className="text-ink-subtle" />}
            </div>
          }
          feedback={
            languageError ? (
              <InlineFeedback tone="error">{t("languageSaveFailed")}</InlineFeedback>
            ) : languageSaveResult ? (
              <InlineFeedback tone="success">{t("saved")}</InlineFeedback>
            ) : null
          }
        />
      </SettingsPanel>

      <details className="group border-b border-line pb-6">
        <summary className="focus-ring flex cursor-pointer list-none items-center justify-between gap-4 py-1">
          <span>
            <span className="block text-sm font-medium tracking-widest text-ink uppercase">
              {t("roadmap")}
            </span>
            <span className="mt-1 block text-xs leading-5 text-ink-disabled">{t("roadmapDesc")}</span>
          </span>
          <span className="flex shrink-0 items-center gap-3 text-[10px] font-bold tracking-[0.2em] text-ink-disabled uppercase group-open:text-ink-muted">
            <span className="hidden sm:inline">{t("comingSoon")}</span>
            <ChevronDown className="duration-standard h-4 w-4 transition-transform group-open:rotate-180" />
          </span>
        </summary>
        <div className="mt-6 space-y-6 border-t border-line pt-6">
          {roadmapItems.map(([title, description]) => (
            <div key={title} className="border-b border-line pb-6 last:border-b-0 last:pb-0">
              <p className="text-sm font-medium tracking-widest text-ink-muted uppercase">{title}</p>
              <p className="mt-2 text-xs leading-5 text-ink-disabled">{description}</p>
            </div>
          ))}
        </div>
      </details>
    </div>
  );
}
