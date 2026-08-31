"use client";

import { ArrowRight, Clock3, FileText, FolderInput, FolderOutput, ImageIcon } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useMemo, useState } from "react";
import useSWR from "swr";

import {
  MetadataCandidatePicker,
  parseMetadataSearchInput,
  parseTmdbId,
  prependMetadataCandidate,
} from "@/components/metadata/MetadataCandidatePicker";
import { Button } from "@/components/ui/Button";
import { InlineFeedback, Spinner, StateMessage } from "@/components/ui/Feedback";
import { ToggleSwitch } from "@/components/ui/FormControls";
import { useWorkflowCache, useWorkflows } from "@/hooks/useWorkflows";
import { API } from "@/lib/api";
import type {
  MetadataSearchResult,
  OrganizationCandidate,
  OrganizationPreview,
  WorkflowAccepted,
} from "@/types/movie";

type RenameStyle = "preserve_stem" | "title_year";

function defaultSearchInput(video: OrganizationCandidate) {
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
  const { data, error, isLoading, mutate } = useSWR<OrganizationCandidate[]>(
    API.libraryOrganizationCandidates(),
  );
  const { upsertWorkflow } = useWorkflowCache();
  const { data: workflows = [] } = useWorkflows();
  const [workflowPaths, setWorkflowPaths] = useState<Record<string, string>>({});
  const [candidatesByPath, setCandidatesByPath] = useState<Record<string, MetadataSearchResult[]>>({});
  const [selectedByPath, setSelectedByPath] = useState<Record<string, MetadataSearchResult>>({});
  const [previewsByPath, setPreviewsByPath] = useState<Record<string, OrganizationPreview>>({});
  const [renameStyles, setRenameStyles] = useState<Record<string, RenameStyle>>({});
  const [searchDrafts, setSearchDrafts] = useState<Record<string, string>>({});
  const [activeReviewPath, setActiveReviewPath] = useState<string | null>(null);
  const [reviewingPath, setReviewingPath] = useState<string | null>(null);
  const [previewingPath, setPreviewingPath] = useState<string | null>(null);
  const [confirmingPath, setConfirmingPath] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<{
    message: string;
    tone: "error" | "success";
  } | null>(null);

  const pendingFiles = useMemo(
    () => (data ?? []).filter((video) => {
      const workflowId = workflowPaths[video.source_path];
      if (!workflowId) return true;
      const workflow = workflows.find((item) => item.id === workflowId);
      return workflow?.status === "failed" || workflow?.status === "cancelled";
    }),
    [data, workflowPaths, workflows],
  );

  useEffect(() => {
    if (!refreshSignal) return;
    void mutate().catch(() => undefined);
  }, [refreshSignal, mutate]);

  useEffect(() => {
    const succeededPaths = Object.entries(workflowPaths)
      .filter(([, workflowId]) => workflows.some(
        (workflow) => workflow.id === workflowId && workflow.status === "succeeded",
      ))
      .map(([sourcePath]) => sourcePath);
    if (succeededPaths.length > 0) {
      void mutate().then(() => {
        const completedPaths = new Set(succeededPaths);
        setWorkflowPaths((current) => Object.fromEntries(
          Object.entries(current).filter(([sourcePath]) => !completedPaths.has(sourcePath)),
        ));
      }).catch(() => undefined);
    }
  }, [mutate, workflowPaths, workflows]);

  const clearSelection = (sourcePath: string) => {
    setSelectedByPath((current) => {
      const next = { ...current };
      delete next[sourcePath];
      return next;
    });
    setPreviewsByPath((current) => {
      const next = { ...current };
      delete next[sourcePath];
      return next;
    });
  };

  const requestPreview = async (
    video: OrganizationCandidate,
    candidate: MetadataSearchResult,
    renameStyle: RenameStyle,
  ) => {
    setFeedback(null);
    setPreviewingPath(video.source_path);
    setSelectedByPath((current) => ({ ...current, [video.source_path]: candidate }));
    setPreviewsByPath((current) => {
      const next = { ...current };
      delete next[video.source_path];
      return next;
    });
    try {
      const response = await fetch(API.libraryOrganizationPreview(), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          source_path: video.source_path,
          tmdb_id: candidate.tmdb_id,
          rename_style: renameStyle,
        }),
      });
      if (!response.ok) {
        throw new Error(t("organizationPreviewFailed"));
      }
      const preview = await response.json() as OrganizationPreview;
      setPreviewsByPath((current) => ({ ...current, [video.source_path]: preview }));
    } catch (previewError) {
      setFeedback({
        message: previewError instanceof Error ? previewError.message : t("organizationPreviewFailed"),
        tone: "error",
      });
    } finally {
      setPreviewingPath(null);
    }
  };

  const handleReview = async (video: OrganizationCandidate) => {
    setFeedback(null);
    setActiveReviewPath(video.source_path);
    setReviewingPath(video.source_path);
    clearSelection(video.source_path);
    try {
      const input = searchDrafts[video.source_path]?.trim() || defaultSearchInput(video);
      const tmdbId = parseTmdbId(input);
      setSearchDrafts((current) => ({ ...current, [video.source_path]: input }));

      if (tmdbId) {
        const response = await fetch(API.metadataMovie(tmdbId));
        if (!response.ok) throw new Error(t("organizationCandidateFailed"));
        const candidate = await response.json() as MetadataSearchResult;
        setCandidatesByPath((current) => ({
          ...current,
          [video.source_path]: prependMetadataCandidate(current[video.source_path] ?? [], candidate),
        }));
        return;
      }

      const { query, year } = parseMetadataSearchInput(input);
      const params = new URLSearchParams({ query });
      if (year) params.set("year", String(year));
      const response = await fetch(`${API.metadataSearch()}?${params}`);
      if (!response.ok) throw new Error(t("organizationCandidateFailed"));
      const candidates = await response.json() as MetadataSearchResult[];
      setCandidatesByPath((current) => ({ ...current, [video.source_path]: candidates }));
      if (candidates.length === 0) {
        setFeedback({ message: libraryT("rootNoCandidates"), tone: "error" });
      }
    } catch (reviewError) {
      setFeedback({
        message: reviewError instanceof Error ? reviewError.message : libraryT("rootReviewFailed"),
        tone: "error",
      });
    } finally {
      setReviewingPath(null);
    }
  };

  const handleConfirm = async (video: OrganizationCandidate, preview: OrganizationPreview) => {
    setFeedback(null);
    setConfirmingPath(video.source_path);
    try {
      const response = await fetch(API.libraryOrganizationConfirm(), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          source_path: video.source_path,
          tmdb_id: preview.match.tmdb_id,
          rename_style: preview.rename_style,
          confirmation_token: preview.confirmation_token,
        }),
      });
      if (!response.ok) {
        setPreviewsByPath((current) => {
          const next = { ...current };
          delete next[video.source_path];
          return next;
        });
        throw new Error(t("organizationConfirmFailed"));
      }
      const result = await response.json() as WorkflowAccepted;
      upsertWorkflow(result.workflow);
      setWorkflowPaths((current) => ({ ...current, [video.source_path]: result.workflow.id }));
      setActiveReviewPath(null);
      setFeedback({ message: t("organizationQueued"), tone: "success" });
    } catch (confirmError) {
      setFeedback({
        message: confirmError instanceof Error ? confirmError.message : t("organizationConfirmFailed"),
        tone: "error",
      });
    } finally {
      setConfirmingPath(null);
    }
  };

  return (
    <article id="file-organization-reviews" className="scroll-mt-32 border-y border-line py-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-3">
            <h3 className="text-sm font-medium tracking-widest text-ink uppercase">
              {t("organizationQueueTitle")}
            </h3>
            <span className="type-badge border border-line-strong px-2 py-1 text-ink-muted">
              {t("organizationQueueCount", { count: pendingFiles.length })}
            </span>
          </div>
          <p className="mt-2 max-w-3xl text-xs leading-5 text-ink-disabled">
            {t("organizationQueueDesc")}
          </p>
        </div>
      </div>

      <div className="mt-5 min-h-5" aria-live="polite">
        {feedback ? <InlineFeedback tone={feedback.tone}>{feedback.message}</InlineFeedback> : null}
      </div>

      {isLoading ? <StateMessage state="loading">{t("organizationQueueLoading")}</StateMessage> : null}
      {error ? <StateMessage state="error">{t("organizationQueueLoadFailed")}</StateMessage> : null}
      {!isLoading && !error && pendingFiles.length === 0 ? (
        <StateMessage>{t("organizationQueueEmpty")}</StateMessage>
      ) : null}

      {!isLoading && !error && pendingFiles.length > 0 ? (
        <ul className="mt-5 divide-y divide-line border-t border-line">
          {pendingFiles.map((video) => {
            const candidates = candidatesByPath[video.source_path] ?? [];
            const selected = selectedByPath[video.source_path];
            const preview = previewsByPath[video.source_path];
            const renameStyle = renameStyles[video.source_path] ?? "preserve_stem";
            const busy = confirmingPath === video.source_path;
            return (
              <li key={video.source_path} className="min-w-0 py-6">
                <div className="flex min-w-0 flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="break-all text-sm font-medium text-ink" title={video.filename}>
                        {video.filename}
                      </p>
                      <span className="type-badge border border-line px-2 py-1 text-ink-subtle">
                        {video.source_location === "legacy_inbox"
                          ? t("organizationSourceInbox")
                          : t("organizationSourceRoot")}
                      </span>
                    </div>
                    <p className="mt-1 text-xs text-ink-subtle">
                      {video.parsed_title}
                      {video.parsed_year ? ` · ${video.parsed_year}` : ""}
                    </p>
                  </div>
                  <span className={`type-badge inline-flex shrink-0 items-center gap-2 ${
                    video.stable ? "text-success" : "text-warning"
                  }`}>
                    {video.stable ? <FolderInput className="h-3.5 w-3.5" /> : <Clock3 className="h-3.5 w-3.5" />}
                    {video.stable ? libraryT("rootReady") : libraryT("rootWaitingForStability")}
                  </span>
                </div>

                {video.stable ? (
                  <div className="mt-5 grid min-w-0 gap-5 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
                    <MetadataCandidatePicker
                      candidates={candidates}
                      disabled={busy || previewingPath === video.source_path}
                      inputValue={searchDrafts[video.source_path] ?? ""}
                      lookupBusy={reviewingPath === video.source_path}
                      lookupLabel={activeReviewPath === video.source_path ? libraryT("rootLookupId") : libraryT("rootReview")}
                      onInputChange={(value) => {
                        setSearchDrafts((current) => ({ ...current, [video.source_path]: value }));
                        clearSelection(video.source_path);
                      }}
                      onInputFocus={() => {
                        setActiveReviewPath(video.source_path);
                        setSearchDrafts((current) => ({
                          ...current,
                          [video.source_path]: current[video.source_path] ?? defaultSearchInput(video),
                        }));
                      }}
                      onLookup={() => void handleReview(video)}
                      onSelect={(candidate) => void requestPreview(video, candidate, renameStyle)}
                      placeholder={libraryT("rootUnifiedSearchPlaceholder")}
                      selectionBusy={previewingPath === video.source_path}
                      busyCandidateId={selected?.tmdb_id}
                      showCandidates={activeReviewPath === video.source_path && candidates.length > 0}
                      showFewerLabel={libraryT("rootShowFewer")}
                      showMoreLabel={(count) => libraryT("rootShowMore", { count })}
                    />

                    <div className="min-w-0 border border-line bg-surface/40 p-4 sm:p-5">
                      {!selected && previewingPath !== video.source_path ? (
                        <p className="text-xs leading-5 text-ink-disabled">{t("organizationSelectCandidate")}</p>
                      ) : null}
                      {previewingPath === video.source_path ? (
                        <div className="flex min-h-24 items-center justify-center gap-3 text-xs text-ink-subtle">
                          <Spinner className="h-4 w-4" />
                          {t("organizationPreviewLoading")}
                        </div>
                      ) : null}
                      {preview ? (
                        <div className="space-y-5">
                          <div className="flex items-start justify-between gap-4">
                            <div>
                              <p className="type-label text-ink-subtle">{t("organizationPlan")}</p>
                              <p className="mt-2 text-sm font-semibold text-ink">
                                {selected?.title ?? preview.match.title} {preview.match.year ? `(${preview.match.year})` : ""}
                              </p>
                              <p className="mt-1 type-meta text-ink-subtle">TMDB {preview.match.tmdb_id}</p>
                            </div>
                            <div className="flex items-center gap-3">
                              <span className="hidden text-xs text-ink-subtle sm:inline">{t("organizationStandardize")}</span>
                              <ToggleSwitch
                                checked={renameStyle === "title_year"}
                                disabled={busy}
                                label={t("organizationStandardize")}
                                onChange={() => {
                                  const nextStyle: RenameStyle = renameStyle === "title_year" ? "preserve_stem" : "title_year";
                                  setRenameStyles((current) => ({ ...current, [video.source_path]: nextStyle }));
                                  if (selected) void requestPreview(video, selected, nextStyle);
                                }}
                              />
                            </div>
                          </div>

                          <div className="grid min-w-0 gap-3 text-xs sm:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] sm:items-center">
                            <div className="min-w-0 border-l border-line-strong pl-3">
                              <p className="type-label text-ink-disabled">{t("organizationSource")}</p>
                              <p className="mt-2 break-all text-ink-muted">{preview.source.filename}</p>
                            </div>
                            <ArrowRight className="hidden h-4 w-4 text-ink-disabled sm:block" />
                            <div className="min-w-0 border-l border-line-strong pl-3">
                              <p className="type-label text-ink-disabled">{t("organizationTarget")}</p>
                              <p className="mt-2 break-all text-ink">{preview.target.folder_name}</p>
                              <p className="mt-1 break-all text-ink-muted">{preview.target.video_name}</p>
                            </div>
                          </div>

                          {preview.sidecars.length > 0 ? (
                            <div>
                              <p className="type-label text-ink-disabled">{t("organizationSidecars")}</p>
                              <ul className="mt-2 space-y-2">
                                {preview.sidecars.map((sidecar) => (
                                  <li key={sidecar.source_name} className={`flex min-w-0 items-start gap-2 text-xs ${sidecar.conflict ? "text-danger" : "text-ink-muted"}`}>
                                    <FileText className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                                    <span className="min-w-0 break-all">{sidecar.source_name} → {sidecar.target_name}</span>
                                  </li>
                                ))}
                              </ul>
                            </div>
                          ) : null}

                          <div className="flex flex-wrap gap-2 type-badge text-ink-subtle">
                            <span className="inline-flex items-center gap-2 border border-line px-2 py-1">
                              <FolderOutput className="h-3.5 w-3.5" />{t("organizationMove")}
                            </span>
                            {preview.post_actions.write_nfo ? (
                              <span className="inline-flex items-center gap-2 border border-line px-2 py-1">
                                <FileText className="h-3.5 w-3.5" />NFO
                              </span>
                            ) : null}
                            {preview.post_actions.download_artwork ? (
                              <span className="inline-flex items-center gap-2 border border-line px-2 py-1">
                                <ImageIcon className="h-3.5 w-3.5" />{t("organizationArtwork")}
                              </span>
                            ) : null}
                          </div>

                          {preview.conflicts.length > 0 ? (
                            <InlineFeedback tone="error">
                              {t("organizationConflicts", {
                                names: preview.conflicts.map((conflict) => conflict.name).join(", "),
                              })}
                            </InlineFeedback>
                          ) : null}

                          <Button
                            responsiveWidth
                            busy={busy}
                            disabled={!preview.can_confirm || previewingPath === video.source_path}
                            onClick={() => void handleConfirm(video, preview)}
                          >
                            {t("organizationConfirm")}
                          </Button>
                        </div>
                      ) : null}
                    </div>
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
