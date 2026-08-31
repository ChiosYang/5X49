import { getTranslations } from "next-intl/server";
import { isFilmResourceId } from "@/lib/resource-id";
import { getLibraryFilm } from "@/lib/server-api";
import MovieDetailView from "../../[id]/MovieDetailView";
import MovieDetailOverlay from "../../MovieDetailOverlay";

interface InterceptedMovieDetailPageProps {
  params: Promise<{
    id: string;
  }>;
}

export default async function InterceptedMovieDetailPage({ params }: InterceptedMovieDetailPageProps) {
  const { id } = await params;
  if (!isFilmResourceId(id)) return null;

  const t = await getTranslations("FilmDetail");
  const film = await getLibraryFilm(id);

  if (!film) {
    return (
      <MovieDetailOverlay dialogLabel={t("dialogLabel")} returnLabel={t("return")}>
        <div className="min-h-screen bg-black text-white flex flex-col items-center justify-center space-y-4">
          <h1 className="text-4xl font-serif font-bold">{t("notFound")}</h1>
        </div>
      </MovieDetailOverlay>
    );
  }

  return (
    <MovieDetailOverlay dialogLabel={t("dialogLabel")} returnLabel={t("return")}>
      <MovieDetailView film={film} />
    </MovieDetailOverlay>
  );
}
