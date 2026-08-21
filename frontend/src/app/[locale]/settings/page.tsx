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
    <div className="min-h-screen bg-black text-white selection:bg-white selection:text-black">
      <header className="border-b border-neutral-900 px-6 py-16 pt-28 sm:px-8 md:px-16 md:py-24 md:pt-32">
        <h1 className="mb-4 text-5xl font-bold uppercase tracking-tight md:text-7xl">
          {t("title")}
        </h1>
        <p className="max-w-2xl text-sm uppercase tracking-widest text-neutral-500">
          {t("subtitle")}
        </p>
      </header>

      <div className="flex min-h-[60vh] flex-col md:flex-row">
        <aside className="w-full min-w-0 overflow-hidden border-b border-neutral-900 bg-black md:w-64 md:shrink-0 md:border-b-0 md:border-r">
          <nav
            aria-label={t("settingsNavigation")}
            className="scrollbar-minimal flex w-full max-w-full gap-2 overflow-x-auto p-6 sm:p-8 md:sticky md:top-24 md:flex-col md:overflow-visible md:p-12"
          >
            {settingSections.map((section) => (
              <button
                key={section}
                type="button"
                onClick={() => selectSection(section)}
                aria-current={activeSection === section ? "page" : undefined}
                className={`block min-w-max px-4 py-3 text-left text-sm font-medium uppercase tracking-widest transition-colors md:w-full ${
                  activeSection === section
                    ? "bg-white text-black"
                    : "text-neutral-500 hover:bg-neutral-900 hover:text-white"
                }`}
              >
                {labels[section]}
              </button>
            ))}
          </nav>
        </aside>

        <section className="min-w-0 flex-1 p-6 sm:p-8 md:p-12 lg:p-16">
          <div className="max-w-3xl">
            {activeSection === "general" && <GeneralSettings />}
            {activeSection === "integrations" && <IntegrationSettings />}
            {activeSection === "library" && <LibrarySettings />}
          </div>
        </section>
      </div>
    </div>
  );
}

function SettingsFallback() {
  return (
    <div className="min-h-screen animate-pulse bg-black text-white">
      <div className="h-64 border-b border-neutral-900 px-8 py-24 md:px-16" />
      <div className="flex min-h-[60vh] flex-col md:flex-row">
        <div className="h-28 border-b border-neutral-900 md:h-auto md:w-64 md:border-b-0 md:border-r" />
        <div className="flex-1 p-8 md:p-16">
          <div className="h-96 max-w-3xl border-b border-neutral-900" />
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
