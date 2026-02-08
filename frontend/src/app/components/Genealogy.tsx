"use client";

import { useState } from "react";
import { Search, Loader2 } from "lucide-react";
import { motion } from "framer-motion";

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

export default function Genealogy() {
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<GenealogyData | null>(null);
  const [error, setError] = useState("");

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;

    setLoading(true);
    setError("");
    setData(null);

    try {
      const res = await fetch(`http://localhost:8000/analyze/${encodeURIComponent(query)}`);
      if (!res.ok) throw new Error("Film not found or analysis failed");
      const jsonData = await res.json();
      setData(jsonData);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-neutral-950 text-neutral-200 p-8 font-sans selection:bg-rose-900 selection:text-white">
      <div className="max-w-4xl mx-auto space-y-12">
        {/* Header */}
        <header className="text-center space-y-4 pt-10">
          <h1 className="text-5xl font-bold tracking-tight bg-gradient-to-r from-rose-400 to-orange-300 bg-clip-text text-transparent">
            Film Genealogy
          </h1>
          <p className="text-neutral-400 text-lg">
            Discover the ancestry and legacy of cinema.
          </p>
        </header>

        {/* Search */}
        <form onSubmit={handleSearch} className="relative max-w-xl mx-auto">
          <input
            type="text"
            placeholder="Enter a film title (e.g., 2001: A Space Odyssey)..."
            className="w-full bg-neutral-900 border border-neutral-800 rounded-full px-6 py-4 pl-14 text-lg focus:outline-none focus:ring-2 focus:ring-rose-500/50 transition-all placeholder:text-neutral-600"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <Search className="absolute left-5 top-1/2 -translate-y-1/2 text-neutral-500 w-5 h-5" />
          <button 
            type="submit" 
            disabled={loading}
            className="absolute right-3 top-1/2 -translate-y-1/2 bg-rose-600 hover:bg-rose-500 text-white px-4 py-2 rounded-full text-sm font-medium transition-colors disabled:opacity-50"
          >
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : "Analyze"}
          </button>
        </form>

        {/* Error */}
        {error && (
          <div className="text-center text-rose-400 bg-rose-950/30 py-3 rounded-lg border border-rose-900/50">
            {error}
          </div>
        )}

        {/* Results */}
        {data && (
          <motion.div 
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="space-y-16"
          >
            {/* Main Film Info */}
            <div className="bg-neutral-900/50 rounded-2xl p-8 border border-neutral-800 text-center relative overflow-hidden">
               <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-transparent via-rose-500 to-transparent opacity-50"></div>
               <h2 className="text-4xl font-serif text-white mb-2">{data.tmdb_metadata.title}</h2>
               <div className="text-rose-400 font-mono text-sm mb-6">{data.tmdb_metadata.year}</div>
               
               <div className="flex flex-wrap justify-center gap-2 mb-6">
                 {data.tmdb_metadata.genres.map(g => (
                   <span key={g} className="px-3 py-1 bg-neutral-800 rounded-full text-xs text-neutral-300 font-medium tracking-wide uppercase">
                     {g}
                   </span>
                 ))}
               </div>

               <div className="max-w-2xl mx-auto space-y-6 text-neutral-300 leading-relaxed">
                  <div>
                    <span className="block text-xs font-bold text-rose-500/80 uppercase tracking-widest mb-1">Micro-Genre</span>
                    <p className="font-serif text-xl italic text-white">"{data.micro_genre}"</p>
                  </div>
                  
                  <div>
                    <span className="block text-xs font-bold text-rose-500/80 uppercase tracking-widest mb-1">Impact Analysis</span>
                    <p className="text-neutral-400">{data.influence_impact}</p>
                  </div>
               </div>
            </div>

            {/* Timeline */}
            <div className="relative border-l-2 border-neutral-800 ml-6 md:ml-auto md:max-w-2xl space-y-12 pl-8 pb-4">
              
              {/* Ancestors */}
              <div className="space-y-8">
                <h3 className="text-sm font-bold text-neutral-500 uppercase tracking-widest -ml-10 mb-6 flex items-center gap-4">
                  <span className="w-2 h-2 rounded-full bg-neutral-700"></span>
                  Ancestors
                </h3>
                {data.ancestors.map((film, i) => (
                  <div key={i} className="relative">
                    <div className="absolute -left-[41px] top-1.5 w-4 h-4 rounded-full bg-neutral-900 border-2 border-neutral-700"></div>
                    <div className="group hover:bg-neutral-900/40 p-4 -m-4 rounded-xl transition-colors">
                      <div className="flex items-baseline justify-between mb-1">
                        <h4 className="text-xl font-bold text-neutral-200 group-hover:text-white transition-colors">
                          {film.title} <span className="text-neutral-500 text-sm font-normal ml-2">{film.year}</span>
                        </h4>
                        <span className="text-xs bg-neutral-800 text-neutral-400 px-2 py-0.5 rounded">{film.type}</span>
                      </div>
                      <p className="text-neutral-400 text-sm">{film.reason}</p>
                    </div>
                  </div>
                ))}
              </div>

              {/* Core Node Marker */}
              <div className="relative py-8">
                 <div className="absolute -left-[45px] top-1/2 -translate-y-1/2 w-6 h-6 rounded-full bg-rose-500 border-4 border-neutral-950 shadow-[0_0_20px_rgba(225,29,72,0.5)]"></div>
              </div>

              {/* Descendants */}
              <div className="space-y-8">
                <h3 className="text-sm font-bold text-neutral-500 uppercase tracking-widest -ml-10 mb-6 flex items-center gap-4">
                  <span className="w-2 h-2 rounded-full bg-neutral-700"></span>
                  Descendants
                </h3>
                {data.descendants.map((film, i) => (
                  <div key={i} className="relative">
                    <div className="absolute -left-[41px] top-1.5 w-4 h-4 rounded-full bg-neutral-900 border-2 border-neutral-700"></div>
                     <div className="group hover:bg-neutral-900/40 p-4 -m-4 rounded-xl transition-colors">
                      <div className="flex items-baseline justify-between mb-1">
                        <h4 className="text-xl font-bold text-neutral-200 group-hover:text-white transition-colors">
                          {film.title} <span className="text-neutral-500 text-sm font-normal ml-2">{film.year}</span>
                        </h4>
                        <span className="text-xs bg-neutral-800 text-neutral-400 px-2 py-0.5 rounded">{film.type}</span>
                      </div>
                      <p className="text-neutral-400 text-sm">{film.reason}</p>
                    </div>
                  </div>
                ))}
              </div>

            </div>
            
            {/* Thought Chain Toggle (Optional) */}
            <div className="border-t border-neutral-900 pt-8 text-center">
               <details className="text-sm text-neutral-500 cursor-pointer group">
                 <summary className="list-none hover:text-rose-400 transition-colors">Show AI Thought Process</summary>
                 <div className="mt-4 p-4 bg-neutral-900/30 rounded-lg text-left font-mono text-xs leading-relaxed max-w-2xl mx-auto">
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
