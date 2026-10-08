"use client";

import { useEffect } from "react";
import { usePathname } from "next/navigation";
import { readFilmReturn } from "@/lib/navigation-context";

export default function FilmReturnRestoration() {
  const pathname = usePathname();
  useEffect(() => {
    const context = readFilmReturn();
    if (!context || context.href !== `${window.location.pathname}${window.location.search}`) return;
    let done = false;
    const restore = () => {
      if (done) return;
      const target = document.getElementById(context.focusId || `film-link-${context.filmId}`);
      if (!target || target.closest("[inert]")) return;
      done = true;
      target.focus({ preventScroll: true });
      window.scrollTo({ top: context.scrollY, behavior: "instant" });
      observer.disconnect();
    };
    const observer = new MutationObserver(restore);
    observer.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ["inert"] });
    const frame = requestAnimationFrame(restore);
    const timer = window.setTimeout(() => observer.disconnect(), 10000);
    return () => { cancelAnimationFrame(frame); clearTimeout(timer); observer.disconnect(); };
  }, [pathname]);
  return null;
}
