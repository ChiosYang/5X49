"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { motion } from "framer-motion";
import { Loader2 } from "lucide-react";
import { Link } from "@/i18n/routing";
import { API } from "@/lib/api";

interface Movie {
  id: string;
  title: string;
  title_cn?: string;
  year: number;
  backdrop_path?: string;
  backdrop_local?: string;
  poster_local?: string;
  micro_genre?: string;
  genres?: string[];
  director?: string;
}

export default function LibraryPage() {
  const t = useTranslations("Library");
  const [movies, setMovies] = useState<Movie[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchLibrary = async () => {
    try {
      const res = await fetch(API.library());
      const data = await res.json();
      setMovies(data);
    } catch (error) {
      console.error("Failed to fetch library", error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchLibrary();
  }, []);



  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-black text-white">
        <Loader2 className="w-6 h-6 animate-spin" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-black text-white p-6 md:p-12 selection:bg-white selection:text-black">
      <div className="max-w-[1600px] mx-auto space-y-20 pt-32">
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
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-x-8 gap-y-16">
            {movies.map((movie, i) => (
              <Link key={movie.id} href={`/library/${movie.id}`}>
              <motion.div
                initial={{ opacity: 0, y: 30 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.05, duration: 0.5, ease: "circOut" }}
                className="group cursor-pointer space-y-4"
              >
                {/* Landscape Still */}
                <div className="relative aspect-video bg-neutral-900 overflow-hidden w-full">
                  {(movie.backdrop_local || movie.backdrop_path) ? (
                    <img
                      src={movie.backdrop_local 
                        ? API.mediaUrl(movie.backdrop_local) 
                        : `https://image.tmdb.org/t/p/w1280${movie.backdrop_path}`}
                      alt={movie.title}
                      className="w-full h-full object-cover transition-transform duration-700 ease-out group-hover:scale-105"
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
                    <h3 className="text-2xl md:text-3xl font-bold uppercase leading-none tracking-tight">
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
