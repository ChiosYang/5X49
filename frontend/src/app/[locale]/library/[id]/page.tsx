import { getTranslations } from "next-intl/server";
import { isFilmResourceId } from "@/lib/resource-id";
import { getLibraryFilm } from "@/lib/server-api";
import MovieDetailReturn from "../MovieDetailReturn";
import MovieDetailView from "./MovieDetailView";

interface MovieDetailPageProps {
  params: Promise<{
    id: string;
  }>;
}

export default async function MovieDetailPage({ params }: MovieDetailPageProps) {
  const t = await getTranslations("FilmDetail");
  const { id } = await params;
  const film = isFilmResourceId(id) ? await getLibraryFilm(id) : null;

  if (!film) {
    return (
      <>
        <MovieDetailReturn behavior="library" label={t("return")} />
        <div className="min-h-screen bg-black text-white flex flex-col items-center justify-center space-y-4">
          <h1 className="text-4xl font-serif font-bold">{t("notFound")}</h1>
        </div>
      </>
    );
  }

  return (
    <>
      <MovieDetailReturn behavior="library" label={t("return")} />
      <MovieDetailView film={film} />
    </>
  );
}
