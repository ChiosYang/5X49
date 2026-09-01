"use client";

import { CheckCircle2, ChevronRight, Film } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useMemo, useState } from "react";

import { InlineFeedback, StateMessage } from "@/components/ui/Feedback";
import { useLibrary } from "@/hooks/useLibrary";
import { Link, useRouter } from "@/i18n/routing";
import type { LibraryFilmSummary } from "@/types/movie";
import { MetadataReviewInspector } from "./manage/MetadataReviewQueue";

function reviewFilms(films: LibraryFilmSummary[], locale: string) {
  return films
    .filter((film) => film.primary_item.metadata.scrape_status === "needs_review")
    .sort((left, right) => (
      Number(Boolean(right.primary_item.metadata.scrape_error))
      - Number(Boolean(left.primary_item.metadata.scrape_error))
      || left.title.localeCompare(right.title, locale)
      || (left.year ?? 0) - (right.year ?? 0)
      || left.id.localeCompare(right.id)
    ));
}

export default function LibraryMetadataCare() {
  const t = useTranslations("LibraryCare");
  const locale = useLocale();
  const router = useRouter();
  const library = useLibrary();
  const films = useMemo(() => reviewFilms(library.data ?? [], locale), [library.data, locale]);
  const [activeFilmId, setActiveFilmId] = useState<string | null>(null);
  const [completed, setCompleted] = useState(false);
  const activeFilm = films.find((film) => film.id === activeFilmId) ?? films[0] ?? null;

  const handleConfirmed = async (filmId: string) => {
    const currentIndex = Math.max(0, films.findIndex((film) => film.id === filmId));
    const currentRemaining = films.filter((film) => film.id !== filmId);
    const refreshed = await library.mutate().catch(() => undefined);
    const remaining = refreshed
      ? reviewFilms(refreshed, locale).filter((film) => film.id !== filmId)
      : currentRemaining;
    setCompleted(remaining.length === 0);
    setActiveFilmId(remaining[currentIndex]?.id ?? remaining.at(-1)?.id ?? null);
    router.refresh();
  };

  if (library.error) {
    return <StateMessage state="error">{t("metadataLoadFailed")}</StateMessage>;
  }

  if (library.isLoading) {
    return <StateMessage state="loading">{t("metadataLoading")}</StateMessage>;
  }

  if (films.length === 0) {
    return (
      <div className="border-y border-line py-16 text-center">
        <CheckCircle2 className="mx-auto h-8 w-8 text-success" />
        <h2 className="mt-5 type-section-title text-ink">{completed ? t("metadataComplete") : t("metadataEmpty")}</h2>
        <p className="mx-auto mt-3 max-w-xl text-sm leading-6 text-ink-subtle">{t("metadataEmptyDesc")}</p>
        <Link href="/library" className="focus-ring mt-7 inline-flex min-h-10 items-center border border-line-strong px-4 type-label text-ink-muted hover:border-ink-disabled hover:text-ink">
          {t("backToFilms")}
        </Link>
      </div>
    );
  }

  return (
    <section className="grid min-w-0 gap-8 lg:grid-cols-[minmax(15rem,0.72fr)_minmax(0,1.5fr)]">
      <aside className="min-w-0 border-y border-line lg:border-r lg:border-y-0 lg:pr-8">
        <div className="flex items-center justify-between gap-4 border-b border-line py-4 lg:pt-0">
          <div>
            <p className="type-label text-ink-muted">{t("metadataTitle")}</p>
            <p className="mt-1 text-xs text-ink-disabled">{t("itemsCount", { count: films.length })}</p>
          </div>
          <Film className="h-4 w-4 text-ink-disabled" />
        </div>
        <ul className="scrollbar-minimal max-h-[34rem] overflow-y-auto">
          {films.map((film) => {
            const active = film.id === activeFilm?.id;
            return (
              <li key={film.id} className="border-b border-line">
                <button
                  type="button"
                  aria-current={active ? "true" : undefined}
                  onClick={() => setActiveFilmId(film.id)}
                  className={`focus-ring flex min-h-16 w-full items-center justify-between gap-4 px-3 py-3 text-left transition-colors ${active ? "bg-inverse text-inverse-ink" : "text-ink-muted hover:bg-surface-raised hover:text-ink"}`}
                >
                  <span className="min-w-0">
                    <span className="block truncate text-sm font-medium">{film.title}</span>
                    <span className={`mt-1 block text-[11px] ${active ? "text-inverse-ink/60" : film.primary_item.metadata.scrape_error ? "text-danger" : "text-ink-disabled"}`}>
                      {film.primary_item.metadata.scrape_error ? t("previousAttemptFailed") : film.year ?? t("unknownYear")}
                    </span>
                  </span>
                  <ChevronRight className="h-4 w-4 shrink-0" />
                </button>
              </li>
            );
          })}
        </ul>
      </aside>

      <div className="min-w-0">
        <div className="mb-5">
          <h2 className="type-section-title text-ink">{t("metadataReviewHeading")}</h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-ink-subtle">{t("metadataReviewDesc")}</p>
        </div>
        {activeFilm ? (
          <MetadataReviewInspector key={activeFilm.id} film={activeFilm} onConfirmed={handleConfirmed} />
        ) : (
          <InlineFeedback>{t("selectFilm")}</InlineFeedback>
        )}
      </div>
    </section>
  );
}
