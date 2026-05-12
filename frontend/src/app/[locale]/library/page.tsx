import { getTranslations } from "next-intl/server";
import { getLibrary } from "@/lib/server-api";
import LibraryEventsRefresher from "./LibraryEventsRefresher";
import LibraryMovieCard from "./LibraryMovieCard";
import LibraryRefreshButton from "./LibraryRefreshButton";

export default async function LibraryPage() {
  const t = await getTranslations("Library");
  const movies = await getLibrary();
  const visibleMovies = movies.filter(
    (movie) => !["missing", "ignored"].includes(movie.library_status || "")
  );

  return (
    <div className="min-h-screen bg-black text-white px-8 py-6 md:px-12 md:py-12 selection:bg-white selection:text-black">
      <LibraryEventsRefresher />
      <div className="w-full space-y-20 pt-32">
        <header className="flex justify-between items-end border-b border-neutral-900 pb-8">
          <div>
            <h1 className="text-6xl md:text-9xl font-serif tracking-tighter leading-none">
              {t("title")}
            </h1>
          </div>
          <div className="flex items-center gap-6">
            <span className="text-neutral-500 text-xs font-bold uppercase tracking-widest hidden md:inline-block">
              {visibleMovies.length} FILMS
            </span>
            <LibraryRefreshButton />
          </div>
        </header>

        {visibleMovies.length === 0 ? (
          <div className="py-24 text-center space-y-4">
            <p className="text-neutral-500 font-serif italic text-xl">{t("empty")}</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5 gap-x-5 xl:gap-x-6 gap-y-12 xl:gap-y-14">
            {visibleMovies.map((movie, i) => (
              <LibraryMovieCard key={movie.id} movie={movie} priority={i === 0} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
