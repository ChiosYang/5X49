"use client";

import { useState, useEffect } from "react";
import { Loader2 } from "lucide-react";
import { motion } from "framer-motion";
import { useTranslations } from "next-intl";
import { API } from "@/lib/api";

interface FilmNode {
  title: string;
  year: number;
  type?: string;
  reason: string;
}

interface GenealogyData {
  thought_chain: string;
  micro_genre: string;
  influence_impact: string;
  ancestors: FilmNode[];
  descendants: FilmNode[];
  tmdb_metadata: {
    title: string;
    year: number;
    overview: string;
    genres: string[];
    keywords: string[];
  };
}

interface GenealogyProps {
  initialQuery?: string;
  hideSearch?: boolean;
}

export default function Genealogy({ initialQuery = "", hideSearch = false }: GenealogyProps) {
  const t = useTranslations("Genealogy");
  const [query, setQuery] = useState(initialQuery);
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<GenealogyData | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    // if (initialQuery) {
    //   handleSearch(new Event('submit') as any, initialQuery);
    // }
  }, [initialQuery]);

  const handleSearch = async (e: React.FormEvent, overrideQuery?: string) => {
    if (e) e.preventDefault();
    const q = overrideQuery || query;
    if (!q.trim()) return;

    setLoading(true);
    setError("");
    setData(null);

    try {
      const res = await fetch(API.analyze(q));
      if (!res.ok) throw new Error("Film not found or analysis failed");
      const jsonData = await res.json();
      setData(jsonData);
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("An unknown error occurred");
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-black text-white p-6 md:p-12 selection:bg-white selection:text-black">
      <div className="max-w-6xl mx-auto space-y-20">
        {/* Header */}
        <header className="space-y-6 pt-12 border-b border-neutral-800 pb-12">
          <h1 className="text-6xl md:text-8xl tracking-tighter font-serif">
            {t("title")}
          </h1>
          <p className="text-neutral-500 text-meta tracking-widest text-sm">
            {t("subtitle")}
          </p>
        </header>

        {/* Search Input (Minimalist) */}
        {!hideSearch && (
          <form onSubmit={handleSearch} className="relative max-w-2xl">
            <input
              type="text"
              placeholder="ENTER FILM TITLE..."
              className="w-full bg-transparent border-b border-neutral-700 py-4 text-2xl md:text-4xl placeholder:text-neutral-800 focus:outline-none focus:border-white transition-colors uppercase font-bold tracking-tight"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            <button 
              type="submit" 
              disabled={loading}
              className="absolute right-0 top-1/2 -translate-y-1/2 text-sm uppercase tracking-widest hover:text-neutral-400 disabled:opacity-50"
            >
              {loading ? <Loader2 className="w-5 h-5 animate-spin" /> : t("analyzing")}
            </button>
          </form>
        )}

        {/* Error */}
        {error && (
          <div className="border border-red-900 text-red-500 p-4 text-xs font-mono uppercase">
            Error: {error}
          </div>
        )}

        {/* Results */}
        {data && (
          <motion.div 
            initial={{ opacity: 0, y: 40 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, ease: "circOut" }}
            className="space-y-24 pb-24"
          >
            {/* Hero Section */}
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-12 items-start">
               <div className="lg:col-span-8 space-y-8">
                 <h2 className="text-7xl md:text-9xl font-bold uppercase leading-[0.8] tracking-tighter break-words">
                   {data.tmdb_metadata.title}
                 </h2>
                 <div className="space-y-4">
                    <p className="text-2xl font-serif italic text-neutral-400">&quot;{data.micro_genre}&quot;</p>
                    <p className="max-w-xl text-lg text-neutral-300 leading-relaxed font-light">
                      {data.influence_impact}
                    </p>
                 </div>
               </div>

               <div className="lg:col-span-4 space-y-6 border-t border-neutral-800 pt-6 lg:pt-0 lg:border-t-0">
                 <div className="flex justify-between border-b border-neutral-900 pb-2">
                   <span className="text-meta text-neutral-500">YEAR</span>
                   <span className="text-lg font-bold">{data.tmdb_metadata.year}</span>
                 </div>
                 <div className="flex flex-col gap-2 border-b border-neutral-900 pb-4">
                   <span className="text-meta text-neutral-500">GENRES</span>
                   <div className="flex flex-wrap gap-2">
                     {data.tmdb_metadata.genres.map(g => (
                       <span key={g} className="text-sm uppercase tracking-wide border border-neutral-800 px-2 py-1">
                         {g}
                       </span>
                     ))}
                   </div>
                 </div>
               </div>
            </div>

            {/* Timeline Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-x-12 gap-y-16 border-t border-neutral-800 pt-16">
              
              {/* Ancestors Column */}
              <div className="space-y-12">
                <h3 className="text-meta text-neutral-500 border-b border-neutral-900 pb-4 mb-8">
                  {t("ancestors")}
                </h3>
                {data.ancestors.map((film, i) => (
                  <div key={i} className="group space-y-3">
                    <div className="flex items-baseline justify-between">
                       <h4 className="text-3xl font-bold uppercase group-hover:underline decoration-1 underline-offset-4">
                         {film.title}
                       </h4>
                       <span className="font-mono text-neutral-500 text-sm">{film.year}</span>
                    </div>
                    <div className="text-xs text-neutral-400 uppercase tracking-widest mb-1">
                      [{film.type}]
                    </div>
                    <p className="text-neutral-400 font-serif italic leading-relaxed">
                      {film.reason}
                    </p>
                  </div>
                ))}
              </div>

              {/* Descendants Column */}
              <div className="space-y-12">
                <h3 className="text-meta text-neutral-500 border-b border-neutral-900 pb-4 mb-8">
                  {t("descendants")}
                </h3>
                {data.descendants.map((film, i) => (
                  <div key={i} className="group space-y-3">
                     <div className="flex items-baseline justify-between">
                       <h4 className="text-3xl font-bold uppercase group-hover:underline decoration-1 underline-offset-4">
                         {film.title}
                       </h4>
                       <span className="font-mono text-neutral-500 text-sm">{film.year}</span>
                    </div>
                    <div className="text-xs text-neutral-400 uppercase tracking-widest mb-1">
                      [{film.type}]
                    </div>
                    <p className="text-neutral-400 font-serif italic leading-relaxed">
                      {film.reason}
                    </p>
                  </div>
                ))}
              </div>

            </div>
            
            {/* Thought Chain Minimal */}
            <div className="pt-24 opacity-50 hover:opacity-100 transition-opacity">
               <details className="cursor-pointer">
                 <summary className="text-meta text-neutral-600 list-none text-center">
                   AI ANALYSIS LOG +
                 </summary>
                 <div className="mt-8 font-mono text-xs text-neutral-500 max-w-3xl mx-auto border-l border-neutral-800 pl-4">
                   {data.thought_chain}
                 </div>
               </details>
            </div>

          </motion.div>
        )}
      </div>
    </div>
  );
}
