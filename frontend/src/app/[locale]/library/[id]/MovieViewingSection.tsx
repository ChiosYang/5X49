"use client";

import { Edit3, Info } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";

import ViewingInlineEditor, { ViewingQuickAdd } from "@/components/viewings/ViewingInlineEditor";
import { StateMessage } from "@/components/ui/Feedback";
import { useFilmViewings } from "@/hooks/useFilm";
import { Link, useRouter } from "@/i18n/routing";
import type { ViewingView } from "@/types/movie";

function formatDate(viewing: ViewingView, locale: string, unknown: string) {
  if (!viewing.watched_at || viewing.watched_at_precision === "unknown") return unknown;
  if (viewing.watched_at_precision === "year") return viewing.watched_at;
  const [year, month, day] = viewing.watched_at.slice(0, 10).split("-").map(Number);
  return new Intl.DateTimeFormat(locale, { year: "numeric", month: "long", day: "numeric" }).format(
    new Date(year, month - 1, day),
  );
}

export default function MovieViewingSection({ filmId }: { filmId: string; filmTitle: string }) {
  const t = useTranslations("Diary");
  const locale = useLocale();
  const router = useRouter();
  const { data, error, isLoading, mutate } = useFilmViewings(filmId);
  const [selected, setSelected] = useState<ViewingView | null>(null);
  const viewings = data || [];

  return (
    <section className="border-b border-line-strong px-8 py-10 md:px-16">
      <div className="flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <span className="type-label block text-ink-subtle">{t("filmSectionEyebrow")}</span>
          <h2 className="mt-2 font-serif text-3xl text-ink">{t("filmSectionTitle")}</h2>
          {!isLoading && !error ? <p className="type-meta mt-2 text-ink-subtle">{t("viewingCount", { count: viewings.length })}</p> : null}
        </div>
        <div className="flex flex-col gap-2 sm:flex-row">
          {viewings.length > 0 ? (
            <Link
              href={`/diary?film=${filmId}`}
              className="focus-ring duration-fast inline-flex min-h-11 items-center justify-center px-5 type-label text-ink-muted transition-colors hover:bg-surface-hover hover:text-ink"
            >
              {t("viewAll")}
            </Link>
          ) : null}
          <ViewingQuickAdd
            filmId={filmId}
            onSaved={async () => { await mutate(); router.refresh(); }}
          />
        </div>
      </div>

      <div className="mt-6">
        {isLoading ? <StateMessage state="loading">{t("loadingFilm")}</StateMessage> : null}
        {error ? <StateMessage state="error">{t("errorFilm")}</StateMessage> : null}
        {!isLoading && !error && viewings.length === 0 ? <StateMessage>{t("emptyFilm")}</StateMessage> : null}
        {!isLoading && !error && viewings.length > 0 ? (
          <div className="grid gap-3 md:grid-cols-3">
            {viewings.slice(0, 3).map((viewing) => (
              <div key={viewing.id} className="min-w-0 border border-line p-4">
                <div className="flex min-w-0 items-center justify-between gap-3">
                  <div className="min-w-0">
                    <p className="truncate font-bold text-ink">{formatDate(viewing, locale, t("unknownDate"))}</p>
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
                    className="focus-ring flex h-9 w-9 shrink-0 items-center justify-center border border-line text-ink-muted hover:text-ink"
                    aria-label={viewing.editable ? t("editViewing") : t("viewViewing")}
                    title={viewing.editable ? t("editViewing") : t("viewViewing")}
                    aria-expanded={selected?.id === viewing.id}
                    onClick={() => setSelected((current) => current?.id === viewing.id ? null : viewing)}
                  >
                    {viewing.editable ? <Edit3 className="h-4 w-4" /> : <Info className="h-4 w-4" />}
                  </button>
                </div>
                {selected?.id === viewing.id ? (
                  <ViewingInlineEditor
                    key={viewing.id}
                    filmId={filmId}
                    viewing={viewing}
                    onCancel={() => setSelected(null)}
                    onSaved={async () => { await mutate(); router.refresh(); }}
                  />
                ) : null}
              </div>
            ))}
          </div>
        ) : null}
      </div>
    </section>
  );
}
