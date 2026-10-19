"use client";

import { useId, useRef, useState, type ReactNode } from "react";
import { IconButton } from "./Button";

/** A click/keyboard disclosure: closed content is not tabbable. */
export function Disclosure({ label, icon, children, active = false }: { label: string; icon: ReactNode; children: ReactNode; active?: boolean }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const trigger = useRef<HTMLButtonElement>(null);
  return <div className="relative" onBlur={(event) => {
    if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false);
  }} onKeyDown={(event) => {
    if (event.key === "Escape" && open) { event.stopPropagation(); setOpen(false); trigger.current?.focus(); }
  }}>
    <IconButton ref={trigger} variant="ghost" aria-label={label} aria-expanded={open} aria-controls={id}
      onClick={() => setOpen((current) => !current)}
      className={active ? "text-ink" : undefined} icon={icon} />
    {open && <div id={id} className="z-popover absolute top-full right-0 w-48 pt-3" onClick={(event) => {
      if ((event.target as HTMLElement).closest("a")) { setOpen(false); trigger.current?.focus(); }
    }}><div className="liquid-glass-popover rounded-media border border-line/80 p-1">{children}</div></div>}
  </div>;
}
