"use client";

import { useEffect } from "react";
import { useTranslations } from "next-intl";
import { useSearchParams } from "next/navigation";
import { usePathname, useRouter } from "@/i18n/routing";
import {
  SettingRow,
} from "@/components/settings/SettingsPrimitives";
import { InlineFeedback, Spinner } from "@/components/ui/Feedback";
import { useLanguageSetting, useUpdateLanguage } from "@/hooks/useSettings";

export default function GeneralSettings() {
  const t = useTranslations("Settings");
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { data: languageData, mutate: cacheLanguage } = useLanguageSetting();
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
      await cacheLanguage({ language }, false);
      router.replace(`${pathname}${searchParams.size ? `?${searchParams.toString()}` : ""}${window.location.hash}`, { locale: language });
    } catch {
      // Mutation state renders the localized error in the row.
    }
  };

  return (
    <div className="space-y-8">
        <SettingRow
          title={t("languagePref")}
          control={
            <div className="flex items-center gap-3">
              <div role="group" aria-label={t("languagePref")} className="inline-flex h-7 items-center border border-line-strong bg-surface-raised p-0.5">
                {(["zh", "en"] as const).map((language) => (
                  <button
                    key={language}
                    type="button"
                    aria-pressed={languageData?.language === language}
                    onClick={() => handleLanguageChange(language)}
                    disabled={languageSaving}
                    className={`focus-ring duration-standard h-5 min-w-8 px-2 text-xs font-medium uppercase transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${languageData?.language === language ? "bg-inverse text-inverse-ink" : "text-ink-subtle hover:text-ink"}`}
                  >
                    {language}
                  </button>
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
    </div>
  );
}
