"use client";

import { AnimatePresence, motion } from "framer-motion";
import {
  AlertTriangle,
  ArrowRight,
  Bot,
  Check,
  CheckCircle2,
  ChevronDown,
  Circle,
  CircleDot,
  Command,
  FileCheck2,
  FileSearch,
  FolderCheck,
  Gauge,
  LayoutDashboard,
  ListChecks,
  Pause,
  Play,
  RefreshCw,
  RotateCcw,
  ScanSearch,
  ShieldCheck,
  Sparkles,
  Wand2,
  X,
  Zap,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

type ModelId = "safe" | "balanced" | "radical";

type ModelConfig = {
  id: ModelId;
  index: string;
  label: string;
  name: string;
  thesis: string;
  accent: string;
  accentSoft: string;
  icon: typeof LayoutDashboard;
  metrics: Array<{ label: string; value: string }>;
};

const models: ModelConfig[] = [
  {
    id: "safe",
    index: "01",
    label: "最保守",
    name: "状态面板",
    thesis: "用户看状态、选工具、逐项确认；把新风险控制在最低。",
    accent: "text-amber-200",
    accentSoft: "border-amber-200/30 bg-amber-200/8",
    icon: LayoutDashboard,
    metrics: [
      { label: "学习成本", value: "低" },
      { label: "处理效率", value: "中" },
      { label: "系统自主", value: "低" },
    ],
  },
  {
    id: "balanced",
    index: "02",
    label: "折中",
    name: "任务收件箱",
    thesis: "系统把状态翻译成待办；用户只处理下一件需要决策的事。",
    accent: "text-sky-300",
    accentSoft: "border-sky-300/30 bg-sky-300/8",
    icon: ListChecks,
    metrics: [
      { label: "学习成本", value: "中" },
      { label: "处理效率", value: "高" },
      { label: "系统自主", value: "中" },
    ],
  },
  {
    id: "radical",
    index: "03",
    label: "最激进",
    name: "目标驾驶舱",
    thesis: "用户声明结果和边界；系统编排流程，只在例外发生时打断。",
    accent: "text-violet-300",
    accentSoft: "border-violet-300/30 bg-violet-300/8",
    icon: Sparkles,
    metrics: [
      { label: "学习成本", value: "高" },
      { label: "处理效率", value: "极高" },
      { label: "系统自主", value: "高" },
    ],
  },
];

const panelTransition = { duration: 0.22, ease: [0.2, 0, 0, 1] as const };

function PrototypeFrame({
  children,
  eyebrow,
  title,
  description,
}: {
  children: React.ReactNode;
  eyebrow: string;
  title: string;
  description: string;
}) {
  return (
    <section className="overflow-hidden border border-white/10 bg-neutral-950 shadow-2xl shadow-black">
      <header className="flex flex-col gap-5 border-b border-white/10 px-5 py-5 sm:px-7 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-[10px] font-black tracking-[0.24em] text-neutral-500 uppercase">{eyebrow}</p>
          <h2 className="mt-2 text-2xl font-bold tracking-tight text-white sm:text-3xl">{title}</h2>
        </div>
        <p className="max-w-xl text-xs leading-5 text-neutral-500 lg:text-right">{description}</p>
      </header>
      {children}
    </section>
  );
}

function StatusDot({ tone }: { tone: "ok" | "busy" | "idle" | "warning" }) {
  const toneClass = {
    ok: "bg-emerald-400 shadow-emerald-400/40",
    busy: "bg-sky-300 shadow-sky-300/40 animate-pulse",
    idle: "bg-neutral-600",
    warning: "bg-amber-300 shadow-amber-300/40",
  }[tone];
  return <span className={`inline-block h-1.5 w-1.5 rounded-full shadow-[0_0_10px] ${toneClass}`} />;
}

function ConservativeModel() {
  const [scanState, setScanState] = useState<"idle" | "running" | "done">("idle");
  const [reviewOpen, setReviewOpen] = useState(false);
  const [candidate, setCandidate] = useState<"2046" | "confession" | null>(null);
  const [queueCount, setQueueCount] = useState(3);

  useEffect(() => {
    if (scanState !== "running") return;
    const timer = window.setTimeout(() => setScanState("done"), 1300);
    return () => window.clearTimeout(timer);
  }, [scanState]);

  const confirmCandidate = () => {
    if (!candidate) return;
    setQueueCount((current) => Math.max(0, current - 1));
    setCandidate(null);
    setReviewOpen(false);
  };

  return (
    <PrototypeFrame
      eyebrow="Model 01 · Familiar controls"
      title="管理状态面板"
      description="按系统模块分组。每个操作都有独立入口、状态反馈和显式确认，迁移成本最低。"
    >
      <div className="grid lg:grid-cols-[15rem_minmax(0,1fr)]">
        <aside className="border-b border-white/10 p-5 lg:border-r lg:border-b-0 lg:p-6">
          <p className="text-[10px] font-bold tracking-[0.2em] text-neutral-600 uppercase">系统状态</p>
          <div className="mt-5 grid grid-cols-2 gap-x-4 gap-y-5 text-xs lg:grid-cols-1">
            {[
              ["文件监控", "运行中", "ok"],
              ["媒体信息", `${queueCount} 项待审核`, queueCount ? "warning" : "ok"],
              ["外部评分", "8 分钟前", "ok"],
              ["文件整理", "空闲", "idle"],
            ].map(([label, value, tone]) => (
              <div key={label} className="flex items-start gap-3">
                <span className="mt-1.5"><StatusDot tone={tone as "ok" | "idle" | "warning"} /></span>
                <div className="min-w-0">
                  <p className="text-neutral-300">{label}</p>
                  <p className="mt-1 truncate text-[11px] text-neutral-600">{value}</p>
                </div>
              </div>
            ))}
          </div>
        </aside>

        <main className="p-5 sm:p-7">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="text-sm font-semibold text-white">今天的维护</p>
              <p className="mt-1 text-xs text-neutral-500">工具按熟悉的系统模块排列。</p>
            </div>
            <span className="inline-flex w-fit items-center gap-2 border border-emerald-400/20 bg-emerald-400/5 px-3 py-2 text-[10px] font-bold tracking-wider text-emerald-300 uppercase">
              <ShieldCheck className="h-3.5 w-3.5" /> 所有服务正常
            </span>
          </div>

          <div className="mt-7 grid gap-3 md:grid-cols-2">
            <article className="border border-white/10 bg-black p-5">
              <div className="flex items-start justify-between gap-4">
                <span className="flex h-9 w-9 items-center justify-center bg-white text-black"><ScanSearch className="h-4 w-4" /></span>
                <span className="text-[10px] text-neutral-600">上次：09:42</span>
              </div>
              <h3 className="mt-6 text-sm font-semibold text-white">扫描媒体库</h3>
              <p className="mt-2 text-xs leading-5 text-neutral-500">查找新增、变更或已删除的影片文件。</p>
              <button
                type="button"
                disabled={scanState === "running"}
                onClick={() => setScanState("running")}
                className="focus-ring mt-5 flex min-h-10 w-full items-center justify-center gap-2 bg-white px-4 text-[10px] font-black tracking-[0.16em] text-black uppercase transition hover:bg-neutral-200 disabled:cursor-wait disabled:opacity-60"
              >
                {scanState === "running" ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : scanState === "done" ? <Check className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}
                {scanState === "running" ? "扫描中" : scanState === "done" ? "扫描完成 · 再次运行" : "立即扫描"}
              </button>
            </article>

            <article className="border border-amber-200/20 bg-amber-200/[0.03] p-5">
              <div className="flex items-start justify-between gap-4">
                <span className="flex h-9 w-9 items-center justify-center bg-amber-200 text-black"><FileSearch className="h-4 w-4" /></span>
                <span className="rounded-full bg-amber-200/10 px-2 py-1 text-[10px] font-bold text-amber-200">{queueCount} 待处理</span>
              </div>
              <h3 className="mt-6 text-sm font-semibold text-white">审核媒体信息</h3>
              <p className="mt-2 text-xs leading-5 text-neutral-500">确认系统没有把影片匹配到错误条目。</p>
              <button
                type="button"
                onClick={() => setReviewOpen((current) => !current)}
                className="focus-ring mt-5 flex min-h-10 w-full items-center justify-center gap-2 border border-white/15 px-4 text-[10px] font-black tracking-[0.16em] text-white uppercase transition hover:bg-white/5"
              >
                打开审核 <ChevronDown className={`h-3.5 w-3.5 transition-transform ${reviewOpen ? "rotate-180" : ""}`} />
              </button>
            </article>

            <article className="border border-white/10 bg-black p-5 md:col-span-2">
              <div className="flex flex-col gap-5 sm:flex-row sm:items-center sm:justify-between">
                <div className="flex gap-4">
                  <span className="flex h-9 w-9 shrink-0 items-center justify-center border border-white/15 text-neutral-400"><FolderCheck className="h-4 w-4" /></span>
                  <div>
                    <h3 className="text-sm font-semibold text-white">文件整理</h3>
                    <p className="mt-1 text-xs leading-5 text-neutral-500">0 个文件需要移动，目录结构已符合规则。</p>
                  </div>
                </div>
                <button type="button" disabled className="min-h-9 border border-white/10 px-4 text-[10px] font-bold tracking-wider text-neutral-700 uppercase">无需操作</button>
              </div>
            </article>
          </div>
        </main>
      </div>

      <AnimatePresence>
        {reviewOpen ? (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-modal flex items-end justify-end bg-black/75 p-0 backdrop-blur-sm sm:p-5"
            onMouseDown={(event) => {
              if (event.currentTarget === event.target) setReviewOpen(false);
            }}
          >
            <motion.aside
              initial={{ x: 48, opacity: 0 }}
              animate={{ x: 0, opacity: 1 }}
              exit={{ x: 48, opacity: 0 }}
              transition={panelTransition}
              role="dialog"
              aria-modal="true"
              aria-label="媒体信息审核"
              className="max-h-[92vh] w-full overflow-y-auto border border-white/15 bg-neutral-950 p-6 shadow-2xl sm:max-w-lg"
            >
              <div className="flex items-start justify-between gap-6">
                <div>
                  <p className="text-[10px] font-bold tracking-[0.2em] text-amber-200 uppercase">1 / {queueCount}</p>
                  <h3 className="mt-2 text-xl font-semibold text-white">花样年华 (2000)</h3>
                  <p className="mt-1 text-xs text-neutral-500">In.the.Mood.for.Love.2000.mkv</p>
                </div>
                <button type="button" onClick={() => setReviewOpen(false)} aria-label="关闭审核" className="focus-ring p-2 text-neutral-500 hover:text-white"><X className="h-4 w-4" /></button>
              </div>
              <div className="mt-7 space-y-3">
                {[
                  { id: "2046" as const, title: "花样年华", meta: "2000 · 王家卫 · 98% 匹配" },
                  { id: "confession" as const, title: "花样年华", meta: "1983 · 黄蜀芹 · 71% 匹配" },
                ].map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => setCandidate(item.id)}
                    className={`focus-ring flex w-full items-center justify-between gap-4 border p-4 text-left transition ${candidate === item.id ? "border-amber-200 bg-amber-200/8" : "border-white/10 hover:border-white/25"}`}
                  >
                    <span>
                      <span className="block text-sm font-semibold text-white">{item.title}</span>
                      <span className="mt-1 block text-[11px] text-neutral-500">{item.meta}</span>
                    </span>
                    {candidate === item.id ? <CheckCircle2 className="h-4 w-4 shrink-0 text-amber-200" /> : <Circle className="h-4 w-4 shrink-0 text-neutral-700" />}
                  </button>
                ))}
              </div>
              <button
                type="button"
                disabled={!candidate}
                onClick={confirmCandidate}
                className="focus-ring mt-6 min-h-11 w-full bg-amber-200 px-4 text-[10px] font-black tracking-[0.16em] text-black uppercase transition hover:bg-amber-100 disabled:cursor-not-allowed disabled:opacity-30"
              >
                确认匹配并继续
              </button>
            </motion.aside>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </PrototypeFrame>
  );
}

