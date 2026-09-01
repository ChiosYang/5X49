"use client";

import { AnimatePresence, motion } from "framer-motion";
import {
  Aperture,
  ArrowLeft,
  Check,
  CheckCircle2,
  Clapperboard,
  Crosshair,
  Eye,
  FileSearch,
  Film,
  FolderInput,
  GitBranch,
  Layers3,
  MousePointer2,
  Orbit,
  Play,
  RotateCcw,
  ScanSearch,
  Sparkles,
  Star,
  WandSparkles,
  Zap,
} from "lucide-react";
import { useMemo, useState } from "react";

import { Link } from "@/i18n/routing";

type VisualModelId = "focus" | "timeline" | "constellation";

type VisualModel = {
  id: VisualModelId;
  index: string;
  degree: string;
  name: string;
  metaphor: string;
  description: string;
  icon: typeof Aperture;
  accent: string;
  selected: string;
};

const visualModels: VisualModel[] = [
  {
    id: "focus",
    index: "01",
    degree: "轻创新",
    name: "聚焦镜头",
    metaphor: "一次只让一件事占据画面",
    description: "用景深、转场和镜头序列代替传统卡片墙。",
    icon: Aperture,
    accent: "text-lime-300",
    selected: "border-lime-300/40 bg-lime-300/[0.07]",
  },
  {
    id: "timeline",
    index: "02",
    degree: "中创新",
    name: "电影剪辑台",
    metaphor: "把维护工作看成一条可剪辑的流程",
    description: "任务成为时间线片段，可定位、预览并逐段执行。",
    icon: Clapperboard,
    accent: "text-orange-300",
    selected: "border-orange-300/40 bg-orange-300/[0.07]",
  },
  {
    id: "constellation",
    index: "03",
    degree: "高创新",
    name: "媒体星图",
    metaphor: "用空间关系表达系统关系",
    description: "影片、文件与服务成为节点，异常直接改变拓扑。",
    icon: Orbit,
    accent: "text-cyan-300",
    selected: "border-cyan-300/40 bg-cyan-300/[0.07]",
  },
];

const easing = [0.2, 0, 0, 1] as const;

function LabFrame({
  title,
  overline,
  children,
  hint,
}: {
  title: string;
  overline: string;
  children: React.ReactNode;
  hint: string;
}) {
  return (
    <section className="overflow-hidden border border-white/10 bg-[#050505] shadow-[0_32px_100px_rgba(0,0,0,0.65)]">
      <header className="flex flex-col gap-3 border-b border-white/10 px-5 py-5 sm:flex-row sm:items-end sm:justify-between sm:px-7">
        <div>
          <p className="text-[9px] font-black tracking-[0.26em] text-neutral-600 uppercase">{overline}</p>
          <h2 className="mt-2 text-xl font-semibold tracking-tight text-white sm:text-2xl">{title}</h2>
        </div>
        <p className="flex items-center gap-2 text-[10px] text-neutral-600"><MousePointer2 className="h-3 w-3" /> {hint}</p>
      </header>
      {children}
    </section>
  );
}

type FocusTask = {
  id: string;
  overline: string;
  title: string;
  description: string;
  count: string;
  action: string;
  icon: typeof ScanSearch;
  color: string;
  glow: string;
};

const focusTasks: FocusTask[] = [
  {
    id: "scan",
    overline: "场景 01 · 发现",
    title: "让新加入的影片进入视野",
    description: "系统发现 4 个尚未被资料库认识的文件。先建立索引，不移动任何文件。",
    count: "04",
    action: "建立索引",
    icon: ScanSearch,
    color: "text-lime-300",
    glow: "bg-lime-300",
  },
  {
    id: "match",
    overline: "场景 02 · 辨认",
    title: "确认一部同名电影的身份",
    description: "《花样年华》出现两个候选结果。海报、年份和导演会在下一镜中并置比较。",
    count: "01",
    action: "进入比对",
    icon: FileSearch,
    color: "text-sky-300",
    glow: "bg-sky-300",
  },
  {
    id: "organize",
    overline: "场景 03 · 归位",
    title: "把散落的文件送回正确位置",
    description: "3 个视频停留在根目录。预览目标位置后，可以让它们依次归入影片文件夹。",
    count: "03",
    action: "预演归位",
    icon: FolderInput,
    color: "text-violet-300",
    glow: "bg-violet-300",
  },
];

