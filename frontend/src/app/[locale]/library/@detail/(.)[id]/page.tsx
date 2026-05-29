import { getTranslations } from "next-intl/server";
import { Link } from "@/i18n/routing";
import { getLibraryMovie } from "@/lib/server-api";
import MovieDetailView from "../../[id]/MovieDetailView";
import MovieDetailOverlay from "../../MovieDetailOverlay";

interface InterceptedMovieDetailPageProps {
  params: Promise<{
    id: string;
  }>;
}

export default async function InterceptedMovieDetailPage({ params }: InterceptedMovieDetailPageProps) {
  const t = await getTranslations("FilmDetail");
  const { id } = await params;
  const movie = await getLibraryMovie(id);

  if (!movie) {
    return (
      <MovieDetailOverlay>
        <div className="min-h-screen bg-black text-white flex flex-col items-center justify-center space-y-4">
          <h1 className="text-4xl font-serif font-bold">{t("notFound")}</h1>
          <Link href="/library" className="text-neutral-400 hover:text-white underline">
            {t("return")}
          </Link>
        </div>
      </MovieDetailOverlay>
    );
  }

  return (
    <MovieDetailOverlay>
      <MovieDetailView movie={movie} />
    </MovieDetailOverlay>
  );
}
