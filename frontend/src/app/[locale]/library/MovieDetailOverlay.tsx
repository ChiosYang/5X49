"use client";

import { type ReactNode, useEffect } from "react";
import { useRouter } from "next/navigation";
import { X } from "lucide-react";

export default function MovieDetailOverlay({ children }: { children: ReactNode }) {
  const router = useRouter();

  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        router.back();
      }
    };

    window.addEventListener("keydown", handleKeyDown);

    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [router]);

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-[80] overflow-y-auto bg-black text-white"
    >
      <button
        type="button"
        onClick={() => router.back()}
        className="fixed right-6 top-6 z-[90] flex h-11 w-11 items-center justify-center border border-white/20 bg-black/70 text-white backdrop-blur-md transition-colors hover:border-white/60 hover:bg-white hover:text-black"
        aria-label="Close movie detail"
        title="Close"
      >
        <X className="h-4 w-4" />
      </button>
      {children}
    </div>
  );
}
