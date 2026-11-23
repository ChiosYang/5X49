"use client";

import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { MoreHorizontal } from "lucide-react";
import { IconButton } from "@/components/ui/Button";
import { closeMetadataCandidateInspection } from "@/components/metadata/MetadataCandidatePicker";

/** A disclosure of ordinary buttons; Tab retains the page's normal focus order. */
export default function FilmMoreActions({ label, modalOpen, children }: {
  label: string;
  modalOpen: boolean;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open || modalOpen) return;
    const outside = (event: PointerEvent) => {
      if (event.target instanceof Node && !root.current?.contains(event.target)) setOpen(false);
    };
    document.addEventListener("pointerdown", outside);
    return () => document.removeEventListener("pointerdown", outside);
  }, [open, modalOpen]);

  useEffect(() => {
    if (!open || modalOpen) return;
    // Run before a containing detail dialog's document-level Escape handler.
    const escape = (event: KeyboardEvent) => {
      if (event.key !== "Escape" || !(event.target instanceof Node)) return;
      // Disabling a pending action can move browser focus to body. Escape still closes More.
      if (!root.current?.contains(event.target) && event.target !== document.body) return;
      event.preventDefault(); event.stopPropagation();
      if (event.target instanceof HTMLElement && closeMetadataCandidateInspection(event.target)) return;
      setOpen(false); trigger.current?.focus();
    };
    window.addEventListener("keydown", escape, true);
    return () => window.removeEventListener("keydown", escape, true);
  }, [open, modalOpen]);

  return (
    <div ref={root} className="relative shrink-0" onBlur={(event) => {
      if (!modalOpen && event.relatedTarget && !event.currentTarget.contains(event.relatedTarget)) setOpen(false);
    }} onKeyDown={(event) => {
      if (event.defaultPrevented || modalOpen) return;
      if (event.key === "Escape" && open) {
        event.preventDefault(); event.stopPropagation(); setOpen(false); trigger.current?.focus();
      }
      if (event.key === "ArrowDown" && event.target === trigger.current) {
        event.preventDefault(); setOpen(true);
        requestAnimationFrame(() => panel.current?.querySelector<HTMLButtonElement>("button:not([disabled])")?.focus());
      }
    }}>
      <IconButton ref={trigger} aria-label={label} title={label} className="rounded-full" aria-expanded={open} aria-controls={id}
        onClick={() => setOpen((value) => !value)} icon={<MoreHorizontal className="h-4 w-4 shrink-0" />} />
      <div ref={panel} id={id} role="group" aria-label={label} onClick={(event) => {
        if ((event.target as HTMLElement).closest("[data-film-more-close]")) setOpen(false);
      }}
        className={open ? "liquid-glass-popover z-popover absolute right-0 top-full mt-2 w-[min(20rem,calc(100vw-4rem))] rounded-media border border-line/80 p-2" : "hidden"}>
        {children}
      </div>
    </div>
  );
}
