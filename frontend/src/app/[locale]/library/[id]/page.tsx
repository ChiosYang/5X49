import { getTranslations } from "next-intl/server";
import { Play } from "lucide-react";
import { Link } from "@/i18n/routing";
import { API } from "@/lib/api";
import Providers from "@/components/Providers";
import { getLibraryMovie } from "@/lib/server-api";
import MovieAnalysisSection from "./MovieAnalysisSection";
import MovieBackdrop from "./MovieBackdrop";
import MovieHeroTitle from "./MovieHeroTitle";
import MoviePoster from "./MoviePoster";
import MovieRefreshButton from "./MovieRefreshButton";

interface MovieDetailPageProps {
  params: Promise<{
    id: string;
  }>;
}

export default async function MovieDetailPage({ params }: MovieDetailPageProps) {
  const t = await getTranslations("FilmDetail");
  const { id } = await params;
  const movie = await getLibraryMovie(id);

  if (!movie) {
    return (
      <div className="min-h-screen bg-black text-white flex flex-col items-center justify-center space-y-4">
        <h1 className="text-4xl font-serif font-bold">{t("notFound")}</h1>
        <Link href="/library" className="text-neutral-400 hover:text-white underline">
          {t("return")}
        </Link>
      </div>
    );
  }

  const artworkVersion = movie.metadata_updated_at ? `?v=${encodeURIComponent(movie.metadata_updated_at)}` : "";
  const backdropSrc = movie.backdrop_local ? `${API.mediaUrl(movie.backdrop_local)}${artworkVersion}` : null;
  const posterSrc = movie.poster_local ? `${API.mediaUrl(movie.poster_local)}${artworkVersion}` : null;

  return (
    <div className="min-h-screen bg-black text-white selection:bg-white selection:text-black">
      {/* Hero Section */}
      <div className="relative h-screen w-full overflow-hidden">
        <MovieBackdrop src={backdropSrc} title={movie.title} />
        <MovieHeroTitle title={movie.title} titleCn={movie.title_cn} />
      </div>

      {/* Info Grid */}
      <div className="border-t border-neutral-800 grid grid-cols-1 md:grid-cols-4 divide-y md:divide-y-0 md:divide-x divide-neutral-800 bg-black text-neutral-300">
         <div className="p-8 md:px-16 space-y-2">
             <span className="block text-xs font-bold uppercase tracking-widest text-neutral-500">{t("directedBy")}</span>
             <span className="block text-xl md:text-2xl font-bold text-white uppercase">{movie.director || "Unknown Director"}</span>
         </div>
         <div className="p-8 md:px-16 space-y-2">
             <span className="block text-xs font-bold uppercase tracking-widest text-neutral-500">{t("released")}</span>
             <span className="block text-xl md:text-2xl font-bold text-white font-serif italic">{movie.year}</span>
         </div>
         <div className="p-8 md:px-16 flex items-center justify-between group cursor-pointer hover:bg-white hover:text-black transition-colors">
             <span className="text-xl md:text-2xl font-bold uppercase">{t("watchNow")}</span>
             <Play className="w-6 h-6 fill-current" />
         </div>
         <Providers>
           <MovieRefreshButton movieId={id} />
         </Providers>
      </div>

      {/* Synopsis & Meta */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-12 p-8 md:p-16 border-b border-neutral-800">
         <div className="space-y-6">
             <div className="flex flex-col gap-4">
                 {['Facebook', 'Twitter', 'Instagram'].map(social => (
                     <a key={social} href="#" className="flex items-center gap-2 text-xs font-bold uppercase tracking-widest hover:opacity-50">
                         {social} <span className="text-[10px]">↗</span>
                     </a>
                 ))}
             </div>
             <div className="pt-12 space-y-3">
                 <span className="block text-xs font-bold uppercase tracking-widest text-neutral-500">{t("microGenre")}</span>
                 <span className="block text-lg font-serif italic text-white">{movie.micro_genre || t("pending")}</span>
                 {movie.micro_genre_definition && (
                   <p className="text-sm text-neutral-400 leading-relaxed">{movie.micro_genre_definition}</p>
                 )}
             </div>
         </div>
         <div className="lg:col-span-2">
             <p className="text-xl md:text-2xl lg:text-3xl font-bold leading-tight text-neutral-200 mb-12 md:mb-16">
                 {movie.overview || movie.plot || t("noDescription")}
             </p>

             {/* Featured Poster - Single Poster Style */}
             {posterSrc && (
               <MoviePoster src={posterSrc} title={movie.title} />
             )}
         </div>
      </div>

      {/* Genealogy Analysis Section */}
      <Providers>
        <MovieAnalysisSection movieId={id} initialMovie={movie} />
      </Providers>
    </div>
  );
}
