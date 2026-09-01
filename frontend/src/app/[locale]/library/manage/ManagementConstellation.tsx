"use client";

import { motion, useReducedMotion } from "framer-motion";
import {
  AlertTriangle,
  CircleDot,
  Database,
  FileQuestion,
  FileWarning,
  FolderInput,
  Maximize2,
  Minus,
  Plus,
  Radar,
  RefreshCw,
  RotateCcw,
  ScanSearch,
  Sparkles,
  Star,
  Wifi,
} from "lucide-react";
import { useMemo, useRef, useState } from "react";

import type {
  ManagementConstellationModel,
  ManagementNode,
  ManagementNodeId,
  ManagementNodeState,
} from "@/lib/management-constellation";

type Translate = (key: string, values?: Record<string, string | number>) => string;

const stateClasses: Record<ManagementNodeState, string> = {
  healthy: "border-emerald-300/45 bg-emerald-300/[0.09] text-emerald-200",
  idle: "border-white/15 bg-white/[0.04] text-neutral-300",
  running: "border-cyan-300/65 bg-cyan-300/[0.13] text-cyan-200 shadow-[0_0_34px_rgba(103,232,249,.13)]",
  attention: "border-amber-300/60 bg-amber-300/[0.12] text-amber-200 shadow-[0_0_34px_rgba(252,211,77,.10)]",
  failed: "border-red-400/70 bg-red-400/[0.12] text-red-300 shadow-[0_0_34px_rgba(248,113,113,.10)]",
  unavailable: "border-dashed border-white/15 bg-black/45 text-neutral-600",
};

const edgeClasses: Record<ManagementNodeState, string> = {
  healthy: "stroke-emerald-300/20",
  idle: "stroke-white/10",
  running: "stroke-cyan-300/65",
  attention: "stroke-amber-300/45",
  failed: "stroke-red-400/55",
  unavailable: "stroke-white/10",
};

function nodeIcon(node: ManagementNode) {
  if (node.id === "library") return Database;
  if (node.id === "watcher") return Wifi;
  if (node.id === "sync") return ScanSearch;
  if (node.id === "metadata") return Sparkles;
  if (node.id === "scores") return Star;
  if (node.id === "organizer") return FolderInput;
  if (node.id === "metadata-review") return FileQuestion;
  if (node.id === "organization-review") return FolderInput;
  if (node.id === "missing-items") return FileWarning;
  if (node.kind === "film") return FileQuestion;
  if (node.kind === "file") return FolderInput;
  if (node.kind === "missing") return FileWarning;
  return CircleDot;
}

function nodeLabel(node: ManagementNode, t: Translate) {
  const labels: Partial<Record<ManagementNodeId, string>> = {
    library: t("nodes.library"),
    watcher: t("nodes.watcher"),
    sync: t("nodes.sync"),
    metadata: t("nodes.metadata"),
    scores: t("nodes.scores"),
    organizer: t("nodes.organizer"),
    "metadata-review": t("nodes.metadataReview"),
    "organization-review": t("nodes.organizationReview"),
    "missing-items": t("nodes.missingItems"),
  };
  return labels[node.id] ?? node.label;
}

function isChild(node: ManagementNode) {
  return node.kind === "film" || node.kind === "file" || node.kind === "missing";
}

function directionScore(
  current: ManagementNode,
  candidate: ManagementNode,
  key: string,
) {
  const dx = candidate.x - current.x;
  const dy = candidate.y - current.y;
  if (key === "ArrowRight" && dx <= 0) return Number.POSITIVE_INFINITY;
  if (key === "ArrowLeft" && dx >= 0) return Number.POSITIVE_INFINITY;
  if (key === "ArrowDown" && dy <= 0) return Number.POSITIVE_INFINITY;
  if (key === "ArrowUp" && dy >= 0) return Number.POSITIVE_INFINITY;
  const primary = key === "ArrowRight" || key === "ArrowLeft" ? Math.abs(dx) : Math.abs(dy);
  const secondary = key === "ArrowRight" || key === "ArrowLeft" ? Math.abs(dy) : Math.abs(dx);
  return primary + secondary * 1.7;
}

