"use client";

import type { ReactNode } from "react";
import { useRouter } from "next/navigation";
import { Dialog } from "@/components/ui/Dialog";

export default function MovieDetailOverlay({ children }: { children: ReactNode }) {
  const router = useRouter();

  return (
    <Dialog
      open
      onClose={() => router.back()}
      closeLabel="Close movie details"
      closeOnBackdrop={false}
      closeOnEscape
      lockScroll
      glass={false}
      scrim={false}
      size="fullscreen"
      ariaLabel="Movie details"
      panelClassName="overflow-y-auto"
    >
      {children}
    </Dialog>
  );
}
