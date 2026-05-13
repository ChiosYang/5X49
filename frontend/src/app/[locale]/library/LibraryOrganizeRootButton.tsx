"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { Check, FolderInput, Loader2, Search } from "lucide-react";
import { useOrganizeRootVideos } from "@/hooks/useSettings";
import { API } from "@/lib/api";
import type { MetadataSearchResult, RootVideo } from "@/types/movie";

type OrganizeStatus = {
  state: string;
  last_started_at: string | null;
  last_finished_at: string | null;
  last_error: string | null;
  last_result: Record<string, unknown> | null;
};

const sleep = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms));

interface LibraryOrganizeRootButtonProps {
  rootVideos?: RootVideo[];
}

export default function LibraryOrganizeRootButton({
  rootVideos = [],
}: LibraryOrganizeRootButtonProps) {
  const t = useTranslations("Library");
  const router = useRouter();
  const { trigger, isMutating, error } = useOrganizeRootVideos();
  const [isWaiting, setIsWaiting] = useState(false);
  const [taskFailed, setTaskFailed] = useState(false);
  const [candidatesByPath, setCandidatesByPath] = useState<Record<string, MetadataSearchResult[]>>({});
  const [reviewingPath, setReviewingPath] = useState<string | null>(null);
  const [confirmingKey, setConfirmingKey] = useState<string | null>(null);
  const [reviewError, setReviewError] = useState<string>("");

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
  const pendingCount = rootVideos.length;

  const handleReview = async (video: RootVideo) => {
    setReviewError("");
    setReviewingPath(video.path);
    try {
      const params = new URLSearchParams({ query: video.parsed_title || video.filename });
      if (video.parsed_year) {
        params.set("year", String(video.parsed_year));
      }
      const res = await fetch(`${API.metadataSearch()}?${params.toString()}`);
      if (!res.ok) {
        throw new Error("search_failed");
      }
      const candidates = await res.json() as MetadataSearchResult[];
      setCandidatesByPath((current) => ({ ...current, [video.path]: candidates.slice(0, 5) }));
      if (candidates.length === 0) {
        setReviewError(t("rootNoCandidates"));
      }
    } catch {
      setReviewError(t("rootReviewFailed"));
    } finally {
      setReviewingPath(null);
    }
  };

  const handleConfirm = async (video: RootVideo, tmdbId: number) => {
    const key = `${video.path}:${tmdbId}`;
    setReviewError("");
    setConfirmingKey(key);
    try {
      const res = await fetch(API.libraryOrganizeRootConfirm(), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          path: video.path,
          tmdb_id: tmdbId,
          options: {
            rename_style: "preserve_stem",
            overwrite: false,
            write_nfo: true,
            download_artwork: true,
          },
        }),
      });
      if (!res.ok) {
        throw new Error("confirm_failed");
      }
      setCandidatesByPath((current) => {
        const next = { ...current };
        delete next[video.path];
        return next;
      });
      router.refresh();
    } catch {
      setReviewError(t("rootConfirmFailed"));
    } finally {
      setConfirmingKey(null);
    }
  };

  return (
    <div className="group/root-organize relative">
      <button
        type="button"
        onClick={handleOrganize}
        disabled={isBusy}
        className={`relative flex h-10 w-10 items-center justify-center border bg-neutral-950 text-white transition-colors hover:bg-neutral-900 disabled:cursor-not-allowed disabled:opacity-50 ${
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
        {pendingCount > 0 && (
          <span className="absolute -right-1.5 -top-1.5 flex min-h-4 min-w-4 items-center justify-center border border-black bg-white px-1 text-[10px] font-bold leading-none text-black">
            {pendingCount > 99 ? "99+" : pendingCount}
          </span>
        )}
      </button>

      {pendingCount > 0 && (
        <div className="pointer-events-none absolute right-0 top-full z-50 w-[min(24rem,calc(100vw-4rem))] pt-3 opacity-0 transition-opacity duration-150 group-hover/root-organize:pointer-events-auto group-hover/root-organize:opacity-100 group-focus-within/root-organize:pointer-events-auto group-focus-within/root-organize:opacity-100">
          <div className="border border-neutral-800 bg-black/95 p-4 shadow-2xl shadow-black/60 backdrop-blur">
            <div className="mb-3 flex items-center justify-between gap-4 border-b border-neutral-900 pb-3">
              <p className="text-xs font-bold uppercase tracking-widest text-neutral-400">
                {t("rootPending", { count: pendingCount })}
              </p>
              <button
                type="button"
                onClick={handleOrganize}
                disabled={isBusy}
                className="flex h-8 items-center gap-2 border border-neutral-800 bg-neutral-950 px-3 text-[11px] font-bold uppercase tracking-widest text-white transition-colors hover:border-neutral-500 hover:bg-neutral-900 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {isBusy && <Loader2 className="h-3 w-3 animate-spin" />}
                {t("organizeRoot")}
              </button>
            </div>
            <div className="max-h-72 overflow-y-auto pr-1">
              <ul className="space-y-3">
                {rootVideos.map((video) => (
                  <li key={video.path} className="min-w-0 border-b border-neutral-950 pb-3 last:border-b-0 last:pb-0">
                    <p className="truncate text-sm text-neutral-200" title={video.filename}>
                      {video.filename}
                    </p>
                    <div className="mt-1 flex items-center justify-between gap-3">
                      <p className="text-xs text-neutral-500">
                        {video.stable ? t("rootReady") : t("rootWaitingForStability")}
                      </p>
                      {video.stable && (
                        <button
                          type="button"
                          onClick={() => handleReview(video)}
                          disabled={reviewingPath === video.path || Boolean(confirmingKey)}
                          className="flex h-7 items-center gap-1.5 border border-neutral-800 bg-neutral-950 px-2 text-[10px] font-bold uppercase tracking-widest text-white transition-colors hover:border-neutral-500 hover:bg-neutral-900 disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          {reviewingPath === video.path ? (
                            <Loader2 className="h-3 w-3 animate-spin" />
                          ) : (
                            <Search className="h-3 w-3" />
                          )}
                          {t("rootReview")}
                        </button>
                      )}
                    </div>
                    {candidatesByPath[video.path]?.length > 0 && (
                      <div className="mt-3 space-y-2">
                        {candidatesByPath[video.path].map((candidate) => {
                          const key = `${video.path}:${candidate.tmdb_id}`;
                          return (
                            <button
                              key={candidate.tmdb_id}
                              type="button"
                              onClick={() => handleConfirm(video, candidate.tmdb_id)}
                              disabled={Boolean(confirmingKey)}
                              className="block w-full border border-neutral-800 bg-neutral-950 px-3 py-2 text-left text-xs text-neutral-300 transition-colors hover:border-neutral-500 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
                            >
                              <span className="flex items-start justify-between gap-3">
                                <span className="min-w-0">
                                  <span className="block truncate font-bold uppercase tracking-widest">
                                    {candidate.title} {candidate.year ? `(${candidate.year})` : ""}
                                  </span>
                                  <span className="block text-neutral-500">
                                    TMDB {candidate.tmdb_id} · {Math.round(candidate.score)}%
                                  </span>
                                </span>
                                {confirmingKey === key ? (
                                  <Loader2 className="mt-0.5 h-3 w-3 shrink-0 animate-spin" />
                                ) : (
                                  <Check className="mt-0.5 h-3 w-3 shrink-0" />
                                )}
                              </span>
                            </button>
                          );
                        })}
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            </div>
            {reviewError && (
              <p className="mt-3 border-t border-neutral-900 pt-3 text-xs uppercase tracking-widest text-red-500">
                {reviewError}
              </p>
            )}
          </div>
        </div>
      )}
    </div>
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
