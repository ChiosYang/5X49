"use client";

import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import {
  Activity,
  AlertTriangle,
  Command,
  DatabaseZap,
  FileQuestion,
  FolderInput,
  Gauge,
  RefreshCw,
  ScanSearch,
  Search,
  Settings,
  Sparkles,
  Star,
  Trash2,
  X,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import type {
  ManagementActionDefinition,
  ManagementActionDisabledReason,
  ManagementActionId,
} from "@/lib/management-constellation";

type Translate = (key: string, values?: Record<string, string | number>) => string;

const actionIcons: Record<ManagementActionId, typeof Search> = {
  scan: ScanSearch,
  "scrape-metadata": Sparkles,
  "refresh-scores": Star,
  "review-metadata": FileQuestion,
  "organize-files": FolderInput,
  "cleanup-missing": Trash2,
  "open-settings": Settings,
  "open-activity": Activity,
  "clear-data": DatabaseZap,
};

function disabledMessage(reason: ManagementActionDisabledReason, t: Translate) {
  return reason ? t(`disabled.${reason}`) : null;
}

export default function ManagementCommandLayer({
  actions,
  attentionCount,
  busyActions,
  onExecute,
  t,
}: {
  actions: ManagementActionDefinition[];
  attentionCount: number;
  busyActions: Partial<Record<ManagementActionId, boolean>>;
  onExecute: (id: ManagementActionId) => void;
  t: Translate;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const reducedMotion = useReducedMotion();
  const inputRef = useRef<HTMLInputElement>(null);

  const openPalette = () => {
    setQuery("");
    setOpen(true);
  };

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        openPalette();
      } else if (event.key === "Escape") {
        setOpen(false);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  useEffect(() => {
    if (open) window.setTimeout(() => inputRef.current?.focus(), 0);
  }, [open]);

  const filteredActions = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase();
    if (!normalized) return actions;
    return actions.filter((action) => (
      `${t(`actions.${action.id}.label`)} ${t(`actions.${action.id}.description`)}`
        .toLocaleLowerCase()
        .includes(normalized)
    ));
  }, [actions, query, t]);

  const run = (id: ManagementActionId) => {
    const action = actions.find((item) => item.id === id);
    if (!action || action.disabledReason || busyActions[id]) return;
    setOpen(false);
    onExecute(id);
  };

  return (
    <>
      <button
        type="button"
        onClick={openPalette}
        className="focus-ring inline-flex min-h-9 items-center gap-2 border border-white/12 px-3 text-[9px] font-black tracking-[0.14em] text-neutral-400 uppercase transition hover:border-white/25 hover:bg-white/[0.04] hover:text-white"
      >
        <Command className="h-3.5 w-3.5" />
        {t("openCommand")}
        {attentionCount > 0 ? <span className="rounded-full bg-amber-200 px-1.5 py-0.5 text-[8px] text-black">{attentionCount > 99 ? "99+" : attentionCount}</span> : null}
      </button>

      <AnimatePresence>
        {open ? (
          <motion.div
            initial={reducedMotion ? false : { opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="z-modal fixed inset-0 flex items-start justify-center bg-black/75 px-4 pt-[15vh] backdrop-blur-sm"
            onMouseDown={(event) => { if (event.target === event.currentTarget) setOpen(false); }}
          >
            <motion.section
              role="dialog"
              aria-modal="true"
              aria-label={t("paletteTitle")}
              initial={reducedMotion ? false : { opacity: 0, y: 10, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={reducedMotion ? { opacity: 0 } : { opacity: 0, y: 7, scale: 0.99 }}
              className="w-full max-w-2xl overflow-hidden border border-white/15 bg-[#050708] shadow-[0_30px_100px_rgba(0,0,0,.8)]"
            >
              <header className="flex items-center gap-3 border-b border-white/10 px-4">
                <Search className="h-4 w-4 text-neutral-600" />
                <input
                  ref={inputRef}
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder={t("palettePlaceholder")}
                  className="min-h-14 min-w-0 flex-1 bg-transparent text-sm text-white outline-none placeholder:text-neutral-700"
                />
                <button type="button" aria-label={t("closePalette")} onClick={() => setOpen(false)} className="focus-ring p-2 text-neutral-600 hover:text-white"><X className="h-4 w-4" /></button>
              </header>
              <div className="scrollbar-minimal max-h-[55vh] overflow-y-auto p-2">
                {filteredActions.length === 0 ? <p className="px-4 py-8 text-center text-xs text-neutral-600">{t("noCommands")}</p> : null}
                {filteredActions.map((action) => {
                  const Icon = actionIcons[action.id];
                  const disabled = disabledMessage(action.disabledReason, t);
                  return (
                    <button
                      key={action.id}
                      type="button"
                      disabled={Boolean(disabled) || busyActions[action.id]}
                      onClick={() => run(action.id)}
                      className={`focus-ring group flex min-h-16 w-full items-center gap-4 px-4 text-left transition hover:bg-white/[0.05] disabled:cursor-not-allowed disabled:opacity-35 ${action.danger ? "text-red-300" : "text-neutral-300"}`}
                    >
                      <span className="flex h-9 w-9 shrink-0 items-center justify-center border border-white/10 bg-black"><Icon className="h-4 w-4" /></span>
                      <span className="min-w-0 flex-1">
                        <span className="block text-xs font-semibold">{t(`actions.${action.id}.label`)}</span>
                        <span className="mt-1 block text-[10px] leading-4 text-neutral-600">{disabled ?? t(`actions.${action.id}.description`)}</span>
                      </span>
                      {busyActions[action.id] ? <RefreshCw className="h-4 w-4 animate-spin text-cyan-300" /> : action.danger ? <AlertTriangle className="h-4 w-4 text-red-400" /> : <Gauge className="h-4 w-4 text-neutral-800 group-hover:text-neutral-500" />}
                    </button>
                  );
                })}
              </div>
              <footer className="flex items-center justify-between border-t border-white/10 px-4 py-3 text-[9px] text-neutral-700">
                <span>{t("paletteHint")}</span><span>⌘ / Ctrl + K</span>
              </footer>
            </motion.section>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </>
  );
}
