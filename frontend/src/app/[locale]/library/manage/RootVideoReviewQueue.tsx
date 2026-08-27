"use client";

import { Clock3, FolderInput } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useMemo, useState } from "react";
import useSWR from "swr";

import {
  MetadataCandidatePicker,
  parseMetadataSearchInput,
  parseTmdbId,
  prependMetadataCandidate,
} from "@/components/metadata/MetadataCandidatePicker";
import { InlineFeedback, StateMessage } from "@/components/ui/Feedback";
import { useWorkflowCache } from "@/hooks/useWorkflows";
import { API } from "@/lib/api";
import type {
  MetadataSearchResult,
  RootVideo,
  WorkflowAccepted,
} from "@/types/movie";

function defaultSearchInput(video: RootVideo) {
  return [video.parsed_title || video.filename, video.parsed_year || ""]
    .filter(Boolean)
    .join(" ");
}

export default function RootVideoReviewQueue({
  refreshSignal,
}: {
  refreshSignal?: string | null;
}) {
  const t = useTranslations("LibraryManagement");
  const libraryT = useTranslations("Library");
  const { data, error, isLoading, mutate } = useSWR<RootVideo[]>(API.libraryRootVideos());
  const { upsertWorkflow } = useWorkflowCache();
  const [hiddenPaths, setHiddenPaths] = useState<Set<string>>(() => new Set());
  const [candidatesByPath, setCandidatesByPath] = useState<Record<string, MetadataSearchResult[]>>({});
  const [searchDrafts, setSearchDrafts] = useState<Record<string, string>>({});
  const [activeReviewPath, setActiveReviewPath] = useState<string | null>(null);
  const [reviewingPath, setReviewingPath] = useState<string | null>(null);
  const [confirmingKey, setConfirmingKey] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<{
    message: string;
    tone: "error" | "success";
  } | null>(null);

  const rootVideos = useMemo(
    () => (data ?? []).filter((video) => !hiddenPaths.has(video.path)),
    [data, hiddenPaths],
  );

  useEffect(() => {
    if (!refreshSignal) return;
    void mutate()
      .then(() => setHiddenPaths(new Set()))
      .catch(() => undefined);
  }, [refreshSignal, mutate]);

  const handleReview = async (video: RootVideo) => {
    setFeedback(null);
    setActiveReviewPath(video.path);
    setReviewingPath(video.path);
    try {
      const input = searchDrafts[video.path]?.trim() || defaultSearchInput(video);
      const tmdbId = parseTmdbId(input);
      setSearchDrafts((current) => ({ ...current, [video.path]: input }));

      if (tmdbId) {
        const response = await fetch(API.metadataMovie(tmdbId));
        if (!response.ok) throw new Error("lookup_failed");
        const candidate = await response.json() as MetadataSearchResult;
        setCandidatesByPath((current) => ({
          ...current,
          [video.path]: prependMetadataCandidate(current[video.path] ?? [], candidate),
        }));
        return;
      }

      const { query, year } = parseMetadataSearchInput(input);
      const params = new URLSearchParams({ query });
      if (year) params.set("year", String(year));
      const response = await fetch(`${API.metadataSearch()}?${params}`);
      if (!response.ok) throw new Error("search_failed");
      const candidates = await response.json() as MetadataSearchResult[];
      setCandidatesByPath((current) => ({ ...current, [video.path]: candidates }));
      if (candidates.length === 0) {
        setFeedback({ message: libraryT("rootNoCandidates"), tone: "error" });
      }
    } catch {
      setFeedback({ message: libraryT("rootReviewFailed"), tone: "error" });
    } finally {
      setReviewingPath(null);
    }
  };

  const handleConfirm = async (video: RootVideo, tmdbId: number) => {
    const key = `${video.path}:${tmdbId}`;
    setFeedback(null);
    setConfirmingKey(key);
    try {
      const response = await fetch(API.libraryOrganizeRootConfirm(), {
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
      if (!response.ok) throw new Error("confirm_failed");
      const result = await response.json() as WorkflowAccepted;
      upsertWorkflow(result.workflow);
      setHiddenPaths((current) => new Set(current).add(video.path));
      setCandidatesByPath((current) => {
        const next = { ...current };
        delete next[video.path];
        return next;
      });
      setActiveReviewPath(null);
      setFeedback({ message: t("rootReviewQueued"), tone: "success" });
    } catch {
      setFeedback({ message: libraryT("rootConfirmFailed"), tone: "error" });
    } finally {
      setConfirmingKey(null);
    }
  };

  return (
    <article
      id="root-video-reviews"
      className="scroll-mt-32 border-y border-line py-6 md:col-span-2"
    >
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-3">
            <h3 className="text-sm font-medium tracking-widest text-ink uppercase">
              {t("rootReviewQueueTitle")}
            </h3>
            <span className="type-badge border border-line-strong px-2 py-1 text-ink-muted">
              {t("rootReviewQueueCount", { count: rootVideos.length })}
            </span>
          </div>
          <p className="mt-2 max-w-2xl text-xs leading-5 text-ink-disabled">
            {t("rootReviewQueueDesc")}
          </p>
        </div>
      </div>

      <div className="mt-5 min-h-5" aria-live="polite">
        {feedback ? <InlineFeedback tone={feedback.tone}>{feedback.message}</InlineFeedback> : null}
      </div>

      {isLoading ? <StateMessage state="loading">{t("rootReviewQueueLoading")}</StateMessage> : null}
      {error ? <StateMessage state="error">{t("rootReviewQueueLoadFailed")}</StateMessage> : null}
      {!isLoading && !error && rootVideos.length === 0 ? (
        <StateMessage>{t("rootReviewQueueEmpty")}</StateMessage>
      ) : null}

      {!isLoading && !error && rootVideos.length > 0 ? (
        <ul className="mt-5 divide-y divide-line border-t border-line">
          {rootVideos.map((video) => {
            const candidates = candidatesByPath[video.path] ?? [];
            const busyCandidateId = confirmingKey?.startsWith(`${video.path}:`)
              ? Number(confirmingKey.slice(video.path.length + 1))
              : null;
            return (
              <li key={video.path} className="min-w-0 py-5">
                <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                  <div className="min-w-0">
                    <p className="break-all text-sm font-medium text-ink" title={video.filename}>
                      {video.filename}
                    </p>
                    <p className="mt-1 text-xs text-ink-subtle">
                      {video.parsed_title}
                      {video.parsed_year ? ` · ${video.parsed_year}` : ""}
                    </p>
                  </div>
                  <span className={`type-badge inline-flex shrink-0 items-center gap-2 ${
                    video.stable ? "text-success" : "text-warning"
                  }`}>
                    {video.stable ? (
                      <FolderInput className="h-3.5 w-3.5" />
                    ) : (
                      <Clock3 className="h-3.5 w-3.5" />
                    )}
                    {video.stable ? libraryT("rootReady") : libraryT("rootWaitingForStability")}
                  </span>
                </div>

                {video.stable ? (
                  <div className="mt-4 min-w-0">
                    <MetadataCandidatePicker
                      busyCandidateId={busyCandidateId}
                      candidates={candidates}
                      disabled={Boolean(confirmingKey)}
                      inputValue={searchDrafts[video.path] ?? ""}
                      lookupBusy={reviewingPath === video.path}
                      lookupLabel={activeReviewPath === video.path
                        ? libraryT("rootLookupId")
                        : libraryT("rootReview")}
                      onInputChange={(value) => setSearchDrafts((current) => ({
                        ...current,
                        [video.path]: value,
                      }))}
                      onInputFocus={() => {
                        setActiveReviewPath(video.path);
                        setSearchDrafts((current) => ({
                          ...current,
                          [video.path]: current[video.path] ?? defaultSearchInput(video),
                        }));
                      }}
                      onLookup={() => void handleReview(video)}
                      onSelect={(candidate) => void handleConfirm(video, candidate.tmdb_id)}
                      placeholder={libraryT("rootUnifiedSearchPlaceholder")}
                      selectionBusy={Boolean(confirmingKey)}
                      showCandidates={activeReviewPath === video.path && candidates.length > 0}
                      showFewerLabel={libraryT("rootShowFewer")}
                      showMoreLabel={(count) => libraryT("rootShowMore", { count })}
                    />
                  </div>
                ) : null}
              </li>
            );
          })}
        </ul>
      ) : null}
    </article>
  );
}
