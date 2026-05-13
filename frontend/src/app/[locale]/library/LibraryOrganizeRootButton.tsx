"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { FolderInput, Loader2 } from "lucide-react";
import { useOrganizeRootVideos } from "@/hooks/useSettings";
import { API } from "@/lib/api";

type OrganizeStatus = {
  state: string;
  last_started_at: string | null;
  last_finished_at: string | null;
  last_error: string | null;
  last_result: Record<string, unknown> | null;
};

const sleep = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms));

export default function LibraryOrganizeRootButton() {
  const t = useTranslations("Library");
  const router = useRouter();
  const { trigger, isMutating, error } = useOrganizeRootVideos();
  const [isWaiting, setIsWaiting] = useState(false);
  const [taskFailed, setTaskFailed] = useState(false);

  const handleOrganize = async () => {
    setTaskFailed(false);
    setIsWaiting(true);
    try {
      const previousStatus = await readOrganizeStatus().catch(() => null);
      await trigger();
      const status = await waitForOrganize(previousStatus?.last_started_at ?? null);
      setTaskFailed(status?.state === "error" || Boolean(status?.last_error));
      router.refresh();
    } catch {
      setTaskFailed(true);
    } finally {
      setIsWaiting(false);
    }
  };

  const isBusy = isMutating || isWaiting;
  const hasError = Boolean(error) || taskFailed;

  return (
    <button
      type="button"
      onClick={handleOrganize}
      disabled={isBusy}
      className={`flex h-10 w-10 items-center justify-center border bg-neutral-950 text-white transition-colors hover:bg-neutral-900 disabled:cursor-not-allowed disabled:opacity-50 ${
        hasError
          ? "border-red-700 hover:border-red-500"
          : "border-neutral-800 hover:border-neutral-500"
      }`}
      aria-label={hasError ? t("organizeRootFailed") : t("organizeRoot")}
      title={hasError ? t("organizeRootFailed") : t("organizeRoot")}
    >
      {isBusy ? (
        <Loader2 className="h-4 w-4 animate-spin" />
      ) : (
        <FolderInput className="h-4 w-4" />
      )}
    </button>
  );
}

async function waitForOrganize(previousStartedAt: string | null): Promise<OrganizeStatus | null> {
  let sawCurrentTask = false;

  for (let attempt = 0; attempt < 45; attempt += 1) {
    await sleep(attempt === 0 ? 500 : 1000);
    const status = await readOrganizeStatus();
    const isCurrentTask = status.last_started_at !== previousStartedAt;
    sawCurrentTask ||= isCurrentTask;
    if (status.state === "running") {
      sawCurrentTask = true;
      continue;
    }

    if (sawCurrentTask) {
      return status;
    }
  }

  return null;
}

async function readOrganizeStatus(): Promise<OrganizeStatus> {
  const res = await fetch(API.libraryOrganizeStatus(), { cache: "no-store" });
  if (!res.ok) {
    throw new Error("Failed to read organize status");
  }
  return res.json();
}
