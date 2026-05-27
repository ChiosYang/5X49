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
        className="flex items-center gap-2 uppercase text-sm font-bold tracking-widest hover:opacity-70 transition-opacity drop-shadow-lg"
      >
        <Menu className="w-5 h-5" /> {isOpen ? "CLOSE" : "MENU"}
      </button>

      {/* Sidebar Overlay */}
      <div
        onClick={closeMenu}
        className={`fixed inset-0 bg-black/50 z-40 backdrop-blur-sm transition-opacity duration-150 ease-out ${
          isOpen ? "opacity-100" : "opacity-0 pointer-events-none"
        }`}
      />

      {/* Sidebar */}
      <div
        aria-hidden={!isOpen}
        className={`fixed top-0 left-0 bottom-0 w-full md:w-[40vw] bg-black z-50 p-8 md:p-16 flex flex-col justify-center shadow-2xl border-r border-neutral-900 transition-transform duration-150 ease-out ${
          isOpen ? "translate-x-0" : "-translate-x-full pointer-events-none"
        }`}
      >
        <div className="space-y-4 md:space-y-6">
          <Link
            href="/library"
            onClick={closeMenu}
            className="block text-5xl md:text-7xl font-bold tracking-tighter text-white hover:text-neutral-400 transition-colors"
          >
            {t("library")}
          </Link>
          <Link
            href="/search"
            onClick={closeMenu}
            className="block text-5xl md:text-7xl font-bold tracking-tighter text-white hover:text-neutral-400 transition-colors"
          >
            Search
          </Link>
          <Link
            href="/library/activity"
            onClick={closeMenu}
            className="block text-5xl md:text-7xl font-bold tracking-tighter text-white hover:text-neutral-400 transition-colors"
          >
            Activity
          </Link>
          <Link
            href="/watch-history"
            onClick={closeMenu}
            className="block text-5xl md:text-7xl font-bold tracking-tighter text-white hover:text-neutral-400 transition-colors"
          >
            {t("watchHistory")}
          </Link>
          <Link
            href="/settings"
            onClick={closeMenu}
            className="block text-5xl md:text-7xl font-bold tracking-tighter text-white hover:text-neutral-400 transition-colors"
          >
            {t("settings")}
          </Link>
          <Link
            href="#"
            className="block text-5xl md:text-7xl font-bold tracking-tighter text-neutral-600 hover:text-neutral-500 transition-colors cursor-not-allowed"
          >
            Television
          </Link>
          <Link
            href="#"
            className="block text-5xl md:text-7xl font-bold tracking-tighter text-neutral-600 hover:text-neutral-500 transition-colors cursor-not-allowed"
          >
            Notes
          </Link>
        </div>

        {/* Footer in Sidebar */}
        <div className="absolute bottom-16 left-8 md:left-16 text-neutral-500 text-xs font-bold uppercase tracking-widest space-y-2">
          <p>{t("project")}</p>
        </div>
      </div>
    </>
  );
}
