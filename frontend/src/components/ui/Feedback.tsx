import type { ReactNode } from "react";
import { Loader2 } from "lucide-react";
import { cn } from "@/lib/cn";

export type FeedbackTone = "neutral" | "success" | "error" | "warning";

const toneClasses: Record<FeedbackTone, string> = {
  neutral: "text-ink-subtle",
  success: "text-success",
  error: "text-danger",
  warning: "text-warning",
};

export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={cn("h-4 w-4 shrink-0 animate-spin", className)} aria-hidden="true" />;
}

export function InlineFeedback({
  children,
  className,
  tone = "neutral",
}: {
  children?: ReactNode;
  className?: string;
  tone?: FeedbackTone;
}) {
  if (!children) return null;

  return (
    <p className={cn("break-words text-xs leading-5", toneClasses[tone], className)}>
      {children}
    </p>
  );
}

export function StateMessage({
  children,
  className,
  state = "empty",
}: {
  children: ReactNode;
  className?: string;
  state?: "loading" | "empty" | "error";
}) {
  return (
    <div
      className={cn(
        "flex min-h-16 items-center justify-center gap-2 break-words border border-line-strong bg-surface px-4 py-4 text-sm",
        state === "error" ? "text-danger" : "text-ink-subtle",
        className,
      )}
      aria-live={state === "loading" ? "polite" : undefined}
    >
      {state === "loading" ? <Spinner /> : null}
      {children}
    </div>
  );
}
