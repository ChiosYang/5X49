"use client";

import { Edit3, Info } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";

import ViewingInlineEditor, { ViewingQuickAdd } from "@/components/viewings/ViewingInlineEditor";
import ViewingReview from "@/components/viewings/ViewingReview";
import { StateMessage } from "@/components/ui/Feedback";
import { useFilmViewings } from "@/hooks/useFilm";
import { Link } from "@/i18n/routing";
import type { ViewingView } from "@/types/movie";

function formatDate(viewing: ViewingView, locale: string, unknown: string) {
  if (!viewing.watched_at || viewing.watched_at_precision === "unknown") return unknown;
  if (viewing.watched_at_precision === "year") return viewing.watched_at;
  const [year, month, day] = viewing.watched_at.slice(0, 10).split("-").map(Number);
  return new Intl.DateTimeFormat(locale, { year: "numeric", month: "long", day: "numeric" }).format(
    new Date(year, month - 1, day),
  );
}

export default function MovieViewingSection({
  filmId,
  embedded = false,
}: {
  filmId: string;
  filmTitle: string;
  embedded?: boolean;
}) {
  const t = useTranslations("Diary");
  const locale = useLocale();
  const { data, error, isLoading } = useFilmViewings(filmId);
  const [editorBusy, setEditorBusy] = useState(false);
  const [selected, setSelected] = useState<ViewingView | null>(null);
  const viewings = data || [];

  return (
    <section className={embedded ? "min-w-0" : "border-b border-line-strong px-8 py-10 md:px-16"}>
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 className={embedded ? "text-lg font-semibold tracking-tight text-ink" : "type-section-title text-ink"}>{t("filmSectionTitle")}</h2>
          {!isLoading && !error ? <p className="type-meta mt-1.5 text-ink-subtle">{t("viewingCount", { count: viewings.length })}</p> : null}
        </div>
        <div className="flex flex-col items-start gap-2 sm:flex-row sm:items-center">
          {viewings.length > 0 ? (
            <Link
              href={`/diary?film=${filmId}`}
              className="focus-ring duration-fast inline-flex min-h-10 items-center justify-center rounded-pill px-3.5 type-label text-ink-muted transition-colors hover:bg-surface-hover hover:text-ink"
            >
              {t("viewAll")}
            </Link>
          ) : null}
          <ViewingQuickAdd
            filmId={filmId}
          />
        </div>
      </div>

      <div className="mt-5">
        {selected ? <div id="film-viewing-editor" className="mb-5 max-w-2xl rounded-media border border-line bg-surface/60 p-5">
          <p className="font-semibold text-ink">{formatDate(selected, locale, t("unknownDate"))}</p>
          <ViewingInlineEditor key={selected.id} filmId={filmId} viewing={selected}
            onBusyChange={setEditorBusy} onCancel={() => setSelected(null)} />
        </div> : null}
        {isLoading ? <StateMessage state="loading">{t("loadingFilm")}</StateMessage> : null}
        {error ? <StateMessage state="error">{t("errorFilm")}</StateMessage> : null}
        {!isLoading && !error && viewings.length === 0 ? <p className="text-sm text-ink-subtle">{t("emptyFilm")}</p> : null}
        {!isLoading && viewings.length > 0 ? (
          <div className="divide-y divide-line border-t border-line">
            {viewings.slice(0, 3).map((viewing) => (
              <div key={viewing.id} className="min-w-0 py-3.5 first:pt-3.5">
                <div className="flex min-w-0 items-center justify-between gap-3">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium tabular-nums text-ink">{formatDate(viewing, locale, t("unknownDate"))}</p>
                    <p className="type-meta mt-1 truncate text-ink-subtle">{t("sourceLabel", {
                      source: viewing.source === "manual"
                        ? t("sources.manual")
                        : viewing.source === "diary"
                          ? t("sources.diary")
                          : t("sources.external", { source: viewing.source }),
                    })}</p>
                  </div>
                  <button
                    type="button"
                    disabled={editorBusy}
                    className="focus-ring duration-fast flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-line text-ink-muted transition-colors hover:border-line-strong hover:text-ink"
                    aria-label={viewing.editable ? t("editViewing") : t("viewViewing")}
                    title={viewing.editable ? t("editViewing") : t("viewViewing")}
                    aria-expanded={selected?.id === viewing.id}
                    onClick={() => {
                      setSelected((current) => current?.id === viewing.id ? null : viewing);
                      requestAnimationFrame(() => document.getElementById("film-viewing-editor")?.scrollIntoView({ block: "center" }));
                    }}
                  >
                    {viewing.editable ? <Edit3 className="h-3.5 w-3.5" /> : <Info className="h-3.5 w-3.5" />}
                  </button>
                </div>
                <ViewingReview viewing={viewing} />
              </div>
            ))}
          </div>
        ) : null}
      </div>
    </section>
  );
}
