"use client";

import { Suspense, useEffect, useId, useRef, useState, type MouseEvent } from "react";
import { ChevronDown } from "lucide-react";
import { useTranslations } from "next-intl";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Link } from "@/i18n/routing";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { canonicalSettingsHref, resolveSettingsLocation, settingSections, settingsHref, type SettingSection } from "@/lib/settings-navigation";
import GeneralSettings from "./GeneralSettings";
import IntegrationSettings from "./IntegrationSettings";
import LibrarySettings from "./LibrarySettings";
import LibraryMaintenanceSettings from "./LibraryMaintenanceSettings";
import VideoCheckSettings from "./VideoCheckSettings";
import DiagnosticsSettings from "./DiagnosticsSettings";
import BackupSettings from "./BackupSettings";
import LibraryDangerZone from "./LibraryDangerZone";

function CategoryContent({ section }: { section: SettingSection }) {
  switch (section) {
    case "general": return <GeneralSettings />;
    case "library": return <LibrarySettings />;
    case "connections": return <IntegrationSettings />;
    case "library-maintenance": return <LibraryMaintenanceSettings />;
    case "video-checks": return <VideoCheckSettings />;
    case "diagnostics": return <DiagnosticsSettings />;
    case "backup": return <BackupSettings />;
    case "cleanup": return <LibraryDangerZone />;
  }
}

function SettingsContent() {
  const t = useTranslations("Settings");
  const area = useTranslations("SettingsArea");
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const activeSection = resolveSettingsLocation(searchParams.get("section")).section;
  const [visited, setVisited] = useState<SettingSection[]>([activeSection]);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuId = useId();
  const focusSection = useRef<SettingSection | null>(null);
  // Keep visited controls mounted so category history does not discard local drafts.
  if (!visited.includes(activeSection)) setVisited([...visited, activeSection]);

  useEffect(() => {
    const normalize = () => {
      const destination = canonicalSettingsHref(searchParams.toString(), window.location.hash);
      const suffix = destination.slice("/settings".length);
      const current = `${searchParams.size ? `?${searchParams.toString()}` : ""}${window.location.hash}`;
      if (suffix !== current) router.replace(`${pathname}${suffix}`, { scroll: false });
    };
    normalize();
    window.addEventListener("hashchange", normalize);
    return () => window.removeEventListener("hashchange", normalize);
  }, [pathname, router, searchParams]);

  useEffect(() => {
    if (focusSection.current !== activeSection) return;
    const frame = requestAnimationFrame(() => {
      document.getElementById(`settings-title-${activeSection}`)?.focus({ preventScroll: true });
      focusSection.current = null;
    });
    return () => cancelAnimationFrame(frame);
  }, [activeSection]);

  const selectSection = (event: MouseEvent<HTMLAnchorElement>, section: SettingSection) => {
    setMenuOpen(false);
    if (section === activeSection) {
      event.preventDefault();
      requestAnimationFrame(() => document.getElementById(`settings-title-${section}`)?.focus({ preventScroll: true }));
    } else focusSection.current = section;
  };
  const navigation = settingSections.map(section => (
    <Link key={section} href={settingsHref(section)} onClick={event => selectSection(event, section)}
      aria-current={activeSection === section ? "page" : undefined}
      className={`focus-ring duration-standard block min-h-11 min-w-0 w-full break-words px-4 py-3 text-left text-sm font-medium tracking-widest uppercase transition-colors ${activeSection === section ? "bg-inverse text-inverse-ink" : "text-ink-subtle hover:bg-surface-raised hover:text-ink"}`}>
      {area(section)}
    </Link>
  ));

  return (
    <div className="min-h-screen bg-canvas text-ink selection:bg-inverse selection:text-inverse-ink">
      <header className="page-x border-b border-line pb-10 pt-28 md:pb-12 md:pt-32">
        <h1 className="type-display-ui">
          {t("title")}
        </h1>
      </header>

      <div className="flex min-h-[60vh] flex-col md:flex-row">
        <aside className="hidden min-w-0 border-r border-line bg-canvas md:block md:w-64 md:shrink-0">
          <nav aria-label={t("settingsNavigation")} className="sticky top-24 space-y-1 p-6 lg:p-8">{navigation}</nav>
        </aside>
        <div className="page-x border-b border-line py-3 md:hidden">
          <Button aria-expanded={menuOpen} aria-controls={menuId} aria-haspopup="dialog" onClick={() => setMenuOpen(true)} className="w-full justify-between"><span>{area("categories")}</span><ChevronDown aria-hidden className="h-4 w-4" /></Button>
        </div>
        <div className="page-x min-w-0 flex-1 py-6 sm:py-8 md:py-12 lg:py-16">
          <div className="max-w-3xl">
            {visited.map(section => <section key={section} hidden={section !== activeSection} aria-labelledby={`settings-title-${section}`}>
              <h2 id={`settings-title-${section}`} tabIndex={-1} className="focus-ring type-section-title">{area(section)}</h2>
              <div className="mt-8">
                {/* Unmount confirmation flows on history navigation to release modal isolation. */}
                {(section === activeSection || !["library-maintenance", "cleanup"].includes(section)) && <CategoryContent section={section} />}
              </div>
            </section>)}
          </div>
        </div>
      </div>
      <Dialog id={menuId} open={menuOpen} onClose={() => setMenuOpen(false)} closeLabel={area("closeCategories")} ariaLabel={t("settingsNavigation")} size="sm" placement="bottom" panelClassName="max-h-[80vh] overflow-y-auto">
        <nav aria-label={t("settingsNavigation")} className="space-y-1 p-4">{navigation}</nav>
      </Dialog>
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
