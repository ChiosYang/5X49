"use client";

import { useEffect } from "react";
import { restoreWindowScroll, takeLibraryScrollPosition } from "@/lib/library-scroll";

export default function LibraryScrollRestorer() {
  useEffect(() => {
    const scrollY = takeLibraryScrollPosition();
    if (scrollY == null) return;

    restoreWindowScroll(scrollY);
  }, []);

  return null;
}
