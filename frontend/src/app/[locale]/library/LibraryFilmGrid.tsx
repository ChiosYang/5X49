"use client";

import { useRef, useState } from "react";
import { useTranslations } from "next-intl";
import type { FilmProfileState, LibraryFilmSummary } from "@/types/movie";
import type { LibraryFilterKey } from "@/lib/library-care";
import { matchesLibraryFilter } from "@/lib/library-interactions";
import LibraryMovieCard from "./LibraryMovieCard";

export default function LibraryFilmGrid({ films, filter }: { films: LibraryFilmSummary[]; filter: LibraryFilterKey }) {
  const t = useTranslations("Library");
  const [overrides, setOverrides] = useState<Record<string, { baseline: string | null | undefined; state: FilmProfileState }>>({});
  const [notice, setNotice] = useState("");
  const noticeRef = useRef<HTMLParagraphElement>(null);
  const items = films.map((film) => {
    const override = overrides[film.id];
    return override && override.baseline === film.profile_state.updated_at ? { ...film, profile_state: override.state } : film;
  }).filter((film) => matchesLibraryFilter(film.profile_state, filter));
  return <>
    <p ref={noticeRef} tabIndex={-1} role="status" className="focus-ring mt-5 min-h-6 text-sm text-ink-muted">{notice}</p>
    <div className="mt-12 grid grid-cols-1 gap-x-5 gap-y-12 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 xl:gap-x-6 xl:gap-y-14 2xl:grid-cols-5">
      {items.map((movie, index) => <LibraryMovieCard key={movie.id} movie={movie} priority={index === 0} onProfileSaved={(state) => {
        const original = films.find((film) => film.id === movie.id)!;
        setOverrides((current) => ({ ...current, [movie.id]: { baseline: original.profile_state.updated_at, state } }));
        if (!matchesLibraryFilter(state, filter)) {
          setNotice(t("removedFromFilter", { title: movie.title }));
          requestAnimationFrame(() => noticeRef.current?.focus({ preventScroll: true }));
        }
      }} />)}
    </div>
  </>;
}
