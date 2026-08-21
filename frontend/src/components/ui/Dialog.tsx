"use client";

import { useEffect, useRef, type ReactNode } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { cn } from "@/lib/cn";

type DialogSize = "sm" | "md" | "lg" | "xl" | "fullscreen";
type DialogPlacement = "center" | "bottom";

const sizeClasses: Record<DialogSize, string> = {
  sm: "max-w-lg",
  md: "max-w-2xl",
  lg: "max-w-5xl",
  xl: "max-w-6xl",
  fullscreen: "h-full max-w-none",
};

export interface DialogProps {
  animated?: boolean;
  ariaLabel?: string;
  ariaLabelledBy?: string;
  children: ReactNode;
  closeLabel: string;
  closeOnBackdrop?: boolean;
  closeOnEscape?: boolean;
  glass?: boolean;
  lockScroll?: boolean;
  onClose: () => void;
  open: boolean;
  overlayClassName?: string;
  panelClassName?: string;
  placement?: DialogPlacement;
  scrim?: boolean;
  size?: DialogSize;
}

export function Dialog({
  animated = false,
  ariaLabel,
  ariaLabelledBy,
  children,
  closeLabel,
  closeOnBackdrop = true,
  closeOnEscape = true,
  glass = true,
  lockScroll = true,
  onClose,
  open,
  overlayClassName,
  panelClassName,
  placement = "center",
  scrim = true,
  size = "md",
}: DialogProps) {
  const previouslyFocused = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!open) return;
    previouslyFocused.current = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null;
    return () => previouslyFocused.current?.focus();
  }, [open]);

  useEffect(() => {
    if (!open || !closeOnEscape) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [closeOnEscape, onClose, open]);

  useEffect(() => {
    if (!open || !lockScroll) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [lockScroll, open]);

  const content = (
    <>
      {closeOnBackdrop ? (
        <button
          type="button"
          tabIndex={-1}
          className="z-content absolute inset-0 cursor-default"
          onClick={onClose}
          aria-label={closeLabel}
        />
      ) : (
        <div className="z-content absolute inset-0" aria-hidden="true" />
      )}
      <section
        role="dialog"
        aria-modal="true"
        aria-label={ariaLabel}
        aria-labelledby={ariaLabelledBy}
        className={cn(
          "z-raised relative w-full overflow-hidden text-ink",
          glass ? "liquid-glass-modal border border-line/80" : "bg-canvas",
          sizeClasses[size],
          panelClassName,
        )}
      >
        {children}
      </section>
    </>
  );
  const overlayClasses = cn(
    "z-modal fixed inset-0 flex justify-center",
    scrim ? "scrim-backdrop" : "bg-canvas",
    size === "fullscreen" ? "p-0" : "p-4",
    placement === "bottom" ? "items-end py-6 sm:items-center" : "items-center",
    overlayClassName,
  );

  if (animated) {
    return (
      <AnimatePresence>
        {open ? (
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 20 }}
            className={overlayClasses}
          >
            {content}
          </motion.div>
        ) : null}
      </AnimatePresence>
    );
  }

  return open ? <div className={overlayClasses}>{content}</div> : null;
}