export default function ManagementConstellation({
  model,
  selectedId,
  onSelect,
  onReset,
  t,
}: {
  model: ManagementConstellationModel;
  selectedId: ManagementNodeId;
  onSelect: (id: ManagementNodeId) => void;
  onReset: () => void;
  t: Translate;
}) {
  const [zoomState, setZoomState] = useState({ context: "library", value: 1 });
  const reducedMotion = useReducedMotion();
  const buttonRefs = useRef(new Map<ManagementNodeId, HTMLButtonElement>());
  const selected = model.nodes.find((node) => node.id === selectedId)
    ?? model.nodes.find((node) => node.id === "library")
    ?? model.nodes[0];
  const activeClusterId = selected.kind === "cluster"
    ? selected.id
    : isChild(selected)
      ? selected.parentId
      : undefined;
  const visibleNodes = useMemo(
    () => model.nodes.filter((node) => !isChild(node) || node.parentId === activeClusterId),
    [activeClusterId, model.nodes],
  );
  const visibleIds = useMemo(() => new Set(visibleNodes.map((node) => node.id)), [visibleNodes]);
  const visibleEdges = model.edges.filter((edge) => visibleIds.has(edge.from) && visibleIds.has(edge.to));

  const zoomContext = activeClusterId ?? selected.id;
  const defaultZoom = activeClusterId ? 1.18 : selected.id === "library" ? 1 : 1.08;
  const zoom = zoomState.context === zoomContext ? zoomState.value : defaultZoom;

  const focusX = selected.x;
  const focusY = selected.y;
  const transform = `translate(${50 - focusX}%, ${50 - focusY}%) scale(${zoom})`;

  const handleNodeKeyDown = (event: React.KeyboardEvent<HTMLButtonElement>, node: ManagementNode) => {
    if (event.key === "Escape") {
      event.preventDefault();
      if (isChild(node) && node.parentId) onSelect(node.parentId);
      else onReset();
      return;
    }
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onSelect(node.id);
      return;
    }
    if (!event.key.startsWith("Arrow")) return;
    event.preventDefault();
    const next = visibleNodes
      .filter((candidate) => candidate.id !== node.id)
      .map((candidate) => ({ candidate, score: directionScore(node, candidate, event.key) }))
      .filter((item) => Number.isFinite(item.score))
      .sort((left, right) => left.score - right.score || left.candidate.id.localeCompare(right.candidate.id))[0];
    if (next) buttonRefs.current.get(next.candidate.id)?.focus();
  };

  return (
    <section
      aria-label={t("mapLabel")}
      className="relative h-[29rem] min-h-0 overflow-hidden bg-[radial-gradient(circle_at_center,rgba(34,211,238,.09),transparent_24%),radial-gradient(circle_at_25%_25%,rgba(251,191,36,.04),transparent_22%),#020506] sm:h-[35rem] xl:h-[calc(100vh-12.5rem)] xl:min-h-[38rem]"
    >
      <div className="pointer-events-none absolute inset-0 opacity-35 [background-image:radial-gradient(rgba(255,255,255,.22)_0.6px,transparent_0.6px)] [background-size:25px_25px]" />
      <div className="pointer-events-none absolute top-1/2 left-1/2 h-[31rem] w-[31rem] -translate-x-1/2 -translate-y-1/2 rounded-full border border-white/[0.035]" />
      <div className="absolute top-4 left-4 z-30 flex items-center gap-2 border border-white/10 bg-black/55 px-3 py-2 text-[9px] font-bold tracking-[0.14em] text-neutral-500 uppercase backdrop-blur-md">
        <Radar className="h-3.5 w-3.5 text-cyan-300" />
        {activeClusterId ? t("focusedMode") : t("systemMode")}
      </div>
      <div className="absolute top-4 right-4 z-30 flex items-center border border-white/10 bg-black/55 p-1 backdrop-blur-md">
        <button type="button" aria-label={t("zoomOut")} onClick={() => setZoomState({ context: zoomContext, value: Math.max(0.78, Number((zoom - 0.1).toFixed(2))) })} className="focus-ring flex h-8 w-8 items-center justify-center text-neutral-500 hover:text-white"><Minus className="h-3.5 w-3.5" /></button>
        <span className="hidden w-10 text-center text-[9px] text-neutral-600 sm:block">{Math.round(zoom * 100)}%</span>
        <button type="button" aria-label={t("zoomIn")} onClick={() => setZoomState({ context: zoomContext, value: Math.min(1.42, Number((zoom + 0.1).toFixed(2))) })} className="focus-ring flex h-8 w-8 items-center justify-center text-neutral-500 hover:text-white"><Plus className="h-3.5 w-3.5" /></button>
        <button type="button" aria-label={t("resetView")} onClick={() => { setZoomState({ context: "library", value: 1 }); onReset(); }} className="focus-ring flex h-8 w-8 items-center justify-center border-l border-white/10 text-neutral-500 hover:text-white sm:ml-1"><Maximize2 className="h-3.5 w-3.5" /></button>
      </div>

      <motion.div
        className="absolute inset-0 origin-center"
        animate={{ transform }}
        transition={reducedMotion ? { duration: 0 } : { duration: 0.38, ease: [0.2, 0, 0, 1] }}
      >
        <svg aria-hidden="true" className="pointer-events-none absolute inset-0 h-full w-full overflow-visible">
          {visibleEdges.map((edge) => {
            const from = visibleNodes.find((node) => node.id === edge.from);
            const to = visibleNodes.find((node) => node.id === edge.to);
            if (!from || !to) return null;
            return (
              <motion.line
                key={edge.id}
                x1={`${from.x}%`}
                y1={`${from.y}%`}
                x2={`${to.x}%`}
                y2={`${to.y}%`}
                className={`${edgeClasses[edge.state]} ${edge.state === "unavailable" ? "[stroke-dasharray:2_2]" : ""}`}
                strokeWidth={edge.from === selectedId || edge.to === selectedId ? 1.5 : 0.8}
                initial={{ opacity: 0 }}
                animate={{ opacity: edge.from === selectedId || edge.to === selectedId ? 1 : 0.6 }}
              />
            );
          })}
        </svg>

        {visibleNodes.map((node) => {
          const Icon = nodeIcon(node);
          const active = node.id === selectedId;
          const large = node.kind === "library";
          const medium = node.kind === "service" || node.kind === "cluster";
          return (
            <motion.button
              key={node.id}
              ref={(element) => {
                if (element) buttonRefs.current.set(node.id, element);
                else buttonRefs.current.delete(node.id);
              }}
              type="button"
              aria-pressed={active}
              aria-label={`${nodeLabel(node, t)}${node.count !== undefined ? `, ${t("itemCount", { count: node.count })}` : ""}, ${t(`states.${node.state}`)}`}
              onClick={() => onSelect(node.id)}
              onKeyDown={(event) => handleNodeKeyDown(event, node)}
              style={{ left: `${node.x}%`, top: `${node.y}%` }}
              initial={reducedMotion ? false : { opacity: 0, scale: 0.7 }}
              animate={{ opacity: 1, scale: active ? 1.1 : 1 }}
              exit={reducedMotion ? { opacity: 0 } : { opacity: 0, scale: 0.7 }}
              whileHover={reducedMotion ? undefined : { scale: active ? 1.1 : 1.05 }}
              transition={reducedMotion ? { duration: 0 } : { duration: 0.24, ease: [0.2, 0, 0, 1] }}
              className={`focus-ring absolute z-10 -translate-x-1/2 -translate-y-1/2 rounded-full border text-center backdrop-blur-sm ${stateClasses[node.state]} ${large ? "h-28 w-28 sm:h-32 sm:w-32" : medium ? "h-[4.75rem] w-[4.75rem] sm:h-[5.5rem] sm:w-[5.5rem]" : "h-14 w-14 sm:h-16 sm:w-16"} ${active ? "ring-1 ring-white/35" : ""}`}
            >
              {node.state === "running" && !reducedMotion ? <span className="absolute inset-[-7px] animate-ping rounded-full border border-cyan-300/30" /> : null}
              {node.state === "failed" ? <AlertTriangle className="absolute top-1 right-1 h-3.5 w-3.5" /> : null}
              <Icon className={`mx-auto ${large ? "h-5 w-5" : "h-4 w-4"}`} />
              <span className={`mx-auto mt-1.5 block max-w-[90%] truncate font-black ${large ? "text-xs" : "text-[9px]"}`}>{nodeLabel(node, t)}</span>
              {node.count !== undefined ? <span className="mt-1 block text-[8px] opacity-55">{t("itemCount", { count: node.count })}</span> : node.detail ? <span className="mx-auto mt-1 block max-w-[85%] truncate text-[8px] opacity-45">{node.detail}</span> : null}
              {active ? <span className="absolute inset-[-7px] rounded-full border border-current opacity-25" /> : null}
            </motion.button>
          );
        })}
      </motion.div>

      <div className="absolute right-4 bottom-4 left-4 z-30 flex items-center justify-between gap-4 text-[9px] text-neutral-700">
        <span className="flex items-center gap-2"><RefreshCw className="h-3 w-3" />{t("liveTopology")}</span>
        <button type="button" onClick={onReset} className="focus-ring inline-flex items-center gap-2 text-neutral-600 hover:text-white"><RotateCcw className="h-3 w-3" />{t("backToSystem")}</button>
      </div>
    </section>
  );
}
