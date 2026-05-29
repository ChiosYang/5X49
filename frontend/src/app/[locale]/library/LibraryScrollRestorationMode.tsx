"use client";

import { useEffect } from "react";

export default function LibraryScrollRestorationMode() {
  useEffect(() => {
    if (!("scrollRestoration" in window.history)) return;

    const previousMode = window.history.scrollRestoration;
    window.history.scrollRestoration = "manual";

    return () => {
      window.history.scrollRestoration = previousMode;
    };
  }, []);

  return null;
}
