"use client";

import { useEffect } from "react";
import { clearLibraryReturnAnchor, getLibraryReturnAnchor } from "@/lib/library-return-anchor";

function findMovieCard(movieId: string) {
  return Array.from(document.querySelectorAll<HTMLElement>("[data-library-movie-id]")).find(
    (element) => element.dataset.libraryMovieId === movieId
  ) ?? null;
}

export default function LibraryReturnAnchorRestorer() {
  useEffect(() => {
    const timeouts: number[] = [];
    let restored = false;

    const clearQueuedRestores = () => {
      for (const timeout of timeouts) {
        window.clearTimeout(timeout);
      }
      timeouts.length = 0;
    };

    const restore = () => {
      if (restored) return;

      const anchor = getLibraryReturnAnchor();
      if (!anchor) return;

      const element = findMovieCard(anchor.movieId);
      if (!element) return;

      const targetTop = window.scrollY + element.getBoundingClientRect().top - anchor.viewportTop;
      window.scrollTo(0, Math.max(0, targetTop));
      restored = true;
      clearLibraryReturnAnchor();
      clearQueuedRestores();
    };

    restore();
    window.requestAnimationFrame(() => {
      restore();
      window.requestAnimationFrame(restore);
    });

    for (const delay of [50, 150, 300, 700, 1200]) {
      timeouts.push(window.setTimeout(restore, delay));
    }
    return () => {
      clearQueuedRestores();
    };
  }, []);

  return null;
}
