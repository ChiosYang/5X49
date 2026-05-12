import Image from "next/image";
import { MessageSquare, Plus, Play, Star, VolumeX } from "lucide-react";
import { Link } from "@/i18n/routing";
import { API } from "@/lib/api";
import type { LibraryMovie } from "@/types/movie";

interface LibraryMovieCardProps {
  movie: LibraryMovie;
  priority?: boolean;
}

export default function LibraryMovieCard({ movie, priority = false }: LibraryMovieCardProps) {
  const showBackdrop = Boolean(movie.backdrop_local);
  const title = movie.title_cn || movie.title;
  const description = movie.overview || movie.plot || movie.micro_genre || "";
  const tags = [
    movie.micro_genre,
    ...(movie.genres || []),
    movie.director ? `Dir. ${movie.director}` : undefined,
  ]
    .filter(Boolean)
    .slice(0, 3);
  const extraGenreCount = Math.max((movie.genres?.length || 0) - 1, 0);

  return (
    <Link href={`/library/${movie.id}`} className="block">
      <div className="group relative z-0 cursor-pointer space-y-4 hover:z-30">
        {/* Landscape Still */}
        <div className="relative aspect-video w-full bg-neutral-900">
          <div className="relative h-full w-full overflow-hidden rounded-md">
            {showBackdrop ? (
              <Image
                src={API.mediaUrl(movie.backdrop_local!)}
                alt={movie.title}
                fill
                priority={priority}
                sizes="(min-width: 1536px) 20vw, (min-width: 1280px) 25vw, (min-width: 1024px) 33vw, (min-width: 640px) 50vw, 100vw"
                className="object-cover transition-transform delay-0 duration-200 ease-out group-hover:scale-[1.05] group-hover:delay-500"
              />
            ) : (
              <div className="flex h-full w-full items-center justify-center border border-neutral-800 transition-transform delay-0 duration-200 ease-out group-hover:scale-[1.05] group-hover:delay-500">
                <span className="font-serif text-4xl text-neutral-800">?</span>
              </div>
            )}
            {/* Hover Overlay */}
            <div className="absolute inset-0 bg-black/0 transition-colors delay-0 duration-200 group-hover:bg-black/35 group-hover:delay-500" />
            <div className="invisible absolute inset-x-0 bottom-0 flex translate-y-1 flex-col gap-1 bg-gradient-to-t from-black/80 via-black/35 to-transparent px-5 pb-4 pt-12 opacity-0 transition-[opacity,transform] delay-0 duration-200 group-hover:visible group-hover:translate-y-0 group-hover:opacity-100 group-hover:delay-500">
              <h3 className="line-clamp-1 text-2xl font-black uppercase leading-none text-white">
                {title}
              </h3>
              <p className="line-clamp-1 text-xs font-bold uppercase tracking-wide text-white">
                {movie.director || movie.title} {movie.year}
              </p>
            </div>
            <span className="invisible absolute right-4 top-4 text-white/90 opacity-0 transition-opacity delay-0 duration-200 group-hover:visible group-hover:opacity-100 group-hover:delay-500">
              <VolumeX className="h-5 w-5 fill-white/30" />
            </span>
          </div>

          <div className="invisible absolute left-0 right-0 top-full z-20 origin-top translate-y-1 scale-95 rounded-b-md border border-white/10 border-t-0 bg-neutral-950 p-5 text-white opacity-0 shadow-2xl shadow-black/70 transition-[opacity,transform] delay-0 duration-200 ease-out group-hover:visible group-hover:translate-y-0 group-hover:scale-100 group-hover:opacity-100 group-hover:delay-500">
            <div className="space-y-4">
              <div className="flex items-center gap-3">
                <span
                  className="inline-flex h-10 items-center gap-2 rounded-full bg-white px-4 text-sm font-black uppercase tracking-wide text-black transition-colors group-hover:bg-neutral-200"
                  aria-label="Watch"
                >
                  <Play className="h-4 w-4 fill-current" />
                  Watch
                </span>
                <span
                  className="flex h-8 w-8 items-center justify-center rounded-full border border-white/55 text-white transition-colors group-hover:border-white"
                  aria-label="Add to list"
                >
                  <Plus className="h-5 w-5" />
                </span>
                <span
                  className="flex h-8 w-8 items-center justify-center rounded-full border border-white/55 text-white transition-colors group-hover:border-white"
                  aria-label="Favorite"
                >
                  <Star className="h-4 w-4" />
                </span>
              </div>

              <p className="overflow-hidden text-[15px] leading-snug text-neutral-300 [display:-webkit-box] [-webkit-box-orient:vertical] [-webkit-line-clamp:4]">
                {description || `${title} (${movie.year})`}
              </p>

              <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-neutral-400">
                <span className="rounded-sm bg-neutral-700 px-1 text-[10px] font-black leading-4 text-neutral-100">
                  HD
                </span>
                <span className="flex items-center gap-1">
                  <span className="h-3 w-3 rounded-full border-2 border-neutral-500 bg-neutral-800" />
                  {movie.year}
                </span>
                {movie.genres?.[0] && (
                  <span className="flex items-center gap-1">
                    <MessageSquare className="h-3.5 w-3.5 fill-neutral-500 text-neutral-500" />
                    {movie.genres[0]}
                    {extraGenreCount > 0 && ` +${extraGenreCount}`}
                  </span>
                )}
              </div>

              {tags.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {tags.map((tag) => (
                    <span
                      key={tag}
                      className="max-w-full truncate rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-[10px] font-black uppercase tracking-widest text-neutral-300"
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Title & Info */}
        <div className="flex justify-between items-start">
          <div className="space-y-1">
            <h3 className="text-xl md:text-2xl font-bold uppercase leading-none tracking-tight">
              {title}
            </h3>
          </div>
          <span className="font-serif text-xl italic text-neutral-400">
            {movie.year}
          </span>
        </div>
      </div>
    </Link>
  );
}
