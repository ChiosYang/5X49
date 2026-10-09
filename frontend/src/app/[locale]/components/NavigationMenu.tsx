"use client";

import { useId, useState } from "react";
import { useTranslations } from "next-intl";
import { Menu, X } from "lucide-react";
import { Dialog } from "@/components/ui/Dialog";
import { Link } from "@/i18n/routing";

export default function NavigationMenu() {
  const panelId = useId();
  const t = useTranslations("Navigation");
  const [isOpen, setIsOpen] = useState(false);

  const closeMenu = () => setIsOpen(false);
  const toggleMenu = () => setIsOpen((open) => !open);

  return (
    <>
      <button
        type="button" aria-expanded={isOpen} aria-controls={panelId} aria-haspopup="dialog"
        onClick={toggleMenu}
        className="focus-ring duration-standard flex items-center gap-2 text-sm font-bold tracking-widest uppercase drop-shadow-lg transition-opacity hover:opacity-70"
      >
        <Menu className="h-5 w-5" /> {isOpen ? t("close") : t("menu")}
      </button>

      <Dialog id={panelId} open={isOpen} onClose={closeMenu} ariaLabel={t("menu")} closeLabel={t("close")}
        size="fullscreen" overlayClassName="justify-start items-stretch"
        panelClassName="liquid-glass-sidebar flex w-full flex-col overflow-y-auto border-r border-line/80 p-8 md:w-[40vw] md:p-16">
        <button type="button" data-dialog-initial-focus="" onClick={closeMenu} className="focus-ring flex min-h-11 items-center gap-2 self-start text-sm font-bold uppercase"><X className="h-5 w-5" aria-hidden />{t("close")}</button>
        <div className="my-auto w-full space-y-4 py-16 md:space-y-6 md:py-20">
          <Link
            href="/library"
            onClick={closeMenu}
            className="focus-ring duration-standard block text-5xl font-bold tracking-tighter text-ink transition-colors hover:text-ink-muted md:text-7xl"
          >
            {t("library")}
          </Link>
          <Link
            href="/explore"
            onClick={closeMenu}
            className="focus-ring duration-standard block text-5xl font-bold tracking-tighter text-ink transition-colors hover:text-ink-muted md:text-7xl"
          >
            {t("explore")}
          </Link>
          <Link
            href="/search"
            onClick={closeMenu}
            className="focus-ring duration-standard block text-5xl font-bold tracking-tighter text-ink transition-colors hover:text-ink-muted md:text-7xl"
          >
            {t("search")}
          </Link>
          <Link href="/ask" onClick={closeMenu} className="focus-ring duration-standard block text-5xl font-bold tracking-tighter text-ink transition-colors hover:text-ink-muted md:text-7xl">
            {t("ask")}
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
            href="/settings"
            onClick={closeMenu}
            className="focus-ring duration-standard block text-5xl font-bold tracking-tighter text-ink transition-colors hover:text-ink-muted md:text-7xl"
          >
            {t("settings")}
          </Link>
          <p className="pt-6 text-xs font-bold tracking-widest text-ink-subtle uppercase">
            {t("project")}
          </p>
        </div>
      </Dialog>
    </>
  );
}
