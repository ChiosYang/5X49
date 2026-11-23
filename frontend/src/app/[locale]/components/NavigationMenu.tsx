"use client";

import { useId, useState } from "react";
import { useTranslations } from "next-intl";
import { Menu, X } from "lucide-react";
import { Dialog } from "@/components/ui/Dialog";
import { Link, usePathname } from "@/i18n/routing";
import { Button } from "@/components/ui/Button";

const PRIMARY_ITEMS = [
  { href: "/library", key: "library" },
  { href: "/explore", key: "explore" },
  { href: "/diary", key: "diary" },
] as const;

const SECONDARY_ITEMS = [
  { href: "/library/activity", key: "activity" },
  { href: "/settings", key: "settings" },
] as const;

function isNavActive(pathname: string, href: string) {
  if (href === "/library") {
    return pathname === "/library" || (pathname.startsWith("/library/") && !pathname.startsWith("/library/activity"));
  }
  return pathname === href || pathname.startsWith(`${href}/`);
}

export default function NavigationMenu() {
  const panelId = useId();
  const t = useTranslations("Navigation");
  const pathname = usePathname();
  const [isOpen, setIsOpen] = useState(false);

  const closeMenu = () => setIsOpen(false);
  const toggleMenu = () => setIsOpen((open) => !open);

  return (
    <>
      <Button
        variant="ghost"
        type="button" aria-expanded={isOpen} aria-controls={panelId} aria-haspopup="dialog"
        onClick={toggleMenu}
        className="px-0 text-ink hover:bg-transparent hover:text-ink-muted"
      >
        <Menu className="h-5 w-5" /> {isOpen ? t("close") : t("menu")}
      </Button>

      <Dialog id={panelId} open={isOpen} onClose={closeMenu} ariaLabel={t("menu")} closeLabel={t("close")}
        size="fullscreen" overlayClassName="justify-start items-stretch"
        panelClassName="liquid-glass-sidebar flex w-full flex-col justify-between overflow-y-auto border-r border-line/80 p-8 md:w-[min(30rem,40vw)] md:px-14 md:py-12">
        <Button variant="ghost" data-dialog-initial-focus="" onClick={closeMenu} className="self-start px-0 text-ink" icon={<X className="h-5 w-5" aria-hidden />}>{t("close")}</Button>

        <nav aria-label={t("menu")} className="my-auto w-full space-y-5 py-12 md:space-y-6">
          {PRIMARY_ITEMS.map(({ href, key }) => {
            const active = isNavActive(pathname, href);
            return (
              <Link
                key={href}
                href={href}
                onClick={closeMenu}
                aria-current={active ? "page" : undefined}
                className={`focus-ring duration-standard flex items-center justify-between gap-4 text-4xl tracking-tight transition-colors md:text-5xl ${
                  active ? "font-medium text-ink" : "font-normal text-ink-subtle hover:text-ink"
                }`}
              >
                <span>{t(key)}</span>
                {active ? <span aria-hidden="true" className="h-1.5 w-1.5 shrink-0 rounded-pill bg-ink" /> : null}
              </Link>
            );
          })}
        </nav>

        <div className="flex flex-wrap items-center gap-x-6 gap-y-3 border-t border-line/80 pt-6">
          {SECONDARY_ITEMS.map(({ href, key }) => {
            const active = isNavActive(pathname, href);
            return (
              <Link
                key={href}
                href={href}
                onClick={closeMenu}
                aria-current={active ? "page" : undefined}
                className={`focus-ring duration-standard inline-flex min-h-10 items-center type-label transition-colors ${
                  active ? "text-ink" : "text-ink-subtle hover:text-ink"
                }`}
              >
                {t(key)}
              </Link>
            );
          })}
        </div>
      </Dialog>
    </>
  );
}
