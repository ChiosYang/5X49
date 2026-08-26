"use client";

import { ExternalLink, Loader2, Network } from "lucide-react";
import { useTranslations } from "next-intl";
import { useSWRConfig } from "swr";

import { Button } from "@/components/ui/Button";
import { InlineFeedback } from "@/components/ui/Feedback";
import { useAnalyzeFilm, useFilm, useFilmAnalysis } from "@/hooks/useFilm";
import { API } from "@/lib/api";
import type { LibraryFilmDetail } from "@/types/movie";

function predicateLabel(value: string) {
  return value.replaceAll("_", " ");
}

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
  const running = isMutating || film.analysis.status === "queued" || film.analysis.status === "running" || analysis?.status === "running";

  const triggerAnalysis = async () => {
    if (running) return;
    await analyze();
    await Promise.all([mutate(API.libraryFilm(filmId)), mutate(API.filmAnalysis(filmId))]);
  };

  return (
    <section className="space-y-8 px-8 py-14 md:px-16 md:py-20">
      <div className="flex flex-wrap items-end justify-between gap-6 border-b border-line-strong pb-6">
        <div>
          <p className="type-label text-ink-subtle">{t("subtitle")}</p>
          <h2 className="mt-2 type-display-editorial text-ink">{t("title")}</h2>
        </div>
        <Button onClick={triggerAnalysis} disabled={running} busy={running} variant="primary">
          {running ? t("analyzing") : t("trigger")}
        </Button>
      </div>

      {error && <InlineFeedback tone="error">{t("failedStatus")}</InlineFeedback>}
      {!analysis && !error && (
        <div className="flex items-center gap-3 text-ink-subtle">
          {running ? <Loader2 className="h-4 w-4 animate-spin" /> : <Network className="h-4 w-4" />}
          <span className="type-label">{running ? t("analyzing") : t("pendingStatus")}</span>
        </div>
      )}

      {analysis && (
        <div className="space-y-10">
          {analysis.summary && <p className="max-w-4xl type-editorial-lead text-ink-muted">{analysis.summary}</p>}

          {analysis.relations.length > 0 && (
            <div className="grid gap-px border border-line bg-line md:grid-cols-2 xl:grid-cols-3">
              {analysis.relations.map((relation) => (
                <article key={relation.id} className="min-w-0 bg-canvas p-5">
                  <div className="flex items-center justify-between gap-3">
                    <span className="type-badge text-ink-subtle">{predicateLabel(relation.predicate)}</span>
                    <span className="rounded-pill border border-line px-2 py-1 type-badge text-ink-subtle">
                      {relation.review_status}
                    </span>
                  </div>
                  <h3 className="mt-5 truncate type-card-title text-ink">
                    {relation.target.display_name || relation.target.entity_id}
                  </h3>
                  {relation.rationale && <p className="mt-3 line-clamp-4 type-body text-ink-muted">{relation.rationale}</p>}
                </article>
              ))}
            </div>
          )}

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
                    className="focus-ring group flex min-w-0 items-start justify-between gap-4 border border-line p-4 transition-colors duration-fast hover:border-line-strong"
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

          {analysis.reviews.length > 0 && (
            <p className="type-meta text-warning" aria-live="polite">
              {t("referencesNeedReview", { count: analysis.reviews.filter((review) => review.status === "open").length })}
            </p>
          )}
        </div>
      )}
    </section>
  );
}
