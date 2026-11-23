"use client";

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
              <div
                role="group"
                aria-label={t("languagePref")}
                className="inline-flex h-7 items-stretch border border-line-strong bg-surface-raised"
              >
                {(
                  [
                    { value: "zh", label: "中文" },
                    { value: "en", label: "English" },
                  ] as const
                ).map((option) => {
                  const active = languageData?.language === option.value;
                  return (
                    <button
                      key={option.value}
                      type="button"
                      aria-pressed={active}
                      disabled={!languageData || languageSaving}
                      onClick={() => void handleLanguageChange(option.value)}
                      className={`focus-ring duration-standard inline-flex items-center px-3 text-xs font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
                        active
                          ? "bg-inverse text-inverse-ink"
                          : "text-ink-subtle hover:text-ink"
                      }`}
                    >
                      {option.label}
                    </button>
                  );
                })}
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
