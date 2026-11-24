"use client";

import { ExternalLink, Loader2, Network } from "lucide-react";
import { useTranslations } from "next-intl";
import { useSWRConfig } from "swr";
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { InlineFeedback } from "@/components/ui/Feedback";
import { useAnalyzeFilm, useFilm, useFilmAnalysis } from "@/hooks/useFilm";
import { API } from "@/lib/api";
import type { LibraryFilmDetail } from "@/types/movie";
import AnalysisReviewPanel from "@/components/AnalysisReviewPanel";

export default function MovieAnalysisSection({
  filmId,
  initialFilm,
}: {
  filmId: string;
  initialFilm: LibraryFilmDetail;
}) {
  const t = useTranslations("Genealogy");
  const { mutate } = useSWRConfig();
  const { data: film = initialFilm } = useFilm(filmId, initialFilm);
  const { data: analysis, error } = useFilmAnalysis(filmId);
  const { trigger: analyze, isMutating } = useAnalyzeFilm(filmId);
  const [triggerFailed, setTriggerFailed] = useState(false);
  const running = isMutating || film.analysis.status === "queued" || film.analysis.status === "running" || analysis?.status === "running";

  const triggerAnalysis = async () => {
    if (running) return;
    setTriggerFailed(false);
    try {
      await analyze();
      await Promise.all([mutate(API.libraryFilm(filmId)), mutate(API.filmAnalysis(filmId))]);
    } catch {
      setTriggerFailed(true);
    }
  };

  const hasAnalysis = Boolean(analysis);

  return (
    <section
      id="film-analysis"
      tabIndex={-1}
      className={
        hasAnalysis
          ? "space-y-8 border-b border-line-strong px-8 py-12 md:px-16 md:py-14"
          : "space-y-4 border-b border-line-strong px-8 py-7 md:px-16 md:py-8"
      }
    >
      <div className={hasAnalysis ? "flex flex-wrap items-end justify-between gap-6 border-b border-line-strong pb-6" : "flex flex-wrap items-center justify-between gap-4"}>
        <div className={hasAnalysis ? undefined : "flex flex-wrap items-center gap-x-5 gap-y-2"}>
          <h2 className={hasAnalysis ? "type-section-title text-ink" : "text-lg font-semibold tracking-tight text-ink"}>{t("title")}</h2>
          {!hasAnalysis && !error && (
            <div className="flex items-center gap-2 text-ink-subtle">
              {running ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Network className="h-3.5 w-3.5" />}
              <span className="type-meta">{running ? t("analyzing") : t("pendingStatus")}</span>
            </div>
          )}
        </div>
        <Button size="sm" onClick={triggerAnalysis} disabled={running} busy={running} variant="primary" className="rounded-pill px-5">
          {running ? t("analyzing") : t("trigger")}
        </Button>
      </div>

      {(error || triggerFailed || analysis?.status === "failed") && <InlineFeedback tone="error">{t("failedStatus")}</InlineFeedback>}

      {analysis && (
        <div className="space-y-10">
          {analysis.summary && <p className="max-w-4xl type-editorial-lead text-ink-muted">{analysis.summary}</p>}

          <AnalysisReviewPanel key={`${analysis.run.id}:${analysis.status}`} filmId={filmId} />

          {analysis.evidence.length > 0 && (
            <div className="space-y-4">
              <h3 className="type-section-title text-ink">{t("evidence")}</h3>
              <div className="grid gap-3 lg:grid-cols-2">
                {analysis.evidence.map((evidence) => (
                  <a
                    key={evidence.id}
                    href={evidence.source_uri}
                    target="_blank"
                    rel="noreferrer"
                    className="focus-ring group flex min-w-0 items-start justify-between gap-4 rounded-media border border-line p-4 transition-colors duration-fast hover:border-line-strong"
                  >
                    <div className="min-w-0">
                      <p className="truncate font-bold text-ink">{evidence.source_title}</p>
                      <p className="mt-2 line-clamp-2 type-body text-ink-muted">{evidence.claim}</p>
                    </div>
                    <ExternalLink className="h-4 w-4 shrink-0 text-ink-subtle transition-colors group-hover:text-ink" />
                  </a>
                ))}
              </div>
            </div>
          )}

        </div>
      )}
    </section>
  );
}
