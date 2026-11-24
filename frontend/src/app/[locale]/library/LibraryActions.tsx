"use client";

import { ScanSearch } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { IconButton } from "@/components/ui/Button";
import { InlineFeedback } from "@/components/ui/Feedback";
import { useLibrarySyncStatus, useScanLibrary } from "@/hooks/useSettings";
import { useWorkflowCache } from "@/hooks/useWorkflows";
import { useSettingsScanGuard } from "@/hooks/useSettingsScanGuard";
import { useRouter } from "@/i18n/routing";
import type { WorkflowAccepted } from "@/types/movie";

type Feedback = { message: string; tone: "success" | "error" };

function errorMessage(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback;
}

export default function LibraryActions({ showScan = true }: { showScan?: boolean }) {
  const t = useTranslations("LibraryCare");
  const router = useRouter();
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const sync = useLibrarySyncStatus();
  const scan = useScanLibrary();
  const scanBlocked = useSettingsScanGuard();
  const { upsertWorkflow, refreshWorkflows } = useWorkflowCache();
  const scanBusy = scan.isMutating || sync.data?.sync.state === "running";

  if (!showScan) return null;

  const runScan = async () => {
    setFeedback(null);
    try {
      const result = await scan.trigger() as Partial<WorkflowAccepted> | undefined;
      if (result?.workflow?.id) upsertWorkflow(result.workflow);
      else refreshWorkflows();
      setFeedback({ message: t("scanStarted"), tone: "success" });
      router.refresh();
    } catch (error) {
      setFeedback({ message: errorMessage(error, t("operationFailed")), tone: "error" });
    }
  };

  return (
    <div className="relative ml-auto flex flex-wrap items-center justify-end gap-1 sm:gap-3">
      <IconButton
        variant="ghost"
        aria-label={scanBusy ? t("scanning") : t("scanNow")}
        busy={scanBusy}
        disabled={scanBlocked}
        icon={<ScanSearch className="h-4 w-4" />}
        onClick={() => void runScan()}
      />

      <div aria-live="polite" aria-atomic="true" className="absolute top-full right-0 mt-3 min-h-5 w-[min(22rem,calc(100vw-2rem))] text-right">
        {feedback ? <InlineFeedback tone={feedback.tone}>{feedback.message}</InlineFeedback> : null}
      </div>
    </div>
  );
}