type InboxItem = {
  id: string;
  type: "decision" | "routine";
  title: string;
  meta: string;
  description: string;
  suggestion: string;
};

const initialInbox: InboxItem[] = [
  {
    id: "metadata",
    type: "decision",
    title: "确认《花样年华》匹配",
    meta: "媒体信息 · 98% 可信度",
    description: "文件名与 2000 年王家卫电影高度吻合，但库中存在一个同名条目。",
    suggestion: "采用 2000 年版本",
  },
  {
    id: "orphan",
    type: "decision",
    title: "处理根目录中的视频",
    meta: "文件整理 · 1.8 GB",
    description: "检测到 Chungking.Express.1994.mkv，可以移动到标准影片目录。",
    suggestion: "创建《重庆森林 (1994)》目录",
  },
  {
    id: "scores",
    type: "routine",
    title: "更新 12 部影片的外部评分",
    meta: "日常任务 · 约 20 秒",
    description: "这些影片的评分已超过 30 天没有更新，此操作不会修改本地媒体文件。",
    suggestion: "立即更新全部评分",
  },
];

function BalancedModel() {
  const [items, setItems] = useState(initialInbox);
  const [activeId, setActiveId] = useState(initialInbox[0].id);
  const [handled, setHandled] = useState(0);
  const [feedback, setFeedback] = useState<string | null>(null);
  const activeItem = items.find((item) => item.id === activeId) ?? items[0];

  const completeItem = (message: string) => {
    if (!activeItem) return;
    const currentIndex = items.findIndex((item) => item.id === activeItem.id);
    const nextItems = items.filter((item) => item.id !== activeItem.id);
    setItems(nextItems);
    setHandled((current) => current + 1);
    setFeedback(message);
    setActiveId(nextItems[Math.min(currentIndex, nextItems.length - 1)]?.id ?? "");
  };

  const runSafeBatch = () => {
    const routineCount = items.filter((item) => item.type === "routine").length;
    setItems((current) => current.filter((item) => item.type !== "routine"));
    setHandled((current) => current + routineCount);
    setFeedback(routineCount ? `已完成 ${routineCount} 个无需判断的任务` : "当前没有可批量执行的任务");
    const firstDecision = items.find((item) => item.type === "decision");
    if (firstDecision) setActiveId(firstDecision.id);
  };

  return (
    <PrototypeFrame
      eyebrow="Model 02 · Decision first"
      title="管理任务收件箱"
      description="模块被隐藏在任务之后。系统先完成确定性工作，把真正需要你判断的内容排成一个队列。"
    >
      <div className="border-b border-white/10 px-5 py-4 sm:px-7">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-5 text-xs">
            <span className="text-white"><strong className="mr-1 text-xl">{items.length}</strong> 待处理</span>
            <span className="text-neutral-600"><strong className="mr-1 text-xl text-neutral-400">{handled}</strong> 本次完成</span>
          </div>
          <button
            type="button"
            onClick={runSafeBatch}
            className="focus-ring inline-flex min-h-9 items-center justify-center gap-2 border border-sky-300/25 bg-sky-300/5 px-4 text-[10px] font-black tracking-[0.14em] text-sky-300 uppercase transition hover:bg-sky-300/10"
          >
            <Zap className="h-3.5 w-3.5" /> 执行安全批次
          </button>
        </div>
        <AnimatePresence mode="wait">
          {feedback ? (
            <motion.p key={feedback} initial={{ opacity: 0, y: -3 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="mt-3 text-xs text-emerald-300" aria-live="polite">
              <Check className="mr-1.5 inline h-3.5 w-3.5" />{feedback}
            </motion.p>
          ) : null}
        </AnimatePresence>
      </div>

      {items.length ? (
        <div className="grid min-h-[31rem] lg:grid-cols-[21rem_minmax(0,1fr)]">
          <div className="border-b border-white/10 lg:border-r lg:border-b-0">
            <div className="flex items-center justify-between px-5 py-4">
              <p className="text-[10px] font-bold tracking-[0.18em] text-neutral-500 uppercase">下一步</p>
              <span className="text-[10px] text-neutral-700">按优先级</span>
            </div>
            <div className="divide-y divide-white/10 border-t border-white/10">
              {items.map((item, index) => {
                const active = activeItem?.id === item.id;
                return (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => {
                      setActiveId(item.id);
                      setFeedback(null);
                    }}
                    className={`focus-ring group flex w-full gap-4 px-5 py-5 text-left transition ${active ? "bg-sky-300/[0.07]" : "hover:bg-white/[0.03]"}`}
                  >
                    <span className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border text-[10px] font-bold ${active ? "border-sky-300 bg-sky-300 text-black" : "border-white/15 text-neutral-600"}`}>{index + 1}</span>
                    <span className="min-w-0">
                      <span className={`block text-xs font-semibold ${active ? "text-white" : "text-neutral-400 group-hover:text-neutral-200"}`}>{item.title}</span>
                      <span className="mt-1.5 block truncate text-[10px] text-neutral-600">{item.meta}</span>
                    </span>
                  </button>
                );
              })}
            </div>
          </div>

          <AnimatePresence mode="wait">
            {activeItem ? (
              <motion.main
                key={activeItem.id}
                initial={{ opacity: 0, x: 8 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -8 }}
                transition={panelTransition}
                className="flex flex-col justify-between p-5 sm:p-8"
              >
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className={`px-2 py-1 text-[9px] font-black tracking-[0.14em] uppercase ${activeItem.type === "decision" ? "bg-amber-300/10 text-amber-200" : "bg-emerald-300/10 text-emerald-300"}`}>
                      {activeItem.type === "decision" ? "需要你的判断" : "低风险任务"}
                    </span>
                    <span className="text-[10px] text-neutral-600">{activeItem.meta}</span>
                  </div>
                  <h3 className="mt-5 max-w-xl text-2xl font-semibold tracking-tight text-white">{activeItem.title}</h3>
                  <p className="mt-3 max-w-xl text-sm leading-6 text-neutral-500">{activeItem.description}</p>

                  <div className="mt-8 border-l-2 border-sky-300 bg-sky-300/[0.05] p-5">
                    <p className="text-[10px] font-black tracking-[0.18em] text-sky-300 uppercase">系统建议</p>
                    <p className="mt-2 text-sm font-semibold text-white">{activeItem.suggestion}</p>
                    <p className="mt-2 text-xs leading-5 text-neutral-500">执行前仍可查看依据；完成后 10 分钟内可撤销。</p>
                  </div>
                </div>

                <div className="mt-9 flex flex-col-reverse gap-3 border-t border-white/10 pt-5 sm:flex-row sm:items-center sm:justify-between">
                  <button
                    type="button"
                    onClick={() => completeItem("已跳过，稍后可以在历史记录中找回")}
                    className="focus-ring min-h-10 px-4 text-[10px] font-bold tracking-[0.14em] text-neutral-500 uppercase hover:text-white"
                  >
                    稍后处理
                  </button>
                  <div className="flex flex-col gap-2 sm:flex-row">
                    <button type="button" className="focus-ring min-h-10 border border-white/15 px-4 text-[10px] font-bold tracking-[0.14em] text-neutral-300 uppercase hover:bg-white/5">查看依据</button>
                    <button
                      type="button"
                      onClick={() => completeItem(`已执行：${activeItem.suggestion}`)}
                      className="focus-ring inline-flex min-h-10 items-center justify-center gap-2 bg-sky-300 px-5 text-[10px] font-black tracking-[0.14em] text-black uppercase hover:bg-sky-200"
                    >
                      接受建议 <ArrowRight className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>
              </motion.main>
            ) : null}
          </AnimatePresence>
        </div>
      ) : (
        <div className="flex min-h-[31rem] flex-col items-center justify-center px-6 text-center">
          <span className="flex h-16 w-16 items-center justify-center rounded-full border border-emerald-300/20 bg-emerald-300/5 text-emerald-300"><CheckCircle2 className="h-7 w-7" /></span>
          <h3 className="mt-5 text-xl font-semibold text-white">收件箱已清空</h3>
          <p className="mt-2 max-w-sm text-xs leading-5 text-neutral-500">需要你判断的事情已经处理完，其余维护工作会在后台继续。</p>
        </div>
      )}
    </PrototypeFrame>
  );
}

type PlanState = "draft" | "running" | "paused" | "decision" | "done";

const planSteps = [
  { label: "扫描媒体库", detail: "对比文件与索引" },
  { label: "补全媒体信息", detail: "12 部影片可自动匹配" },
  { label: "整理文件结构", detail: "移动 4 个散落文件" },
  { label: "刷新外部评分", detail: "同步过期评分" },
];

function RadicalModel() {
  const [planState, setPlanState] = useState<PlanState>("draft");
  const [activeStep, setActiveStep] = useState(0);
  const [guardrail, setGuardrail] = useState<"strict" | "balanced">("strict");
  const [approvedException, setApprovedException] = useState(false);

  useEffect(() => {
    if (planState !== "running") return;
    const timer = window.setTimeout(() => {
      if (activeStep === 1 && !approvedException) {
        setPlanState("decision");
        return;
      }
      if (activeStep >= planSteps.length - 1) {
        setPlanState("done");
        return;
      }
      setActiveStep((current) => current + 1);
    }, 1150);
    return () => window.clearTimeout(timer);
  }, [activeStep, approvedException, planState]);

  const startPlan = () => {
    if (planState === "done") {
      setActiveStep(0);
      setApprovedException(false);
    }
    setPlanState("running");
  };

  const stepStatus = (index: number) => {
    if (planState === "done" || index < activeStep) return "done";
    if (index === activeStep && (planState === "running" || planState === "paused" || planState === "decision")) return planState;
    return "waiting";
  };

  return (
    <PrototypeFrame
      eyebrow="Model 03 · Outcome first"
      title="管理目标驾驶舱"
      description="不再启动单个工具。你只定义目标与不可越过的边界，系统规划并执行完整维护流程。"
    >
      <div className="relative min-h-[38rem] overflow-hidden">
        <div className="pointer-events-none absolute -top-36 -right-24 h-80 w-80 rounded-full bg-violet-500/10 blur-3xl" />
        <div className="pointer-events-none absolute -bottom-48 -left-24 h-96 w-96 rounded-full bg-fuchsia-400/5 blur-3xl" />

        <div className="relative grid lg:grid-cols-[minmax(0,1.15fr)_minmax(20rem,0.85fr)]">
          <main className="border-b border-white/10 p-5 sm:p-8 lg:border-r lg:border-b-0 lg:p-10">
            <div className="flex items-center gap-3">
              <span className="flex h-8 w-8 items-center justify-center rounded-full bg-violet-300 text-black"><Wand2 className="h-4 w-4" /></span>
              <p className="text-[10px] font-black tracking-[0.2em] text-violet-300 uppercase">当前意图</p>
            </div>
            <h3 className="mt-6 max-w-2xl text-3xl font-semibold leading-tight tracking-tight text-white sm:text-4xl">
              把媒体库整理到<br /><span className="font-serif font-normal text-violet-200 italic">可以安心观看</span>的状态
            </h3>
            <p className="mt-5 max-w-xl text-sm leading-6 text-neutral-500">补全缺失信息、整理散落文件、刷新评分。遇到不确定匹配或文件冲突时停下来问我。</p>

            <div className="mt-8">
              <p className="text-[10px] font-bold tracking-[0.18em] text-neutral-600 uppercase">自动化边界</p>
              <div className="mt-3 grid gap-2 sm:grid-cols-2">
                {[
                  { id: "strict" as const, title: "谨慎", text: "任何文件移动都先询问", icon: ShieldCheck },
                  { id: "balanced" as const, title: "信任系统", text: "仅冲突或低可信度时询问", icon: Bot },
                ].map((option) => {
                  const Icon = option.icon;
                  return (
                    <button
                      key={option.id}
                      type="button"
                      disabled={planState === "running" || planState === "decision"}
                      onClick={() => setGuardrail(option.id)}
                      className={`focus-ring flex items-start gap-3 border p-4 text-left transition disabled:cursor-not-allowed disabled:opacity-50 ${guardrail === option.id ? "border-violet-300/50 bg-violet-300/8" : "border-white/10 hover:border-white/20"}`}
                    >
                      <Icon className={`mt-0.5 h-4 w-4 shrink-0 ${guardrail === option.id ? "text-violet-300" : "text-neutral-600"}`} />
                      <span>
                        <span className="block text-xs font-semibold text-white">{option.title}</span>
                        <span className="mt-1 block text-[10px] leading-4 text-neutral-600">{option.text}</span>
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="mt-8 flex flex-wrap items-center gap-3">
              {planState === "running" ? (
                <button type="button" onClick={() => setPlanState("paused")} className="focus-ring inline-flex min-h-11 items-center gap-2 bg-violet-300 px-5 text-[10px] font-black tracking-[0.14em] text-black uppercase"><Pause className="h-3.5 w-3.5" /> 暂停执行</button>
              ) : planState === "decision" ? (
                <span className="inline-flex min-h-11 items-center gap-2 border border-amber-300/30 bg-amber-300/5 px-5 text-[10px] font-black tracking-[0.14em] text-amber-200 uppercase"><AlertTriangle className="h-3.5 w-3.5" /> 等待你的决定</span>
              ) : (
                <button type="button" onClick={startPlan} className="focus-ring inline-flex min-h-11 items-center gap-2 bg-violet-300 px-5 text-[10px] font-black tracking-[0.14em] text-black uppercase hover:bg-violet-200"><Play className="h-3.5 w-3.5" /> {planState === "paused" ? "继续执行" : planState === "done" ? "再次运行" : "批准并开始"}</button>
              )}
              <span className="text-[10px] text-neutral-600">预计 1 分 40 秒 · 所有动作可回滚</span>
            </div>
          </main>

          <aside className="p-5 sm:p-8 lg:p-10">
            <div className="flex items-center justify-between">
              <p className="text-[10px] font-black tracking-[0.18em] text-neutral-500 uppercase">执行计划</p>
              <span className={`inline-flex items-center gap-1.5 text-[10px] ${planState === "running" ? "text-violet-300" : planState === "done" ? "text-emerald-300" : "text-neutral-600"}`}>
                <StatusDot tone={planState === "running" ? "busy" : planState === "done" ? "ok" : "idle"} />
                {planState === "running" ? "执行中" : planState === "done" ? "已完成" : planState === "decision" ? "已暂停" : "未开始"}
              </span>
            </div>
            <ol className="mt-7 space-y-0">
              {planSteps.map((step, index) => {
                const status = stepStatus(index);
                return (
                  <li key={step.label} className="relative flex gap-4 pb-7 last:pb-0">
                    {index < planSteps.length - 1 ? <span className={`absolute top-6 bottom-0 left-[11px] w-px ${status === "done" ? "bg-emerald-400/50" : "bg-white/10"}`} /> : null}
                    <span className={`relative z-10 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border ${status === "done" ? "border-emerald-300 bg-emerald-300 text-black" : status === "running" ? "border-violet-300 bg-violet-300/15 text-violet-300" : status === "decision" ? "border-amber-300 bg-amber-300/10 text-amber-200" : status === "paused" ? "border-violet-300 text-violet-300" : "border-white/15 bg-neutral-950 text-neutral-700"}`}>
                      {status === "done" ? <Check className="h-3 w-3" /> : status === "running" ? <RefreshCw className="h-3 w-3 animate-spin" /> : status === "decision" ? <AlertTriangle className="h-3 w-3" /> : <span className="text-[9px] font-bold">{index + 1}</span>}
                    </span>
                    <div className="pt-0.5">
                      <p className={`text-xs font-semibold ${status === "waiting" ? "text-neutral-600" : "text-white"}`}>{step.label}</p>
                      <p className="mt-1 text-[10px] text-neutral-700">{step.detail}</p>
                    </div>
                  </li>
                );
              })}
            </ol>
            <div className="mt-8 border-t border-white/10 pt-5">
              <div className="flex items-center justify-between text-[10px]">
                <span className="text-neutral-600">系统权限</span>
                <span className="text-neutral-400">{guardrail === "strict" ? "逐次确认文件变更" : "例外时确认"}</span>
              </div>
              <div className="mt-3 h-1 overflow-hidden rounded-full bg-white/10">
                <motion.div
                  className="h-full bg-violet-300"
                  animate={{ width: planState === "draft" ? "0%" : planState === "done" ? "100%" : `${((activeStep + 0.5) / planSteps.length) * 100}%` }}
                  transition={panelTransition}
                />
              </div>
            </div>
          </aside>
        </div>

        <AnimatePresence>
          {planState === "decision" ? (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="absolute inset-0 z-10 flex items-center justify-center bg-black/75 p-4 backdrop-blur-sm">
              <motion.div initial={{ scale: 0.97, y: 8 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.97, opacity: 0 }} transition={panelTransition} role="dialog" aria-modal="true" aria-label="自动化需要决定" className="w-full max-w-md border border-amber-300/25 bg-neutral-950 p-6 shadow-2xl">
                <span className="flex h-9 w-9 items-center justify-center rounded-full bg-amber-300/10 text-amber-200"><AlertTriangle className="h-4 w-4" /></span>
                <p className="mt-5 text-[10px] font-black tracking-[0.18em] text-amber-200 uppercase">发现一个例外</p>
                <h3 className="mt-2 text-xl font-semibold text-white">两个文件会使用同一目录名</h3>
                <p className="mt-3 text-xs leading-5 text-neutral-500">系统建议保留两个版本，并在较新的文件夹后添加“4K Remaster”。这不会覆盖任何文件。</p>
                <div className="mt-6 flex flex-col gap-2 sm:flex-row">
                  <button type="button" onClick={() => setPlanState("paused")} className="focus-ring min-h-10 flex-1 border border-white/15 px-4 text-[10px] font-bold tracking-wider text-neutral-300 uppercase hover:bg-white/5">退出并检查</button>
                  <button
                    type="button"
                    onClick={() => {
                      setApprovedException(true);
                      setPlanState("running");
                    }}
                    className="focus-ring min-h-10 flex-1 bg-amber-200 px-4 text-[10px] font-black tracking-wider text-black uppercase hover:bg-amber-100"
                  >
                    采用建议
                  </button>
                </div>
              </motion.div>
            </motion.div>
          ) : null}
        </AnimatePresence>
      </div>
    </PrototypeFrame>
  );
}

function ModelNotes({ model }: { model: ModelConfig }) {
  const notes: Record<ModelId, { best: string; risk: string; signal: string }> = {
    safe: {
      best: "现有用户已经熟悉按模块维护，并且大多数操作低频。",
      risk: "状态很多，但用户仍需自己判断下一步该做什么。",
      signal: "测试用户能否在 10 秒内找到“待审核”并完成一次匹配。",
    },
    balanced: {
      best: "维护事项经常出现，但真正需要人工判断的比例不高。",
      risk: "用户可能不知道系统在队列背后自动做了哪些工作。",
      signal: "观察用户是否愿意连续清空队列，以及是否会频繁打开“依据”。",
    },
    radical: {
      best: "用户更在意媒体库最终状态，而不是理解每一种维护工具。",
      risk: "信任门槛最高；回滚、解释和权限边界必须非常可靠。",
      signal: "测试用户是否敢点“批准并开始”，以及在哪个节点选择暂停。",
    },
  };
  const note = notes[model.id];

  return (
    <div className="mt-6 grid gap-px border border-white/10 bg-white/10 md:grid-cols-3">
      {[
        { icon: Gauge, label: "适合场景", text: note.best },
        { icon: AlertTriangle, label: "主要风险", text: note.risk },
        { icon: FileCheck2, label: "建议观察", text: note.signal },
      ].map((item) => {
        const Icon = item.icon;
        return (
          <div key={item.label} className="bg-black p-5">
            <Icon className={`h-4 w-4 ${model.accent}`} />
            <p className="mt-4 text-[10px] font-black tracking-[0.18em] text-neutral-500 uppercase">{item.label}</p>
            <p className="mt-2 text-xs leading-5 text-neutral-400">{item.text}</p>
          </div>
        );
      })}
    </div>
  );
}

export default function ManagementInteractionLab() {
  const [activeModel, setActiveModel] = useState<ModelId>("balanced");
  const [resetKey, setResetKey] = useState(0);
  const active = useMemo(() => models.find((model) => model.id === activeModel) ?? models[1], [activeModel]);

  return (
    <div className="min-h-screen bg-black text-white selection:bg-white selection:text-black">
      <header className="page-x border-b border-white/10 pt-32 pb-10 sm:pt-36 sm:pb-12">
        <div className="mx-auto max-w-[90rem]">
          <div className="flex flex-col gap-7 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <div className="flex items-center gap-3 text-[10px] font-black tracking-[0.24em] text-neutral-500 uppercase">
                <Command className="h-3.5 w-3.5" /> Interaction lab · Mock data only
              </div>
              <h1 className="mt-5 max-w-4xl text-4xl font-bold tracking-[-0.04em] text-white sm:text-6xl lg:text-7xl">
                Management，<span className="font-serif font-normal text-neutral-500 italic">换一种做法。</span>
              </h1>
              <p className="mt-5 max-w-2xl text-sm leading-6 text-neutral-500">三个一次性原型，共用同一组管理问题。直接点击、完成任务，再比较哪一种更接近你想要的控制感。</p>
            </div>
            <div className="flex items-center gap-2 border border-white/10 bg-white/[0.02] px-3 py-2 text-[10px] text-neutral-500">
              <ShieldCheck className="h-3.5 w-3.5 text-emerald-300" /> 演示不会调用真实 API
            </div>
          </div>
        </div>
      </header>

      <main className="page-x py-8 sm:py-10">
        <div className="mx-auto max-w-[90rem]">
          <div className="grid gap-3 lg:grid-cols-3" role="tablist" aria-label="交互模型">
            {models.map((model) => {
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
                  className={`focus-ring group relative overflow-hidden border p-5 text-left transition ${selected ? model.accentSoft : "border-white/10 bg-neutral-950/50 hover:border-white/20"}`}
                >
                  <div className="flex items-start justify-between gap-5">
                    <div>
                      <p className={`text-[10px] font-black tracking-[0.18em] uppercase ${selected ? model.accent : "text-neutral-600"}`}>{model.index} · {model.label}</p>
                      <p className="mt-2 text-lg font-semibold text-white">{model.name}</p>
                    </div>
                    <Icon className={`h-5 w-5 ${selected ? model.accent : "text-neutral-700 group-hover:text-neutral-500"}`} />
                  </div>
                  <p className="mt-4 text-xs leading-5 text-neutral-500">{model.thesis}</p>
                  <div className="mt-5 flex flex-wrap gap-x-5 gap-y-2">
                    {model.metrics.map((metric) => (
                      <span key={metric.label} className="text-[9px] font-bold tracking-wider text-neutral-600 uppercase">{metric.label} <strong className={selected ? model.accent : "text-neutral-400"}>{metric.value}</strong></span>
                    ))}
                  </div>
                </button>
              );
            })}
          </div>

          <div className="mt-7 flex items-center justify-between gap-4">
            <div className="flex items-center gap-2 text-[10px] text-neutral-600">
              <CircleDot className={`h-3.5 w-3.5 ${active.accent}`} /> 正在体验：{active.label} · {active.name}
            </div>
            <button
              type="button"
              onClick={() => setResetKey((current) => current + 1)}
              className="focus-ring inline-flex min-h-9 items-center gap-2 px-2 text-[10px] font-bold tracking-wider text-neutral-600 uppercase transition hover:text-white"
            >
              <RotateCcw className="h-3.5 w-3.5" /> 重置演示
            </button>
          </div>

          <div className="mt-3" role="tabpanel">
            <AnimatePresence mode="wait">
              <motion.div
                key={`${activeModel}-${resetKey}`}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -5 }}
                transition={panelTransition}
              >
                {activeModel === "safe" ? <ConservativeModel /> : null}
                {activeModel === "balanced" ? <BalancedModel /> : null}
                {activeModel === "radical" ? <RadicalModel /> : null}
              </motion.div>
            </AnimatePresence>
          </div>

          <ModelNotes model={active} />

          <footer className="flex flex-col gap-3 py-10 text-[10px] leading-5 text-neutral-700 sm:flex-row sm:items-center sm:justify-between">
            <span>5X49 · Management interaction study</span>
            <span>建议每个模型至少完成一次主要任务后再做选择。</span>
          </footer>
        </div>
      </main>
    </div>
  );
}
