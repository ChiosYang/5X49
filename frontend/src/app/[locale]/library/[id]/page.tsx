import { getTranslations } from "next-intl/server";
import { Link } from "@/i18n/routing";
import { getLibraryFilm } from "@/lib/server-api";
import MovieDetailView from "./MovieDetailView";

interface MovieDetailPageProps {
  params: Promise<{
    id: string;
  }>;
}

export default async function MovieDetailPage({ params }: MovieDetailPageProps) {
  const t = await getTranslations("FilmDetail");
  const { id } = await params;
  const film = await getLibraryFilm(id);

  if (!film) {
    return (
      <div className="min-h-screen bg-black text-white flex flex-col items-center justify-center space-y-4">
        <h1 className="text-4xl font-serif font-bold">{t("notFound")}</h1>
        <Link href="/library" className="text-neutral-400 hover:text-white underline">
          {t("return")}
        </Link>
      </div>
    );
  }

  return <MovieDetailView film={film} />;
}
