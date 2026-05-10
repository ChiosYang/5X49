import Image from "next/image";
import { Link } from "@/i18n/routing";
import { API } from "@/lib/api";
import type { LibraryMovie } from "@/types/movie";

interface LibraryMovieCardProps {
  movie: LibraryMovie;
  priority?: boolean;
}

export default function LibraryMovieCard({ movie, priority = false }: LibraryMovieCardProps) {
  return (
    <Link href={`/library/${movie.id}`}>
      <div className="group cursor-pointer space-y-4">
        {/* Landscape Still */}
        <div className="relative aspect-video bg-neutral-900 overflow-hidden w-full">
          {movie.backdrop_local ? (
            <Image
              src={API.mediaUrl(movie.backdrop_local)}
              alt={movie.title}
              fill
              priority={priority}
              sizes="(min-width: 1536px) 20vw, (min-width: 1280px) 25vw, (min-width: 1024px) 33vw, (min-width: 640px) 50vw, 100vw"
              className="object-cover transition-transform duration-150 ease-out group-hover:scale-105"
            />
          ) : (
            <div className="w-full h-full flex items-center justify-center border border-neutral-800">
              <span className="font-serif text-4xl text-neutral-800">?</span>
            </div>
          )}
          {/* Hover Overlay */}
          <div className="absolute inset-0 bg-black/0 group-hover:bg-black/10 transition-colors" />
        </div>

        {/* Title & Info */}
        <div className="flex justify-between items-start">
          <div className="space-y-1">
            <h3 className="text-xl md:text-2xl font-bold uppercase leading-none tracking-tight">
              {movie.title_cn || movie.title}
            </h3>
            <p className="text-xs font-bold uppercase tracking-widest text-neutral-500">
              {movie.micro_genre || movie.genres?.join(" / ") || movie.director || ""}
            </p>
          </div>
          <span className="font-serif text-xl italic text-neutral-400">
            {movie.year}
          </span>
        </div>
      </div>
    </Link>
  );
}
