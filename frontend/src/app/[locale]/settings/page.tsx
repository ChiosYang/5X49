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
    <div className="min-h-screen bg-canvas text-ink selection:bg-inverse selection:text-inverse-ink">
      <header className="page-x border-b border-line py-16 pt-28 md:py-24 md:pt-32">
        <h1 className="type-display-ui mb-4">
          {t("title")}
        </h1>
        <p className="max-w-2xl text-sm tracking-widest text-ink-subtle uppercase">
          {t("subtitle")}
        </p>
      </header>

      <div className="flex min-h-[60vh] flex-col md:flex-row">
        <aside className="w-full min-w-0 overflow-hidden border-b border-line bg-canvas md:w-64 md:shrink-0 md:border-r md:border-b-0">
          <nav
            aria-label={t("settingsNavigation")}
            className="scrollbar-minimal z-sticky flex w-full max-w-full gap-2 overflow-x-auto p-6 sm:p-8 md:sticky md:top-24 md:flex-col md:overflow-visible md:p-12"
          >
            {settingSections.map((section) => (
              <button
                key={section}
                type="button"
                onClick={() => selectSection(section)}
                aria-current={activeSection === section ? "page" : undefined}
                className={`focus-ring duration-standard block min-w-max px-4 py-3 text-left text-sm font-medium tracking-widest uppercase transition-colors md:w-full ${
                  activeSection === section
                    ? "bg-inverse text-inverse-ink"
                    : "text-ink-subtle hover:bg-surface-raised hover:text-ink"
                }`}
              >
                {labels[section]}
              </button>
            ))}
          </nav>
        </aside>

        <section className="page-x min-w-0 flex-1 py-6 sm:py-8 md:py-12 lg:py-16">
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
    <div className="min-h-screen animate-pulse bg-canvas text-ink">
      <div className="page-x h-64 border-b border-line py-24" />
      <div className="flex min-h-[60vh] flex-col md:flex-row">
        <div className="h-28 border-b border-line md:h-auto md:w-64 md:border-r md:border-b-0" />
        <div className="flex-1 p-8 md:p-16">
          <div className="h-96 max-w-3xl border-b border-line" />
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
