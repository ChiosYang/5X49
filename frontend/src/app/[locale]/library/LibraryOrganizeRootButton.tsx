"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { FolderInput, Loader2, Search } from "lucide-react";
import { API } from "@/lib/api";
import type { MetadataSearchResult, RootVideo } from "@/types/movie";

const DEFAULT_VISIBLE_CANDIDATES = 5;

const parseTmdbId = (value: string) => {
  const trimmed = value.trim();
  const match = trimmed.match(/(?:movie\/)?(\d+)/);
  return match ? Number(match[1]) : null;
};

const parseSearchInput = (value: string) => {
  const yearMatch = value.match(/\b(19\d{2}|20\d{2})\b/);
  return {
    query: value.replace(/\b(19\d{2}|20\d{2})\b/, "").trim() || value.trim(),
    year: yearMatch ? Number(yearMatch[1]) : null,
  };
};

const prependCandidate = (
  candidates: MetadataSearchResult[],
  candidate: MetadataSearchResult,
) => [candidate, ...candidates.filter((item) => item.tmdb_id !== candidate.tmdb_id)];

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
  const [expandedPaths, setExpandedPaths] = useState<Record<string, boolean>>({});

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
          [video.path]: prependCandidate(current[video.path] || [], candidate),
        }));
        setExpandedPaths((current) => ({ ...current, [video.path]: false }));
        return;
      }

      const { query, year } = parseSearchInput(input);
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
      setExpandedPaths((current) => ({ ...current, [video.path]: false }));
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
        className="relative flex h-10 w-10 items-center justify-center border border-neutral-800 bg-neutral-950 text-white transition-colors"
        aria-label={t("rootPending", { count: pendingCount })}
        title={t("organizeRoot")}
      >
        <FolderInput className="h-4 w-4" />
        {pendingCount > 0 && (
          <span className="absolute -right-1.5 -top-1.5 flex min-h-4 min-w-4 items-center justify-center border border-black bg-white px-1 text-[10px] font-bold leading-none text-black">
            {pendingCount > 99 ? "99+" : pendingCount}
          </span>
        )}
      </div>

      {pendingCount > 0 && (
        <div className="pointer-events-none absolute right-0 top-full z-50 w-[min(24rem,calc(100vw-4rem))] pt-3 opacity-0 transition-opacity duration-150 group-hover/root-organize:pointer-events-auto group-hover/root-organize:opacity-100 group-focus-within/root-organize:pointer-events-auto group-focus-within/root-organize:opacity-100">
          <div className="border border-neutral-800 bg-black/95 p-4 shadow-2xl shadow-black/60 backdrop-blur">
            <div className="mb-3 flex items-center justify-between gap-4 border-b border-neutral-900 pb-3">
              <p className="text-xs font-bold uppercase tracking-widest text-neutral-400">
                {t("rootPending", { count: pendingCount })}
              </p>
            </div>
            <div className="scrollbar-minimal max-h-72 overflow-y-auto pr-1">
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
                    </div>
                    {video.stable && (
                      <div className="mt-3 space-y-2">
                        <div className="flex gap-2">
                          <input
                            type="text"
                            value={searchDrafts[video.path] ?? ""}
                            onChange={(event) => setSearchDrafts((current) => ({
                              ...current,
                              [video.path]: event.target.value,
                            }))}
                            onFocus={() => {
                              setActiveReviewPath(video.path);
                              setSearchDrafts((current) => ({
                                ...current,
                                [video.path]: current[video.path] ?? [
                                  video.parsed_title || video.filename,
                                  video.parsed_year || "",
                                ].filter(Boolean).join(" "),
                              }));
                            }}
                            placeholder={t("rootUnifiedSearchPlaceholder")}
                            className="min-w-0 flex-1 border border-neutral-800 bg-neutral-950 px-3 py-2 text-xs text-white placeholder:text-neutral-600 focus:border-neutral-500 focus:outline-none"
                          />
                          <button
                            type="button"
                            onClick={() => handleReview(video)}
                            disabled={reviewingPath === video.path || Boolean(confirmingKey)}
                            className="flex h-9 w-24 items-center justify-center gap-1.5 border border-neutral-800 bg-neutral-950 px-2 text-[10px] font-bold uppercase tracking-widest text-white transition-colors hover:border-neutral-500 disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            {reviewingPath === video.path ? (
                              <Loader2 className="h-3 w-3 animate-spin" />
                            ) : (
                              <Search className="h-3 w-3" />
                            )}
                            {activeReviewPath === video.path ? t("rootLookupId") : t("rootReview")}
                          </button>
                        </div>
                        {activeReviewPath === video.path && (
                          <>
                        {(expandedPaths[video.path]
                          ? candidatesByPath[video.path] || []
                          : (candidatesByPath[video.path] || []).slice(0, DEFAULT_VISIBLE_CANDIDATES)
                        ).map((candidate) => {
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
                                {confirmingKey === key && <Loader2 className="mt-0.5 h-3 w-3 shrink-0 animate-spin" />}
                              </span>
                            </button>
                          );
                        })}
                        {(candidatesByPath[video.path] || []).length > DEFAULT_VISIBLE_CANDIDATES && (
                          <button
                            type="button"
                            onClick={() => setExpandedPaths((current) => ({
                              ...current,
                              [video.path]: !current[video.path],
                            }))}
                            className="text-[10px] font-bold uppercase tracking-widest text-neutral-500 hover:text-white"
                          >
                            {expandedPaths[video.path]
                              ? t("rootShowFewer")
                              : t("rootShowMore", {
                                count: (candidatesByPath[video.path] || []).length - DEFAULT_VISIBLE_CANDIDATES,
                              })}
                          </button>
                        )}
                          </>
                        )}
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