function FocusLensModel() {
  const [activeIndex, setActiveIndex] = useState(0);
  const [completed, setCompleted] = useState<string[]>([]);
  const active = focusTasks[activeIndex];
  const allDone = completed.length === focusTasks.length;

  const completeActive = () => {
    if (!completed.includes(active.id)) setCompleted((current) => [...current, active.id]);
    const nextIndex = focusTasks.findIndex((task, index) => index > activeIndex && !completed.includes(task.id));
    if (nextIndex >= 0) setActiveIndex(nextIndex);
    else {
      const firstOpen = focusTasks.findIndex((task) => task.id !== active.id && !completed.includes(task.id));
      if (firstOpen >= 0) setActiveIndex(firstOpen);
    }
  };

  return (
    <LabFrame title="聚焦镜头" overline="Visual model 01 · Depth & sequence" hint="点击下方镜号切换当前任务">
      <div className="relative min-h-[39rem] overflow-hidden bg-[radial-gradient(circle_at_50%_45%,rgba(163,230,53,0.10),transparent_33%),linear-gradient(to_bottom,#070707,#020202)]">
        <div className="pointer-events-none absolute inset-0 opacity-[0.06] [background-image:linear-gradient(rgba(255,255,255,.35)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,.35)_1px,transparent_1px)] [background-size:64px_64px]" />
        <div className="pointer-events-none absolute top-1/2 left-1/2 h-[28rem] w-[28rem] -translate-x-1/2 -translate-y-1/2 rounded-full border border-white/[0.04] sm:h-[34rem] sm:w-[34rem]" />
        <div className="pointer-events-none absolute top-1/2 left-1/2 h-[20rem] w-[20rem] -translate-x-1/2 -translate-y-1/2 rounded-full border border-dashed border-white/[0.05] sm:h-[25rem] sm:w-[25rem]" />

        <div className="relative z-10 flex min-h-[39rem] flex-col px-5 py-7 sm:px-8 sm:py-9">
          <div className="flex items-center justify-between gap-4">
            <div className="flex items-center gap-3 text-[10px] font-bold tracking-[0.16em] text-neutral-600 uppercase">
              <span className="relative flex h-2 w-2">
                <span className={`absolute inline-flex h-full w-full animate-ping rounded-full opacity-30 ${active.glow}`} />
                <span className={`relative inline-flex h-2 w-2 rounded-full ${active.glow}`} />
              </span>
              Live focus
            </div>
            <p className="text-[10px] text-neutral-700">{completed.length} / {focusTasks.length} 已完成</p>
          </div>

          <div className="flex flex-1 items-center justify-center py-10">
            <AnimatePresence mode="wait">
              <motion.article
                key={active.id}
                initial={{ opacity: 0, scale: 0.94, filter: "blur(10px)" }}
                animate={{ opacity: 1, scale: 1, filter: "blur(0px)" }}
                exit={{ opacity: 0, scale: 1.04, filter: "blur(8px)" }}
                transition={{ duration: 0.42, ease: easing }}
                className="relative w-full max-w-3xl px-2 text-center sm:px-10"
              >
                <span className="absolute -top-10 -left-1 text-[7rem] font-black leading-none tracking-[-0.08em] text-white/[0.025] sm:-top-20 sm:text-[13rem]">{String(activeIndex + 1).padStart(2, "0")}</span>
                <div className={`mx-auto flex h-12 w-12 items-center justify-center rounded-full border border-white/10 bg-black/50 ${active.color}`}>
                  <active.icon className="h-5 w-5" />
                </div>
                <p className={`mt-6 text-[10px] font-black tracking-[0.22em] uppercase ${active.color}`}>{active.overline}</p>
                <h3 className="mx-auto mt-4 max-w-2xl text-3xl font-semibold leading-tight tracking-[-0.04em] text-white sm:text-5xl">{active.title}</h3>
                <p className="mx-auto mt-5 max-w-xl text-xs leading-6 text-neutral-500 sm:text-sm">{active.description}</p>
                <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
                  <button type="button" className="focus-ring min-h-11 border border-white/15 px-5 text-[10px] font-bold tracking-[0.15em] text-neutral-400 uppercase transition hover:bg-white/5 hover:text-white">
                    预览这一镜
                  </button>
                  <button
                    type="button"
                    onClick={completeActive}
                    disabled={completed.includes(active.id)}
                    className={`focus-ring inline-flex min-h-11 items-center gap-2 px-6 text-[10px] font-black tracking-[0.15em] text-black uppercase transition disabled:opacity-50 ${active.glow}`}
                  >
                    {completed.includes(active.id) ? <Check className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}
                    {completed.includes(active.id) ? "这一镜已完成" : active.action}
                  </button>
                </div>
              </motion.article>
            </AnimatePresence>
          </div>

          <div className="grid gap-2 sm:grid-cols-3">
            {focusTasks.map((task, index) => {
              const selected = index === activeIndex;
              const done = completed.includes(task.id);
              return (
                <button
                  key={task.id}
                  type="button"
                  onClick={() => setActiveIndex(index)}
                  className={`focus-ring group flex items-center gap-3 border px-4 py-3 text-left transition ${selected ? "border-white/25 bg-white/[0.06]" : "border-white/[0.07] bg-black/30 hover:border-white/15"}`}
                >
                  <span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full border text-[9px] font-black ${done ? "border-emerald-300 bg-emerald-300 text-black" : selected ? `border-white/20 ${task.color}` : "border-white/10 text-neutral-700"}`}>
                    {done ? <Check className="h-3 w-3" /> : String(index + 1).padStart(2, "0")}
                  </span>
                  <span className="min-w-0">
                    <span className={`block truncate text-[10px] font-semibold ${selected ? "text-white" : "text-neutral-600 group-hover:text-neutral-400"}`}>{task.title}</span>
                    <span className="mt-1 block text-[9px] text-neutral-700">{task.count} 个对象</span>
                  </span>
                </button>
              );
            })}
          </div>
          {allDone ? <p className="mt-4 text-center text-[10px] font-bold tracking-[0.16em] text-emerald-300 uppercase"><CheckCircle2 className="mr-1.5 inline h-3.5 w-3.5" /> 今日片单已经收工</p> : null}
        </div>
      </div>
    </LabFrame>
  );
}

type TimelineClip = {
  id: string;
  row: number;
  column: number;
  span: number;
  title: string;
  meta: string;
  before: string;
  after: string;
  tone: string;
};

const timelineClips: TimelineClip[] = [
  { id: "discover", row: 0, column: 2, span: 3, title: "扫描新增文件", meta: "4 个对象", before: "未进入资料库", after: "建立基础索引", tone: "border-lime-300/35 bg-lime-300/10 text-lime-200" },
  { id: "identify", row: 1, column: 4, span: 4, title: "补全媒体信息", meta: "12 部影片", before: "仅有文件名", after: "海报、演职员与类型", tone: "border-sky-300/35 bg-sky-300/10 text-sky-200" },
  { id: "review", row: 1, column: 8, span: 2, title: "同名审核", meta: "1 个决定", before: "两个候选结果", after: "锁定 2000 年版本", tone: "border-amber-300/40 bg-amber-300/10 text-amber-200" },
  { id: "organize", row: 2, column: 6, span: 4, title: "整理目录", meta: "3 个文件", before: "停留在根目录", after: "归入标准影片目录", tone: "border-violet-300/35 bg-violet-300/10 text-violet-200" },
  { id: "scores", row: 3, column: 9, span: 4, title: "刷新评分", meta: "12 部影片", before: "评分已过期", after: "同步最新外部评分", tone: "border-rose-300/35 bg-rose-300/10 text-rose-200" },
];

const trackNames = ["采集轨", "识别轨", "文件轨", "增强轨"];

function TimelineModel() {
  const [selectedId, setSelectedId] = useState("identify");
  const [completed, setCompleted] = useState<string[]>(["discover"]);
  const selected = timelineClips.find((clip) => clip.id === selectedId) ?? timelineClips[1];
  const playhead = Math.min(100, ((selected.column + selected.span - 2) / 12) * 100);

  const executeClip = () => {
    if (!completed.includes(selected.id)) setCompleted((current) => [...current, selected.id]);
    const currentIndex = timelineClips.findIndex((clip) => clip.id === selected.id);
    const next = timelineClips.slice(currentIndex + 1).find((clip) => !completed.includes(clip.id));
    if (next) setSelectedId(next.id);
  };

  return (
    <LabFrame title="电影剪辑台" overline="Visual model 02 · Timeline & scrubber" hint="点击彩色片段查看前后变化">
      <div className="bg-[#080706]">
        <div className="flex flex-col gap-5 border-b border-white/10 px-5 py-5 sm:flex-row sm:items-center sm:justify-between sm:px-7">
          <div className="flex items-center gap-4">
            <span className="flex h-9 w-9 items-center justify-center rounded-sm bg-orange-300 text-black"><Clapperboard className="h-4 w-4" /></span>
            <div>
              <p className="text-xs font-semibold text-white">今日维护剪辑</p>
              <p className="mt-1 text-[10px] text-neutral-600">5 个片段 · 预计 01:42</p>
            </div>
          </div>
          <div className="flex items-center gap-4 text-[10px] text-neutral-600">
            <span><strong className="mr-1 text-white">{completed.length}</strong> 已成片</span>
            <span><strong className="mr-1 text-orange-300">{timelineClips.length - completed.length}</strong> 待剪辑</span>
          </div>
        </div>

        <div className="overflow-x-auto border-b border-white/10 scrollbar-minimal">
          <div className="relative min-w-[56rem] px-5 py-6 sm:px-7">
            <div className="mb-3 grid grid-cols-[6rem_repeat(12,minmax(3.25rem,1fr))] text-[9px] text-neutral-700">
              <span />
              {Array.from({ length: 12 }, (_, index) => <span key={index} className="border-l border-white/[0.05] pl-2">{String(index * 10).padStart(2, "0")}</span>)}
            </div>
            <div className="relative">
              <div className="pointer-events-none absolute top-0 bottom-0 z-20 w-px bg-orange-300 shadow-[0_0_12px_rgba(253,186,116,.65)]" style={{ left: `calc(6rem + (100% - 6rem) * ${playhead / 100})` }}>
                <span className="absolute -top-1.5 left-1/2 h-2.5 w-2.5 -translate-x-1/2 rotate-45 bg-orange-300" />
              </div>
              {trackNames.map((track, row) => (
                <div key={track} className="grid min-h-20 grid-cols-[6rem_repeat(12,minmax(3.25rem,1fr))] items-center border-t border-white/[0.07] last:border-b">
                  <div className="pr-4 text-[9px] font-bold tracking-[0.16em] text-neutral-600 uppercase">{track}</div>
                  {Array.from({ length: 12 }, (_, index) => <span key={index} className="h-full border-l border-white/[0.035]" style={{ gridColumn: index + 2, gridRow: 1 }} />)}
                  {timelineClips.filter((clip) => clip.row === row).map((clip) => {
                    const isSelected = clip.id === selected.id;
                    const done = completed.includes(clip.id);
                    return (
                      <motion.button
                        layout
                        key={clip.id}
                        type="button"
                        onClick={() => setSelectedId(clip.id)}
                        style={{ gridColumn: `${clip.column} / span ${clip.span}`, gridRow: 1 }}
                        className={`focus-ring relative z-10 mx-1 min-w-0 border px-3 py-3 text-left transition ${clip.tone} ${isSelected ? "translate-y-[-2px] shadow-[0_8px_24px_rgba(0,0,0,.45)] ring-1 ring-white/20" : "opacity-70 hover:opacity-100"}`}
                      >
                        <span className="flex items-center justify-between gap-2">
                          <span className="truncate text-[10px] font-bold">{clip.title}</span>
                          {done ? <Check className="h-3 w-3 shrink-0" /> : null}
                        </span>
                        <span className="mt-1 block truncate text-[9px] opacity-50">{clip.meta}</span>
                        <span className="absolute top-1/2 -left-0.5 h-4 w-1 -translate-y-1/2 rounded-full bg-current opacity-40" />
                        <span className="absolute top-1/2 -right-0.5 h-4 w-1 -translate-y-1/2 rounded-full bg-current opacity-40" />
                      </motion.button>
                    );
                  })}
                </div>
              ))}
            </div>
          </div>
        </div>

        <AnimatePresence mode="wait">
          <motion.div key={selected.id} initial={{ opacity: 0, y: 5 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -4 }} transition={{ duration: 0.2, ease: easing }} className="grid lg:grid-cols-[minmax(0,1fr)_auto]">
            <div className="grid gap-px bg-white/10 sm:grid-cols-2">
              <div className="bg-[#080706] p-5 sm:p-7">
                <p className="flex items-center gap-2 text-[9px] font-black tracking-[0.18em] text-neutral-600 uppercase"><Eye className="h-3 w-3" /> 入点 · Before</p>
                <p className="mt-3 text-sm font-semibold text-neutral-300">{selected.before}</p>
              </div>
              <div className="bg-[#080706] p-5 sm:p-7">
                <p className="flex items-center gap-2 text-[9px] font-black tracking-[0.18em] text-orange-300 uppercase"><Sparkles className="h-3 w-3" /> 出点 · After</p>
                <p className="mt-3 text-sm font-semibold text-white">{selected.after}</p>
              </div>
            </div>
            <div className="flex min-w-64 flex-col justify-center border-t border-white/10 p-5 lg:border-t-0 lg:border-l lg:p-7">
              <p className="text-[10px] text-neutral-600">当前片段</p>
              <p className="mt-1 text-sm font-semibold text-white">{selected.title}</p>
              <button
                type="button"
                onClick={executeClip}
                disabled={completed.includes(selected.id)}
                className="focus-ring mt-4 inline-flex min-h-10 items-center justify-center gap-2 bg-orange-300 px-5 text-[10px] font-black tracking-[0.14em] text-black uppercase transition hover:bg-orange-200 disabled:opacity-40"
              >
                {completed.includes(selected.id) ? <Check className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}
                {completed.includes(selected.id) ? "片段已完成" : "执行这一段"}
              </button>
            </div>
          </motion.div>
        </AnimatePresence>
      </div>
    </LabFrame>
  );
}

type StarNode = {
  id: string;
  label: string;
  meta: string;
  x: number;
  y: number;
  size: "sm" | "md" | "lg";
  kind: "film" | "file" | "service" | "exception";
  detail: string;
};

const starNodes: StarNode[] = [
  { id: "library", label: "主资料库", meta: "248 部影片", x: 50, y: 50, size: "lg", kind: "service", detail: "所有已整理影片的中心索引。" },
  { id: "mood", label: "花样年华", meta: "待确认身份", x: 28, y: 28, size: "md", kind: "exception", detail: "同名候选造成识别分叉，需要确认 2000 年王家卫版本。" },
  { id: "chungking", label: "重庆森林", meta: "根目录文件", x: 73, y: 22, size: "md", kind: "file", detail: "文件已经稳定，可以接入主资料库并建立标准目录。" },
  { id: "scores", label: "外部评分", meta: "12 个过期", x: 78, y: 65, size: "md", kind: "service", detail: "12 部影片的评分超过 30 天没有更新。" },
  { id: "poster", label: "海报资源", meta: "3 个缺失", x: 30, y: 74, size: "sm", kind: "service", detail: "有 3 部影片缺少纵向海报，但不影响播放。" },
  { id: "fallen", label: "堕落天使", meta: "已连接", x: 13, y: 51, size: "sm", kind: "film", detail: "文件、媒体信息和评分均已与主资料库连接。" },
  { id: "happy", label: "春光乍泄", meta: "已连接", x: 88, y: 44, size: "sm", kind: "film", detail: "所有资料完整，当前不需要维护。" },
];

const starEdges = [
  ["library", "mood"],
  ["library", "chungking"],
  ["library", "scores"],
  ["library", "poster"],
  ["library", "fallen"],
  ["library", "happy"],
] as const;

function ConstellationModel() {
  const [selectedId, setSelectedId] = useState("mood");
  const [resolved, setResolved] = useState<string[]>([]);
  const [filter, setFilter] = useState<"all" | "exceptions">("all");
  const selected = starNodes.find((node) => node.id === selectedId) ?? starNodes[1];
  const nodeById = useMemo(() => new Map(starNodes.map((node) => [node.id, node])), []);

  const visibleNode = (node: StarNode) => filter === "all" || node.kind === "exception" || node.kind === "file" || node.id === "library";
  const resolveSelected = () => {
    if (selected.id === "library") return;
    if (!resolved.includes(selected.id)) setResolved((current) => [...current, selected.id]);
  };

  const nodeTone = (node: StarNode) => {
    if (resolved.includes(node.id)) return "border-emerald-300/50 bg-emerald-300/15 text-emerald-200";
    if (node.kind === "exception") return "border-amber-300/60 bg-amber-300/15 text-amber-200 shadow-[0_0_35px_rgba(252,211,77,.12)]";
    if (node.kind === "file") return "border-violet-300/50 bg-violet-300/10 text-violet-200";
    if (node.kind === "service") return "border-cyan-300/35 bg-cyan-300/[0.08] text-cyan-200";
    return "border-white/15 bg-white/[0.05] text-neutral-300";
  };

  return (
    <LabFrame title="媒体星图" overline="Visual model 03 · Spatial topology" hint="点击节点观察关系，不再按模块浏览">
      <div className="grid bg-[#030608] lg:grid-cols-[minmax(0,1fr)_21rem]">
        <div className="relative min-h-[34rem] overflow-hidden border-b border-white/10 lg:border-r lg:border-b-0">
          <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(34,211,238,.10),transparent_22%),radial-gradient(circle_at_25%_30%,rgba(251,191,36,.05),transparent_18%)]" />
          <div className="pointer-events-none absolute inset-0 opacity-30 [background-image:radial-gradient(rgba(255,255,255,.22)_0.6px,transparent_0.6px)] [background-size:24px_24px]" />
          <div className="absolute top-5 left-5 z-20 flex items-center gap-1 border border-white/10 bg-black/50 p-1 backdrop-blur-sm">
            {[
              { id: "all" as const, label: "完整星图" },
              { id: "exceptions" as const, label: "只看异常" },
            ].map((item) => (
              <button key={item.id} type="button" onClick={() => setFilter(item.id)} className={`focus-ring px-3 py-2 text-[9px] font-bold tracking-wider uppercase transition ${filter === item.id ? "bg-cyan-300 text-black" : "text-neutral-600 hover:text-white"}`}>{item.label}</button>
            ))}
          </div>
          <div className="absolute top-6 right-5 z-20 flex items-center gap-2 text-[9px] text-neutral-700"><Crosshair className="h-3 w-3" /> 拓扑实时更新</div>

          <svg aria-hidden="true" className="pointer-events-none absolute inset-0 h-full w-full">
            <defs>
              <linearGradient id="star-line" x1="0" x2="1">
                <stop offset="0" stopColor="rgb(34 211 238)" stopOpacity="0.04" />
                <stop offset="0.5" stopColor="rgb(34 211 238)" stopOpacity="0.28" />
                <stop offset="1" stopColor="rgb(255 255 255)" stopOpacity="0.04" />
              </linearGradient>
            </defs>
            {starEdges.map(([fromId, toId]) => {
              const from = nodeById.get(fromId)!;
              const to = nodeById.get(toId)!;
              const hidden = !visibleNode(from) || !visibleNode(to);
              return <motion.line key={`${fromId}-${toId}`} x1={`${from.x}%`} y1={`${from.y}%`} x2={`${to.x}%`} y2={`${to.y}%`} stroke="url(#star-line)" strokeWidth={selectedId === toId ? 1.5 : 0.75} animate={{ opacity: hidden ? 0.05 : selectedId === toId ? 1 : 0.5 }} />;
            })}
          </svg>

          {starNodes.map((node) => {
            const selectedNode = node.id === selectedId;
            const visible = visibleNode(node);
            const sizeClass = node.size === "lg" ? "h-24 w-24 sm:h-28 sm:w-28" : node.size === "md" ? "h-16 w-16 sm:h-20 sm:w-20" : "h-11 w-11 sm:h-14 sm:w-14";
            return (
              <motion.button
                key={node.id}
                type="button"
                aria-label={`${node.label}，${node.meta}`}
                onClick={() => setSelectedId(node.id)}
                animate={{ opacity: visible ? 1 : 0.12, scale: selectedNode ? 1.12 : 1 }}
                whileHover={{ scale: selectedNode ? 1.12 : 1.06 }}
                transition={{ duration: 0.26, ease: easing }}
                style={{ left: `${node.x}%`, top: `${node.y}%` }}
                className={`focus-ring absolute z-10 -translate-x-1/2 -translate-y-1/2 rounded-full border backdrop-blur-sm ${sizeClass} ${nodeTone(node)} ${selectedNode ? "ring-1 ring-white/30" : ""}`}
              >
                {selectedNode ? <span className="absolute inset-[-7px] animate-pulse rounded-full border border-current opacity-25" /> : null}
                <span className={`mx-auto block font-black ${node.size === "lg" ? "text-xs" : "text-[9px]"}`}>{node.label}</span>
                {node.size !== "sm" ? <span className="mt-1 block text-[8px] opacity-50">{node.meta}</span> : null}
                {resolved.includes(node.id) ? <span className="absolute -right-0.5 -bottom-0.5 flex h-5 w-5 items-center justify-center rounded-full bg-emerald-300 text-black"><Check className="h-3 w-3" /></span> : null}
              </motion.button>
            );
          })}

          <div className="absolute right-5 bottom-5 left-5 flex items-center justify-between gap-4 text-[9px] text-neutral-700">
            <span className="flex items-center gap-2"><GitBranch className="h-3 w-3" /> 连线代表依赖关系</span>
            <span>{starNodes.length} 节点 · {starEdges.length} 连接</span>
          </div>
        </div>

        <AnimatePresence mode="wait">
          <motion.aside key={selected.id} initial={{ opacity: 0, x: 7 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -5 }} transition={{ duration: 0.2, ease: easing }} className="flex min-h-[25rem] flex-col p-6 sm:p-8">
            <div className="flex items-center justify-between">
              <p className="text-[9px] font-black tracking-[0.18em] text-cyan-300 uppercase">节点检查器</p>
              <span className="text-[9px] text-neutral-700">{selected.x.toFixed(0)}:{selected.y.toFixed(0)}</span>
            </div>
            <div className="mt-8 flex h-11 w-11 items-center justify-center rounded-full border border-white/10 text-cyan-300">
              {selected.kind === "film" ? <Film className="h-4 w-4" /> : selected.kind === "file" ? <FolderInput className="h-4 w-4" /> : selected.kind === "exception" ? <Zap className="h-4 w-4" /> : <Layers3 className="h-4 w-4" />}
            </div>
            <p className="mt-5 text-xl font-semibold tracking-tight text-white">{selected.label}</p>
            <p className="mt-1 text-[10px] text-neutral-600">{selected.meta}</p>
            <p className="mt-5 text-xs leading-6 text-neutral-400">{selected.detail}</p>

            <div className="mt-6 space-y-3 border-t border-white/10 pt-5 text-[10px]">
              <div className="flex items-center justify-between"><span className="text-neutral-700">与主库距离</span><span className="text-neutral-400">{selected.id === "library" ? "中心" : "1 跳"}</span></div>
              <div className="flex items-center justify-between"><span className="text-neutral-700">关系状态</span><span className={resolved.includes(selected.id) ? "text-emerald-300" : selected.kind === "exception" ? "text-amber-200" : "text-neutral-400"}>{resolved.includes(selected.id) ? "已修复" : selected.kind === "exception" ? "分叉" : "已识别"}</span></div>
            </div>

            <div className="mt-auto pt-8">
              <button
                type="button"
                disabled={selected.id === "library" || resolved.includes(selected.id)}
                onClick={resolveSelected}
                className="focus-ring inline-flex min-h-11 w-full items-center justify-center gap-2 bg-cyan-300 px-5 text-[10px] font-black tracking-[0.14em] text-black uppercase transition hover:bg-cyan-200 disabled:opacity-35"
              >
                {resolved.includes(selected.id) ? <Check className="h-3.5 w-3.5" /> : <Orbit className="h-3.5 w-3.5" />}
                {resolved.includes(selected.id) ? "节点已经稳定" : selected.kind === "exception" ? "合并这条分叉" : "接入主轨道"}
              </button>
            </div>
          </motion.aside>
        </AnimatePresence>
      </div>
    </LabFrame>
  );
}

function ConceptReadout({ model }: { model: VisualModel }) {
  const details: Record<VisualModelId, { shift: string; delight: string; caution: string }> = {
    focus: {
      shift: "从总览找入口，变成沿镜头序列处理。",
      delight: "视觉噪音最少，任务之间的转场有完成感。",
      caution: "全局状态被弱化，需要保留快速跳镜能力。",
    },
    timeline: {
      shift: "从模块分区，变成跨模块的可视化时间线。",
      delight: "前后关系和并行工作一眼可见，符合电影产品语境。",
      caution: "小屏需要横向浏览，任务过多时必须支持缩放与折叠轨道。",
    },
    constellation: {
      shift: "从清单阅读，变成理解对象之间的空间拓扑。",
      delight: "异常不再只是红点，而是肉眼可见的断裂、分叉与孤岛。",
      caution: "需要稳定的空间布局，否则节点移动会破坏用户的空间记忆。",
    },
  };
  const detail = details[model.id];
  return (
    <div className="mt-5 grid gap-px border border-white/10 bg-white/10 md:grid-cols-3">
      {[
        ["交互转变", detail.shift],
        ["创新价值", detail.delight],
        ["设计约束", detail.caution],
      ].map(([label, text]) => (
        <div key={label} className="bg-black p-5">
          <p className={`text-[9px] font-black tracking-[0.18em] uppercase ${model.accent}`}>{label}</p>
          <p className="mt-2 text-xs leading-5 text-neutral-500">{text}</p>
        </div>
      ))}
    </div>
  );
}

export default function VisualInteractionLab() {
  const [activeModel, setActiveModel] = useState<VisualModelId>("timeline");
  const [resetKey, setResetKey] = useState(0);
  const active = visualModels.find((model) => model.id === activeModel) ?? visualModels[1];

  return (
    <div className="min-h-screen bg-black text-white selection:bg-cyan-300 selection:text-black">
      <header className="page-x relative overflow-hidden border-b border-white/10 pt-32 pb-10 sm:pt-36 sm:pb-12">
        <div className="pointer-events-none absolute top-0 left-1/2 h-72 w-[60rem] -translate-x-1/2 bg-[radial-gradient(ellipse_at_top,rgba(34,211,238,.09),transparent_65%)]" />
        <div className="relative mx-auto max-w-[90rem]">
          <Link href="/library/manage/concepts" className="focus-ring inline-flex items-center gap-2 text-[9px] font-black tracking-[0.18em] text-neutral-600 uppercase transition hover:text-white"><ArrowLeft className="h-3 w-3" /> 返回流程交互实验</Link>
          <div className="mt-6 flex flex-col gap-7 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <p className="flex items-center gap-2 text-[10px] font-black tracking-[0.24em] text-cyan-300 uppercase"><WandSparkles className="h-3.5 w-3.5" /> Visual interaction lab</p>
              <h1 className="mt-5 max-w-5xl text-4xl font-bold tracking-[-0.045em] text-white sm:text-6xl lg:text-7xl">不是换皮，<span className="font-serif font-normal text-neutral-500 italic">是换一种空间。</span></h1>
              <p className="mt-5 max-w-2xl text-sm leading-6 text-neutral-500">三种方案拥有相同的数据、权限与任务，只改变任务如何占据屏幕，以及用户如何在它们之间移动。</p>
            </div>
            <div className="border border-white/10 bg-white/[0.02] px-4 py-3 text-[10px] text-neutral-500">
              <span className="text-white">固定变量</span> · 相同任务 / 相同权限 / 相同风险
            </div>
          </div>
        </div>
      </header>

      <main className="page-x py-8 sm:py-10">
        <div className="mx-auto max-w-[90rem]">
          <div className="grid gap-3 lg:grid-cols-3" role="tablist" aria-label="视觉交互模型">
            {visualModels.map((model) => {
              const Icon = model.icon;
              const selected = activeModel === model.id;
              return (
                <button
                  key={model.id}
                  type="button"
                  role="tab"
                  aria-selected={selected}
                  onClick={() => {
                    setActiveModel(model.id);
                    setResetKey((current) => current + 1);
                  }}
                  className={`focus-ring group border p-5 text-left transition ${selected ? model.selected : "border-white/10 bg-[#050505] hover:border-white/20"}`}
                >
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <p className={`text-[9px] font-black tracking-[0.18em] uppercase ${selected ? model.accent : "text-neutral-700"}`}>{model.index} · {model.degree}</p>
                      <p className="mt-2 text-lg font-semibold text-white">{model.name}</p>
                    </div>
                    <Icon className={`h-5 w-5 ${selected ? model.accent : "text-neutral-700 group-hover:text-neutral-500"}`} />
                  </div>
                  <p className="mt-4 text-xs font-medium text-neutral-300">{model.metaphor}</p>
                  <p className="mt-2 text-[10px] leading-4 text-neutral-600">{model.description}</p>
                </button>
              );
            })}
          </div>

          <div className="mt-7 flex items-center justify-between gap-4">
            <p className="flex items-center gap-2 text-[10px] text-neutral-600"><Crosshair className={`h-3.5 w-3.5 ${active.accent}`} /> 当前空间：{active.name}</p>
            <button type="button" onClick={() => setResetKey((current) => current + 1)} className="focus-ring inline-flex min-h-9 items-center gap-2 px-2 text-[9px] font-black tracking-[0.14em] text-neutral-600 uppercase transition hover:text-white"><RotateCcw className="h-3.5 w-3.5" /> 重置体验</button>
          </div>

          <div className="mt-3" role="tabpanel">
            <AnimatePresence mode="wait">
              <motion.div key={`${activeModel}-${resetKey}`} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -5 }} transition={{ duration: 0.22, ease: easing }}>
                {activeModel === "focus" ? <FocusLensModel /> : null}
                {activeModel === "timeline" ? <TimelineModel /> : null}
                {activeModel === "constellation" ? <ConstellationModel /> : null}
              </motion.div>
            </AnimatePresence>
          </div>

          <ConceptReadout model={active} />

          <footer className="flex flex-col gap-3 py-10 text-[10px] text-neutral-700 sm:flex-row sm:items-center sm:justify-between">
            <span>5X49 · Visual interaction study</span>
            <span className="flex items-center gap-2"><Star className="h-3 w-3" /> 判断标准：是否更快理解、是否更想继续操作、是否记得刚才发生了什么。</span>
          </footer>
        </div>
      </main>
    </div>
  );
}
