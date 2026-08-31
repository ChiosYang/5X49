"use client";

import { useEffect, useRef, type ReactNode } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { cn } from "@/lib/cn";

type DialogSize = "sm" | "md" | "lg" | "xl" | "fullscreen";
type DialogPlacement = "center" | "bottom";

const focusableSelector = [
  "a[href]",
  "area[href]",
  "button:not([disabled])",
  "input:not([disabled]):not([type='hidden'])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "[contenteditable='true']",
  "[tabindex]:not([tabindex='-1'])",
].join(",");

const openDialogs: HTMLElement[] = [];

function getFocusableElements(container: HTMLElement) {
  return Array.from(container.querySelectorAll<HTMLElement>(focusableSelector)).filter(
    (element) =>
      element.getAttribute("aria-hidden") !== "true" &&
      !element.closest("[inert]") &&
      element.getClientRects().length > 0,
  );
}

function isolateDialogBackground(dialog: HTMLElement) {
  const previousStates: Array<{
    element: HTMLElement;
    inert: boolean;
    ariaHidden: string | null;
  }> = [];
  let current: HTMLElement = dialog;

  while (current.parentElement) {
    const parent = current.parentElement;

    for (const sibling of Array.from(parent.children)) {
      if (
        !(sibling instanceof HTMLElement) ||
        sibling === current ||
        sibling.tagName === "SCRIPT" ||
        sibling.tagName === "STYLE"
      ) {
        continue;
      }

      previousStates.push({
        element: sibling,
        inert: sibling.inert,
        ariaHidden: sibling.getAttribute("aria-hidden"),
      });
      sibling.inert = true;
      sibling.setAttribute("aria-hidden", "true");
    }

    if (parent === document.body) break;
    current = parent;
  }

  return () => {
    for (const { element, inert, ariaHidden } of previousStates.reverse()) {
      element.inert = inert;
      if (ariaHidden === null) {
        element.removeAttribute("aria-hidden");
      } else {
        element.setAttribute("aria-hidden", ariaHidden);
      }
    }
  };
}

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
  const overlayRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLElement>(null);

  useEffect(() => {
    if (!open) return;
    const overlay = overlayRef.current;
    const panel = panelRef.current;
    if (!overlay || !panel) return;

    previouslyFocused.current = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null;

    openDialogs.push(overlay);
    const preferredFocus = panel.querySelector<HTMLElement>("[data-dialog-initial-focus]");
    const initialFocus = preferredFocus || getFocusableElements(panel)[0] || panel;
    initialFocus.focus({ preventScroll: true });
    const restoreBackground = isolateDialogBackground(overlay);

    return () => {
      const stackIndex = openDialogs.lastIndexOf(overlay);
      if (stackIndex >= 0) openDialogs.splice(stackIndex, 1);
      restoreBackground();

      const focusTarget = previouslyFocused.current;
      if (focusTarget?.isConnected && !focusTarget.closest("[inert]")) {
        focusTarget.focus({ preventScroll: true });
      }
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      const overlay = overlayRef.current;
      const panel = panelRef.current;
      if (!overlay || !panel || openDialogs.at(-1) !== overlay) return;

      if (event.key === "Escape" && closeOnEscape) {
        event.preventDefault();
        onClose();
        return;
      }

      if (event.key !== "Tab") return;

      const focusableElements = getFocusableElements(panel);
      if (focusableElements.length === 0) {
        event.preventDefault();
        panel.focus({ preventScroll: true });
        return;
      }

      const first = focusableElements[0];
      const last = focusableElements.at(-1)!;
      const activeElement = document.activeElement;

      if (event.shiftKey && (activeElement === first || !panel.contains(activeElement))) {
        event.preventDefault();
        last.focus({ preventScroll: true });
      } else if (!event.shiftKey && (activeElement === last || !panel.contains(activeElement))) {
        event.preventDefault();
        first.focus({ preventScroll: true });
      }
    };
    document.addEventListener("keydown", handleKeyDown, true);
    return () => document.removeEventListener("keydown", handleKeyDown, true);
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
        ref={panelRef}
        tabIndex={-1}
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
            ref={overlayRef}
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

  return open ? <div ref={overlayRef} className={overlayClasses}>{content}</div> : null;
}
