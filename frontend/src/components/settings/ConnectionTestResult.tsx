"use client";

import { useId } from "react";
import { Check, X } from "lucide-react";
import { useTranslations } from "next-intl";
import type { ConnectionOutcome } from "@/hooks/useConnectionTest";

export function ConnectionTestResult({ outcome }: { outcome: ConnectionOutcome }) {
  const t = useTranslations("Settings");
  const id = useId();
  const message = outcome === "success" ? t("connectionTestPassed") : t("connectionTestFailed");
  const Icon = outcome === "success" ? Check : X;
  return <span className="group/test-result relative inline-flex h-11 w-5 shrink-0 items-center justify-center">
    <span className="sr-only" role="status" aria-live="polite">{outcome ? message : ""}</span>
    {outcome ? <>
      <span role="img" tabIndex={0} aria-label={message} aria-describedby={id} className={`focus-ring inline-flex h-7 w-5 items-center justify-center ${outcome === "success" ? "text-success" : "text-danger"}`}>
        <Icon aria-hidden className="h-4 w-4" />
      </span>
      <span id={id} role="tooltip" className="pointer-events-none invisible absolute right-0 top-full z-20 mt-2 w-max max-w-56 border border-line-strong bg-surface-raised px-3 py-2 text-xs group-hover/test-result:visible group-focus-within/test-result:visible">{message}</span>
    </> : null}
  </span>;
}
