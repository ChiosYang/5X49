"use client";

import type { ReactNode } from "react";
import { ChevronDown, Loader2 } from "lucide-react";

type StatusTone = "neutral" | "success" | "error" | "warning";

const statusToneClasses: Record<StatusTone, string> = {
  neutral: "text-neutral-500",
  success: "text-emerald-400",
  error: "text-red-400",
  warning: "text-amber-300",
};

export function SectionIntro({
  eyebrow,
  title,
  description,
}: {
  eyebrow?: string;
  title: string;
  description: string;
}) {
  return (
    <header className="space-y-3 border-b border-neutral-900 pb-7">
      {eyebrow && (
        <p className="text-xs font-bold uppercase tracking-[0.22em] text-neutral-600">
          {eyebrow}
        </p>
      )}
      <h2 className="text-3xl font-semibold tracking-tight text-white md:text-4xl">
        {title}
      </h2>
      <p className="max-w-2xl text-sm leading-6 text-neutral-500">{description}</p>
    </header>
  );
}

export function SettingsPanel({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: ReactNode;
}) {
  return (
    <section className="border border-neutral-900 bg-neutral-950/40">
      <div className="border-b border-neutral-900 px-5 py-4 sm:px-6">
        <h3 className="text-xs font-bold uppercase tracking-[0.2em] text-neutral-200">
          {title}
        </h3>
        {description && (
          <p className="mt-2 text-xs leading-5 text-neutral-600">{description}</p>
        )}
      </div>
      <div className="divide-y divide-neutral-900">{children}</div>
    </section>
  );
}

export function SettingRow({
  title,
  description,
  control,
  feedback,
  children,
}: {
  title: string;
  description: string;
  control?: ReactNode;
  feedback?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <div className="px-5 py-5 sm:px-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-neutral-100">{title}</p>
          <p className="mt-1 max-w-2xl text-xs leading-5 text-neutral-600">{description}</p>
        </div>
        {control && <div className="shrink-0 sm:max-w-[60%]">{control}</div>}
      </div>
      {children && <div className="mt-4">{children}</div>}
      <div className="mt-3 min-h-5" aria-live="polite">
        {feedback}
      </div>
    </div>
  );
}

export function InlineStatus({
  children,
  tone = "neutral",
}: {
  children?: ReactNode;
  tone?: StatusTone;
}) {
  if (!children) return null;

  return (
    <p className={`break-words text-xs leading-5 ${statusToneClasses[tone]}`}>
      {children}
    </p>
  );
}

export function ToggleSwitch({
  checked,
  disabled,
  label,
  onChange,
}: {
  checked: boolean;
  disabled?: boolean;
  label: string;
  onChange: () => void;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={onChange}
      disabled={disabled}
      className={`relative h-7 w-12 shrink-0 border transition-colors ${
        checked ? "border-white bg-white" : "border-neutral-700 bg-neutral-900"
      } disabled:cursor-not-allowed disabled:opacity-50`}
    >
      <span
        className={`absolute left-1 top-1 h-5 w-5 bg-black transition-transform ${
          checked ? "translate-x-5" : "translate-x-0"
        }`}
      />
    </button>
  );
}

export function DisclosurePanel({
  title,
  description,
  summary,
  children,
}: {
  title: string;
  description: string;
  summary?: string;
  children: ReactNode;
}) {
  return (
    <details className="group border border-neutral-900 bg-neutral-950/30">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-5 px-5 py-5 sm:px-6">
        <span className="min-w-0">
          <span className="block text-sm font-semibold text-neutral-100">{title}</span>
          <span className="mt-1 block text-xs leading-5 text-neutral-600">{description}</span>
        </span>
        <span className="flex shrink-0 items-center gap-3">
          {summary && (
            <span className="hidden max-w-56 truncate text-[11px] font-bold uppercase tracking-widest text-neutral-500 sm:inline lg:max-w-80">
              {summary}
            </span>
          )}
          <ChevronDown className="h-4 w-4 text-neutral-500 transition-transform group-open:rotate-180" />
        </span>
      </summary>
      <div className="divide-y divide-neutral-900 border-t border-neutral-900">{children}</div>
    </details>
  );
}

export function ActionCard({
  title,
  description,
  meta,
  status,
  statusTone = "neutral",
  children,
  danger = false,
}: {
  title: string;
  description: string;
  meta?: ReactNode;
  status?: ReactNode;
  statusTone?: StatusTone;
  children: ReactNode;
  danger?: boolean;
}) {
  return (
    <article
      className={`flex h-full flex-col border p-5 sm:p-6 ${
        danger
          ? "border-red-950/80 bg-red-950/10"
          : "border-neutral-900 bg-neutral-950/40"
      }`}
    >
      <div className="min-h-28 flex-1">
        <h3 className={`text-sm font-semibold ${danger ? "text-red-300" : "text-neutral-100"}`}>
          {title}
        </h3>
        <p className="mt-2 text-xs leading-5 text-neutral-600">{description}</p>
        {meta && <div className="mt-3 text-xs leading-5 text-neutral-500">{meta}</div>}
      </div>
      <div className="mt-5 min-h-5" aria-live="polite">
        <InlineStatus tone={statusTone}>{status}</InlineStatus>
      </div>
      <div className="mt-3">{children}</div>
    </article>
  );
}

export function ActionButton({
  children,
  busy = false,
  disabled = false,
  danger = false,
  onClick,
}: {
  children: ReactNode;
  busy?: boolean;
  disabled?: boolean;
  danger?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled || busy}
      className={`inline-flex min-h-11 w-full items-center justify-center gap-2 px-4 text-xs font-bold uppercase tracking-[0.16em] transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
        danger
          ? "border border-red-900 bg-red-950/30 text-red-200 hover:border-red-600 hover:bg-red-900/40"
          : "border border-neutral-800 bg-neutral-900 text-white hover:border-neutral-600 hover:bg-neutral-800"
      }`}
    >
      {busy && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
      {children}
    </button>
  );
}

export function StatusTile({
  label,
  value,
  detail,
  active = false,
  error = false,
}: {
  label: string;
  value: string;
  detail?: string;
  active?: boolean;
  error?: boolean;
}) {
  return (
    <div className="border border-neutral-900 bg-neutral-950/40 p-4">
      <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-neutral-600">{label}</p>
      <p
        className={`mt-3 text-sm font-semibold ${
          error ? "text-red-400" : active ? "text-emerald-400" : "text-neutral-200"
        }`}
      >
        {value}
      </p>
      {detail && <p className="mt-1 truncate text-xs text-neutral-600">{detail}</p>}
    </div>
  );
}
