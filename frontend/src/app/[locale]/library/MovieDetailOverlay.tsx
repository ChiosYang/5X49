"use client";

import type { ReactNode } from "react";
import { useRouter } from "next/navigation";
import { Dialog } from "@/components/ui/Dialog";
import MovieDetailReturn from "./MovieDetailReturn";

interface MovieDetailOverlayProps {
  children: ReactNode;
  dialogLabel: string;
  returnLabel: string;
}

export default function MovieDetailOverlay({ children, dialogLabel, returnLabel }: MovieDetailOverlayProps) {
  const router = useRouter();

  return (
    <Dialog
      open
      onClose={() => router.back()}
      closeLabel={returnLabel}
      closeOnBackdrop={false}
      closeOnEscape
      lockScroll
      glass={false}
      scrim={false}
      size="fullscreen"
      ariaLabel={dialogLabel}
      panelClassName="overflow-y-auto"
    >
      <MovieDetailReturn behavior="history" label={returnLabel} />
      {children}
    </Dialog>
  );
}
