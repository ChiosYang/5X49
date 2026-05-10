"use client";

import { useState } from "react";
import Image from "next/image";
import { useTranslations } from "next-intl";
import { motion } from "framer-motion";
import { Loader2 } from "lucide-react";
import { Link } from "@/i18n/routing";
import { API } from "@/lib/api";
import { useLibrary } from "@/hooks/useLibrary";

export default function LibraryPage() {
  const t = useTranslations("Library");
  const { data: movies = [], isLoading } = useLibrary();

  // Skip entrance animation when data comes from SWR cache (e.g. navigating back)
  const [skipAnimation] = useState(() => !isLoading && movies.length > 0);

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-black text-white">
        <Loader2 className="w-6 h-6 animate-spin" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-black text-white px-8 py-6 md:px-12 md:py-12 selection:bg-white selection:text-black">
      <div className="w-full space-y-20 pt-32">
        <header className="flex justify-between items-end border-b border-neutral-900 pb-8">
          <div>
            <h1 className="text-6xl md:text-9xl font-serif tracking-tighter leading-none">
              {t("title")}
            </h1>
          </div>
          <div className="flex items-center gap-6">
            <span className="text-neutral-500 text-xs font-bold uppercase tracking-widest hidden md:inline-block">
              {movies.length} FILMS
            </span>
          </div>
        </header>

        {movies.length === 0 ? (
          <div className="py-24 text-center space-y-4">
            <p className="text-neutral-500 font-serif italic text-xl">{t("empty")}</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5 gap-x-5 xl:gap-x-6 gap-y-12 xl:gap-y-14">
            {movies.map((movie, i) => (
              <Link key={movie.id} href={`/library/${movie.id}`}>
              <motion.div
                initial={skipAnimation ? { opacity: 1, y: 0 } : { opacity: 0, y: 30 }}
                animate={{ opacity: 1, y: 0 }}
                transition={skipAnimation ? { duration: 0 } : { delay: i * 0.05, duration: 0.5, ease: "circOut" }}
                className="group cursor-pointer space-y-4"
              >
                {/* Landscape Still */}
                <div className="relative aspect-video bg-neutral-900 overflow-hidden w-full">
                  {movie.backdrop_local ? (
                    <Image
                      src={API.mediaUrl(movie.backdrop_local)}
                      alt={movie.title}
                      fill
                      sizes="(min-width: 1536px) 20vw, (min-width: 1280px) 25vw, (min-width: 1024px) 33vw, (min-width: 640px) 50vw, 100vw"
                      className="object-cover transition-transform duration-700 ease-out group-hover:scale-105"
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
                      {movie.micro_genre || movie.genres?.join(' / ') || movie.director || ''}
                    </p>
                  </div>
                  <span className="font-serif text-xl italic text-neutral-400">
                    {movie.year}
                  </span>
                </div>
              </motion.div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
