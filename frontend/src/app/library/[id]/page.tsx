"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { ArrowLeft, Play, Share2, Search, Menu } from "lucide-react";
import { API } from "@/lib/api";
import Genealogy from "../../components/Genealogy";

interface MovieDetail {
  id: string;
  title: string;
  title_cn?: string;
  year: number;
  backdrop_path?: string;
  backdrop_local?: string;
  poster_local?: string;
  overview: string;
  micro_genre: string;
  analysis_status: string;
  director?: string;
}

export default function MovieDetailPage() {
  const { id } = useParams();
  const router = useRouter();
  const [movie, setMovie] = useState<MovieDetail | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id) return;
    
    const fetchMovie = async () => {
      try {
        const res = await fetch(API.libraryMovie(id as string));
        if (!res.ok) throw new Error("Movie not found");
        const data = await res.json();
        setMovie(data);
      } catch (error) {
        console.error(error);
      } finally {
        setLoading(false);
      }
    };

    fetchMovie();
  }, [id]);

  if (loading) return (
    <div className="min-h-screen bg-black text-white flex items-center justify-center">
      <div className="animate-spin rounded-full h-8 w-8 border-t-2 border-b-2 border-white"></div>
    </div>
  );
  
  if (!movie) return (
    <div className="min-h-screen bg-black text-white flex flex-col items-center justify-center space-y-4">
      <h1 className="text-4xl font-serif font-bold">MOVIE NOT FOUND</h1>
      <button onClick={() => router.push('/library')} className="text-neutral-400 hover:text-white underline">
        Return to Library
      </button>
    </div>
  );

  return (
    <div className="min-h-screen bg-black text-white selection:bg-white selection:text-black">
      {/* Hero Section */}
      <div className="relative h-screen w-full overflow-hidden">
        {/* Backdrop */}
        <div className="absolute inset-0">
            {(movie.backdrop_local || movie.backdrop_path) && (
                <img 
                    src={movie.backdrop_local 
                      ? `http://localhost:8000${movie.backdrop_local}` 
                      : `https://image.tmdb.org/t/p/original${movie.backdrop_path}`}
                    alt={movie.title}
                    className="w-full h-full object-cover opacity-80"
                />
            )}
            <div className="absolute inset-0 bg-gradient-to-t from-black via-black/20 to-transparent" />
        </div>

        {/* Navigation Back */}
        <button 
          onClick={() => router.back()}
          className="absolute top-8 left-8 z-50 flex items-center gap-2 text-sm font-bold uppercase tracking-widest hover:opacity-70 transition-opacity mix-blend-exclusion text-white"
        >
          <ArrowLeft className="w-5 h-5" /> Back
        </button>

        {/* Title Block */}
        <div className="absolute bottom-0 left-0 p-8 md:p-16 w-full z-40">
           <motion.h1 
             initial={{ y: 100, opacity: 0 }}
             animate={{ y: 0, opacity: 1 }}
             transition={{ duration: 1, ease: "circOut" }}
             className="text-6xl md:text-8xl lg:text-9xl font-bold uppercase tracking-tighter leading-none mb-6"
           >
             {movie.title_cn || movie.title}
           </motion.h1>
           {movie.title_cn && (
             <motion.p 
               initial={{ opacity: 0 }}
               animate={{ opacity: 1 }}
               transition={{ delay: 0.5, duration: 1 }}
               className="text-2xl md:text-3xl font-serif italic text-neutral-400"
             >
               {movie.title}
             </motion.p>
           )}
        </div>
      </div>

      {/* Info Grid */}
      <div className="border-t border-neutral-800 grid grid-cols-1 md:grid-cols-3 divide-y md:divide-y-0 md:divide-x divide-neutral-800 bg-black text-neutral-300">
         <div className="p-8 space-y-2">
             <span className="block text-xs font-bold uppercase tracking-widest text-neutral-500">Directed By</span>
             <span className="block text-xl md:text-2xl font-bold text-white uppercase">{movie.director || "Unknown Director"}</span>
         </div>
         <div className="p-8 space-y-2">
             <span className="block text-xs font-bold uppercase tracking-widest text-neutral-500">Released</span>
             <span className="block text-xl md:text-2xl font-bold text-white font-serif italic">{movie.year}</span>
         </div>
         <div className="p-8 flex items-center justify-between group cursor-pointer hover:bg-white hover:text-black transition-colors">
             <span className="text-xl md:text-2xl font-bold uppercase">Watch Now</span>
             <Play className="w-6 h-6 fill-current" />
         </div>
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
             <div className="pt-12">
                 <span className="block text-xs font-bold uppercase tracking-widest text-neutral-500 mb-2">Micro-Genre</span>
                 <span className="text-lg font-serif italic text-white">{movie.micro_genre || "Genre Analysis Pending"}</span>
             </div>
         </div>
         <div className="lg:col-span-2">
             <p className="text-xl md:text-2xl lg:text-3xl font-bold leading-tight text-neutral-200">
                 {movie.overview}
             </p>
         </div>
      </div>

      {/* Genealogy Analysis Section */}
      <div className="min-h-screen">
          <Genealogy initialQuery={movie.title_cn || movie.title} />
      </div>

    </div>
  );
}
