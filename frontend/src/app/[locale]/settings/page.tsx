"use client";

import { Suspense } from "react";
import { useTranslations } from "next-intl";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import GeneralSettings from "./GeneralSettings";
import IntegrationSettings from "./IntegrationSettings";
import LibrarySettings from "./LibrarySettings";

const settingSections = ["general", "integrations", "library"] as const;
type SettingSection = (typeof settingSections)[number];

function isSettingSection(value: string | null): value is SettingSection {
  return settingSections.includes(value as SettingSection);
}

function SettingsContent() {
  const t = useTranslations("Settings");
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const requestedSection = searchParams.get("section");
  const activeSection: SettingSection = isSettingSection(requestedSection)
    ? requestedSection
    : "general";

  const labels: Record<SettingSection, string> = {
    general: t("general"),
    integrations: t("integrations"),
    library: t("librarySettings"),
  };

  const selectSection = (section: SettingSection) => {
    const params = new URLSearchParams(searchParams.toString());
    params.set("section", section);
    router.replace(`${pathname}?${params.toString()}`, { scroll: false });
  };

  return (
    <div className="min-h-screen bg-black px-5 pb-20 pt-28 text-white selection:bg-white selection:text-black sm:px-8 md:px-12 md:pt-32">
      <div className="mx-auto w-full max-w-7xl">
        <header className="border-b border-neutral-900 pb-8">
          <p className="text-xs font-bold uppercase tracking-[0.24em] text-neutral-600">
            {t("systemConfiguration")}
          </p>
          <div className="mt-4 flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <h1 className="font-serif text-5xl leading-none tracking-tighter md:text-7xl">
                {t("title")}
              </h1>
              <p className="mt-4 max-w-2xl text-sm leading-6 text-neutral-500">
                {t("subtitle")}
              </p>
            </div>
            <p className="max-w-sm text-xs leading-5 text-neutral-600 lg:text-right">
              {t("settingsHint")}
            </p>
          </div>
        </header>

        <div className="mt-8 grid gap-8 lg:grid-cols-[220px_minmax(0,1fr)] lg:gap-12">
          <aside className="min-w-0 overflow-hidden">
            <nav
              aria-label={t("settingsNavigation")}
              className="scrollbar-minimal flex w-full max-w-full gap-2 overflow-x-auto pb-2 lg:sticky lg:top-28 lg:flex-col lg:overflow-visible"
            >
              {settingSections.map((section, index) => (
                <button
                  key={section}
                  type="button"
                  onClick={() => selectSection(section)}
                  aria-current={activeSection === section ? "page" : undefined}
                  className={`flex min-w-max items-center gap-3 border px-4 py-3 text-left text-xs font-bold uppercase tracking-[0.16em] transition-colors lg:w-full ${
                    activeSection === section
                      ? "border-white bg-white text-black"
                      : "border-neutral-900 text-neutral-500 hover:border-neutral-700 hover:text-white"
                  }`}
                >
                  <span className="text-[10px] opacity-60">0{index + 1}</span>
                  {labels[section]}
                </button>
              ))}
            </nav>
          </aside>

          <section className="min-w-0 max-w-4xl">
            {activeSection === "general" && <GeneralSettings />}
            {activeSection === "integrations" && <IntegrationSettings />}
            {activeSection === "library" && <LibrarySettings />}
          </section>
        </div>
      </div>
    </div>
  );
}

function SettingsFallback() {
  return (
    <div className="min-h-screen bg-black px-5 pb-20 pt-28 text-white sm:px-8 md:px-12 md:pt-32">
      <div className="mx-auto max-w-7xl animate-pulse">
        <div className="h-20 border-b border-neutral-900" />
        <div className="mt-8 grid gap-8 lg:grid-cols-[220px_minmax(0,1fr)] lg:gap-12">
          <div className="h-36 bg-neutral-950" />
          <div className="h-96 border border-neutral-900 bg-neutral-950/40" />
        </div>
      </div>
    </div>
  );
}

export default function SettingsPage() {
  return (
    <Suspense fallback={<SettingsFallback />}>
      <SettingsContent />
    </Suspense>
  );
}
