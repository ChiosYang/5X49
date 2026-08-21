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
        <Menu className="w-5 h-5" /> {isOpen ? t("close") : t("menu")}
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
        className={`liquid-glass-sidebar fixed top-0 left-0 bottom-0 w-full md:w-[40vw] z-50 flex flex-col overflow-y-auto border-r border-neutral-900/80 p-8 transition-transform duration-150 ease-out md:p-16 ${
          isOpen ? "translate-x-0" : "-translate-x-full pointer-events-none"
        }`}
      >
        <div className="my-auto w-full space-y-4 py-16 md:space-y-6 md:py-20">
          <Link
            href="/library"
            onClick={closeMenu}
            className="block text-5xl md:text-7xl font-bold tracking-tighter text-white hover:text-neutral-400 transition-colors"
          >
            {t("library")}
          </Link>
          <Link
            href="/library/manage"
            onClick={closeMenu}
            className="block text-5xl md:text-7xl font-bold tracking-tighter text-white hover:text-neutral-400 transition-colors"
          >
            {t("libraryManagement")}
          </Link>
          <Link
            href="/search"
            onClick={closeMenu}
            className="block text-5xl md:text-7xl font-bold tracking-tighter text-white hover:text-neutral-400 transition-colors"
          >
            {t("search")}
          </Link>
          <Link
            href="/library/activity"
            onClick={closeMenu}
            className="block text-5xl md:text-7xl font-bold tracking-tighter text-white hover:text-neutral-400 transition-colors"
          >
            {t("activity")}
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
            {t("television")}
          </Link>
          <Link
            href="#"
            className="block text-5xl md:text-7xl font-bold tracking-tighter text-neutral-600 hover:text-neutral-500 transition-colors cursor-not-allowed"
          >
            {t("notes")}
          </Link>
          <p className="pt-6 text-xs font-bold uppercase tracking-widest text-neutral-500">
            {t("project")}
          </p>
        </div>
      </div>
    </>
  );
}
