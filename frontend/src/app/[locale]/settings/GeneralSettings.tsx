"use client";

import { useTranslations } from "next-intl";
import { useSearchParams } from "next/navigation";
import { usePathname, useRouter } from "@/i18n/routing";
import {
  SettingRow,
} from "@/components/settings/SettingsPrimitives";
import { InlineFeedback, Spinner } from "@/components/ui/Feedback";
import { ToggleSwitch } from "@/components/ui/FormControls";
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
    error: languageError,
  } = useUpdateLanguage();

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
            <div className="inline-flex h-7 items-center gap-3" aria-busy={languageSaving || undefined}>
              <span className="inline-flex h-4 w-4 shrink-0" aria-live="polite">
                {languageSaving ? <><Spinner className="text-ink-subtle" /><span className="sr-only">{t("saving")}</span></> : null}
              </span>
              <div role="group" aria-label={t("languagePref")} className="inline-flex h-7 items-center gap-2">
                <span aria-hidden className={`text-xs ${languageData?.language === "zh" ? "font-semibold text-ink" : "text-ink-disabled"}`}>中</span>
                <ToggleSwitch checked={languageData?.language === "en"} disabled={!languageData || languageSaving}
                  label={t("languageCurrent", { language: languageData?.language === "en" ? "English" : "中文" })}
                  onChange={() => void handleLanguageChange(languageData?.language === "en" ? "zh" : "en")} />
                <span aria-hidden className={`text-xs ${languageData?.language === "en" ? "font-semibold text-ink" : "text-ink-disabled"}`}>EN</span>
              </div>
            </div>
          }
          feedback={
            languageError ? (
              <InlineFeedback tone="error">{t("languageSaveFailed")}</InlineFeedback>
            ) : null
          }
        />
    </div>
  );
}
