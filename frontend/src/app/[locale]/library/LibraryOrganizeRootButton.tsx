"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { FolderInput } from "lucide-react";
import {
  MetadataCandidatePicker,
  parseMetadataSearchInput,
  parseTmdbId,
  prependMetadataCandidate,
} from "@/components/metadata/MetadataCandidatePicker";
import { API } from "@/lib/api";
import type { MetadataSearchResult, RootVideo } from "@/types/movie";

interface LibraryOrganizeRootButtonProps {
  rootVideos?: RootVideo[];
}

export default function LibraryOrganizeRootButton({
  rootVideos = [],
}: LibraryOrganizeRootButtonProps) {
  const t = useTranslations("Library");
  const router = useRouter();
  const [candidatesByPath, setCandidatesByPath] = useState<Record<string, MetadataSearchResult[]>>({});
  const [reviewingPath, setReviewingPath] = useState<string | null>(null);
  const [activeReviewPath, setActiveReviewPath] = useState<string | null>(null);
  const [confirmingKey, setConfirmingKey] = useState<string | null>(null);
  const [reviewError, setReviewError] = useState<string>("");
  const [searchDrafts, setSearchDrafts] = useState<Record<string, string>>({});

  const pendingCount = rootVideos.length;

  const handleReview = async (video: RootVideo) => {
    setReviewError("");
    setActiveReviewPath(video.path);
    setReviewingPath(video.path);
    try {
      const input = searchDrafts[video.path]?.trim() || [
        video.parsed_title || video.filename,
        video.parsed_year || "",
      ].filter(Boolean).join(" ");
      const tmdbId = parseTmdbId(input);
      setSearchDrafts((current) => ({ ...current, [video.path]: input }));

      if (tmdbId) {
        const res = await fetch(API.metadataMovie(tmdbId));
        if (!res.ok) {
          throw new Error("lookup_failed");
        }
        const candidate = await res.json() as MetadataSearchResult;
        setCandidatesByPath((current) => ({
          ...current,
          [video.path]: prependMetadataCandidate(current[video.path] || [], candidate),
        }));
        return;
      }

      const { query, year } = parseMetadataSearchInput(input);
      const params = new URLSearchParams({ query });
      if (year) {
        params.set("year", String(year));
      }
      const res = await fetch(`${API.metadataSearch()}?${params.toString()}`);
      if (!res.ok) {
        throw new Error("search_failed");
      }
      const candidates = await res.json() as MetadataSearchResult[];
      setCandidatesByPath((current) => ({ ...current, [video.path]: candidates }));
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
      setActiveReviewPath(null);
      router.refresh();
    } catch {
      setReviewError(t("rootConfirmFailed"));
    } finally {
      setConfirmingKey(null);
    }
  };

  return (
    <div className="group/root-organize relative">
      <div
        className="relative flex h-10 w-10 items-center justify-center border border-line-strong bg-surface text-ink transition-colors"
        aria-label={t("rootPending", { count: pendingCount })}
        title={t("organizeRoot")}
      >
        <FolderInput className="h-4 w-4" />
        {pendingCount > 0 && (
          <span className="absolute -top-1.5 -right-1.5 flex min-h-4 min-w-4 items-center justify-center border border-canvas bg-inverse px-1 text-[10px] font-bold leading-none text-inverse-ink">
            {pendingCount > 99 ? "99+" : pendingCount}
          </span>
        )}
      </div>

      {pendingCount > 0 && (
        <div className="z-popover duration-standard pointer-events-none absolute top-full right-0 w-[min(24rem,calc(100vw-4rem))] pt-3 opacity-0 transition-opacity group-hover/root-organize:pointer-events-auto group-hover/root-organize:opacity-100 group-focus-within/root-organize:pointer-events-auto group-focus-within/root-organize:opacity-100">
          <div className="liquid-glass-popover relative border border-line/80 p-4">
            <div className="mb-3 flex items-center justify-between gap-4 border-b border-line pb-3">
              <p className="type-label text-ink-muted">
                {t("rootPending", { count: pendingCount })}
              </p>
            </div>
            <div className="scrollbar-minimal max-h-72 overflow-y-auto pr-1">
              <ul className="space-y-3">
                {rootVideos.map((video) => (
                  <li key={video.path} className="min-w-0 border-b border-line pb-3 last:border-b-0 last:pb-0">
                    <p className="truncate text-sm text-ink-muted" title={video.filename}>
                      {video.filename}
                    </p>
                    <div className="mt-1 flex items-center justify-between gap-3">
                      <p className="text-xs text-ink-subtle">
                        {video.stable ? t("rootReady") : t("rootWaitingForStability")}
                      </p>
                    </div>
                    {video.stable && (
                      <div className="mt-3 space-y-2">
                        <MetadataCandidatePicker
                          key={`${video.path}:${reviewingPath === video.path ? "searching" : (candidatesByPath[video.path] || []).map((candidate) => candidate.tmdb_id).join(",")}`}
                          candidates={candidatesByPath[video.path] || []}
                          inputValue={searchDrafts[video.path] ?? ""}
                          onInputChange={(value) => setSearchDrafts((current) => ({
                            ...current,
                            [video.path]: value,
                          }))}
                          onInputFocus={() => {
                            setActiveReviewPath(video.path);
                            setSearchDrafts((current) => ({
                              ...current,
                              [video.path]: current[video.path] ?? [
                                video.parsed_title || video.filename,
                                video.parsed_year || "",
                              ].filter(Boolean).join(" "),
                            }));
                          }}
                          onLookup={() => handleReview(video)}
                          onSelect={(candidate) => handleConfirm(video, candidate.tmdb_id)}
                          lookupBusy={reviewingPath === video.path}
                          selectionBusy={Boolean(confirmingKey)}
                          busyCandidateId={confirmingKey?.startsWith(`${video.path}:`)
                            ? Number(confirmingKey.slice(video.path.length + 1))
                            : null}
                          disabled={Boolean(confirmingKey)}
                          showCandidates={activeReviewPath === video.path}
                          lookupLabel={activeReviewPath === video.path ? t("rootLookupId") : t("rootReview")}
                          placeholder={t("rootUnifiedSearchPlaceholder")}
                          showFewerLabel={t("rootShowFewer")}
                          showMoreLabel={(count) => t("rootShowMore", { count })}
                        />
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            </div>
            {reviewError && (
              <p className="mt-3 border-t border-line pt-3 text-xs tracking-widest text-danger uppercase">
                {reviewError}
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
