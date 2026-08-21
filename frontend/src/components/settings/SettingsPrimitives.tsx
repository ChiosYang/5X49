"use client";

import type { ReactNode } from "react";
import { ChevronDown, Loader2 } from "lucide-react";

type StatusTone = "neutral" | "success" | "error" | "warning";

const statusToneClasses: Record<StatusTone, string> = {
  neutral: "text-ink-subtle",
  success: "text-success",
  error: "text-danger",
  warning: "text-warning",
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
    <header>
      {eyebrow && (
        <p className="type-label mb-2 text-ink-disabled">
          {eyebrow}
        </p>
      )}
      <h2 className="type-section-title mb-2 text-ink">
        {title}
      </h2>
      <p className="text-sm text-ink-subtle">{description}</p>
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
    <section>
      <div className="mb-6">
        <h3 className="type-label text-ink-muted">
          {title}
        </h3>
        {description && (
          <p className="mt-2 text-xs leading-5 text-ink-disabled">{description}</p>
        )}
      </div>
      <div className="space-y-6">{children}</div>
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
    <div className="border-b border-line pb-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 flex-1">
          <p className="mb-1 text-sm font-medium tracking-widest text-ink uppercase">
            {title}
          </p>
          <p className="max-w-2xl text-xs leading-5 text-ink-disabled">{description}</p>
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
      className={`focus-ring duration-standard relative h-7 w-12 shrink-0 border transition-colors ${
        checked ? "border-inverse bg-inverse" : "border-line-strong bg-surface-raised"
      } disabled:cursor-not-allowed disabled:opacity-50`}
    >
      <span
        className={`duration-standard absolute top-1 left-1 h-5 w-5 bg-inverse-ink transition-transform ${
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
    <details className="group border-b border-line pb-6">
      <summary className="focus-ring flex cursor-pointer list-none items-center justify-between gap-5 py-1">
        <span className="min-w-0">
          <span className="block text-sm font-medium tracking-widest text-ink uppercase">
            {title}
          </span>
          <span className="mt-1 block text-xs leading-5 text-ink-disabled">{description}</span>
        </span>
        <span className="flex shrink-0 items-center gap-3">
          {summary && (
            <span className="hidden max-w-56 truncate text-[11px] font-bold tracking-widest text-ink-subtle uppercase sm:inline lg:max-w-80">
              {summary}
            </span>
          )}
          <ChevronDown className="duration-standard h-4 w-4 text-ink-subtle transition-transform group-open:rotate-180" />
        </span>
      </summary>
      <div className="mt-6 space-y-6 border-t border-line pt-6">{children}</div>
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
      className={`flex h-full flex-col border-b pb-6 ${
        danger
          ? "border-danger/20"
          : "border-line"
      }`}
    >
      <div className="flex-1">
        <h3 className={`text-sm font-medium tracking-widest uppercase ${danger ? "text-danger" : "text-ink"}`}>
          {title}
        </h3>
        <p className="mt-2 text-xs leading-5 text-ink-disabled">{description}</p>
        {meta && <div className="mt-3 text-xs leading-5 text-ink-subtle">{meta}</div>}
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
      className={`focus-ring duration-fast inline-flex min-h-11 w-full items-center justify-center gap-2 px-5 text-xs font-medium tracking-widest uppercase transition-colors disabled:cursor-not-allowed disabled:opacity-50 sm:w-auto ${
        danger
          ? "border border-danger/40 bg-danger/10 text-danger hover:border-danger/70 hover:bg-danger/20"
          : "border border-line-strong bg-surface-raised text-ink hover:border-ink-disabled hover:bg-surface-hover"
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
    <div className="border-l border-line-strong py-1 pl-4">
      <p className="text-[10px] font-medium tracking-widest text-ink-disabled uppercase">{label}</p>
      <p
        className={`mt-3 text-sm font-semibold ${
          error ? "text-danger" : active ? "text-success" : "text-ink"
        }`}
      >
        {value}
      </p>
      {detail && <p className="mt-1 truncate text-xs text-ink-disabled">{detail}</p>}
    </div>
  );
}
