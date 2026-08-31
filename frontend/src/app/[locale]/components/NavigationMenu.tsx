"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Menu } from "lucide-react";
import { Link } from "@/i18n/routing";

export default function NavigationMenu() {
  const t = useTranslations("Navigation");
  const [isOpen, setIsOpen] = useState(false);

  const closeMenu = () => setIsOpen(false);
  const toggleMenu = () => setIsOpen((open) => !open);

  return (
    <>
      <button
        onClick={toggleMenu}
        className="focus-ring duration-standard flex items-center gap-2 text-sm font-bold tracking-widest uppercase drop-shadow-lg transition-opacity hover:opacity-70"
      >
        <Menu className="h-5 w-5" /> {isOpen ? t("close") : t("menu")}
      </button>

      {/* Sidebar Overlay */}
      <div
        onClick={closeMenu}
        className={`z-overlay fixed inset-0 bg-scrim backdrop-blur-sm transition-opacity duration-standard ease-exit ${
          isOpen ? "opacity-100" : "pointer-events-none opacity-0"
        }`}
      />

      {/* Sidebar */}
      <div
        aria-hidden={!isOpen}
        className={`liquid-glass-sidebar z-navigation fixed top-0 bottom-0 left-0 flex w-full flex-col overflow-y-auto border-r border-line/80 p-8 transition-transform duration-standard ease-exit md:w-[40vw] md:p-16 ${
          isOpen ? "translate-x-0" : "pointer-events-none -translate-x-full"
        }`}
      >
        <div className="my-auto w-full space-y-4 py-16 md:space-y-6 md:py-20">
          <Link
            href="/library"
            onClick={closeMenu}
            className="focus-ring duration-standard block text-5xl font-bold tracking-tighter text-ink transition-colors hover:text-ink-muted md:text-7xl"
          >
            {t("library")}
          </Link>
          <Link
            href="/library/manage"
            onClick={closeMenu}
            className="focus-ring duration-standard block text-5xl font-bold tracking-tighter text-ink transition-colors hover:text-ink-muted md:text-7xl"
          >
            {t("libraryManagement")}
          </Link>
          <Link
            href="/search"
            onClick={closeMenu}
            className="focus-ring duration-standard block text-5xl font-bold tracking-tighter text-ink transition-colors hover:text-ink-muted md:text-7xl"
          >
            {t("search")}
          </Link>
          <Link
            href="/library/activity"
            onClick={closeMenu}
            className="focus-ring duration-standard block text-5xl font-bold tracking-tighter text-ink transition-colors hover:text-ink-muted md:text-7xl"
          >
            {t("activity")}
          </Link>
          <Link
            href="/diary"
            onClick={closeMenu}
            className="focus-ring duration-standard block text-5xl font-bold tracking-tighter text-ink transition-colors hover:text-ink-muted md:text-7xl"
          >
            {t("diary")}
          </Link>
          <Link
            href="/watch-history"
            onClick={closeMenu}
            className="focus-ring duration-standard block text-5xl font-bold tracking-tighter text-ink transition-colors hover:text-ink-muted md:text-7xl"
          >
            {t("watchHistory")}
          </Link>
          <Link
            href="/settings"
            onClick={closeMenu}
            className="focus-ring duration-standard block text-5xl font-bold tracking-tighter text-ink transition-colors hover:text-ink-muted md:text-7xl"
          >
            {t("settings")}
          </Link>
          <Link
            href="#"
            className="duration-standard block cursor-not-allowed text-5xl font-bold tracking-tighter text-ink-disabled transition-colors hover:text-ink-subtle md:text-7xl"
          >
            {t("television")}
          </Link>
          <Link
            href="#"
            className="duration-standard block cursor-not-allowed text-5xl font-bold tracking-tighter text-ink-disabled transition-colors hover:text-ink-subtle md:text-7xl"
          >
            {t("notes")}
          </Link>
          <p className="pt-6 text-xs font-bold tracking-widest text-ink-subtle uppercase">
            {t("project")}
          </p>
        </div>
      </div>
    </>
  );
}
