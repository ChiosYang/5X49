import { motion } from 'framer-motion';
import FilmCard from './FilmCard';

interface FilmReference {
  title: string;
  year: number;
  type: string;
  reason: string;
}

interface AnalysisData {
  thought_chain: string;
  micro_genre: string;
  influence_impact: string;
  ancestors: FilmReference[];
  descendants: FilmReference[];
  tmdb_metadata?: any;
}

interface GenealogySectionProps {
  analysisData: AnalysisData | null;
  analysisStatus: string;
  movieTitle: string;
  movieYear: number;
  onTriggerAnalysis?: () => void;
  analyzing?: boolean;
}

export default function GenealogySection({ 
  analysisData, 
  analysisStatus, 
  movieTitle, 
  movieYear,
  onTriggerAnalysis,
  analyzing = false
}: GenealogySectionProps) {
  // Pending state with trigger button
  if (analysisStatus === 'pending' && onTriggerAnalysis) {
    return (
      <div className="border-b border-neutral-800 p-8 md:p-16">
        <h2 className="text-2xl md:text-3xl font-bold uppercase tracking-tight mb-8">Film Genealogy</h2>
        <div className="flex flex-col items-center justify-center py-16 space-y-6">
          <p className="text-sm text-neutral-500 uppercase tracking-widest text-center">
            Genealogy analysis not yet performed
          </p>
          <button
            onClick={onTriggerAnalysis}
            disabled={analyzing}
            className="group relative px-8 py-4 border-2 border-white bg-black text-white font-bold uppercase tracking-widest text-sm hover:bg-white hover:text-black transition-all duration-300 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {analyzing ? (
              <>
                <span className="flex items-center gap-3">
                  <div className="animate-spin h-4 w-4 border-2 border-neutral-700 border-t-white rounded-full"></div>
                  Analyzing...
                </span>
              </>
            ) : (
              'Analyze Film Genealogy'
            )}
          </button>
          <p className="text-xs text-neutral-600 text-center max-w-md">
            This will send the film to our AI for genealogical analysis. The process typically takes 90-120 seconds.
          </p>
        </div>
      </div>
    );
  }
  // Loading state
  if (analysisStatus === 'pending' || analysisStatus === 'processing') {
    return (
      <div className="border-b border-neutral-800 p-8 md:p-16">
        <h2 className="text-2xl md:text-3xl font-bold uppercase tracking-tight mb-8">Film Genealogy</h2>
        <div className="flex items-center justify-center py-16">
          <div className="text-center space-y-4">
            <div className="animate-spin h-8 w-8 border-2 border-neutral-700 border-t-white rounded-full mx-auto"></div>
            <p className="text-sm text-neutral-500 uppercase tracking-widest">Analyzing film genealogy...</p>
          </div>
        </div>
      </div>
    );
  }

  // Failed state
  if (analysisStatus === 'failed' || !analysisData) {
    return (
      <div className="border-b border-neutral-800 p-8 md:p-16">
        <h2 className="text-2xl md:text-3xl font-bold uppercase tracking-tight mb-8">Film Genealogy</h2>
        <div className="text-center py-16">
          <p className="text-neutral-500 text-sm uppercase tracking-widest">Analysis unavailable</p>
        </div>
      </div>
    );
  }

  const { ancestors = [], descendants = [], influence_impact } = analysisData;

  return (
    <div className="border-b border-neutral-800 p-8 md:p-16">
      {/* Section Title */}
      <motion.h2 
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        className="text-2xl md:text-3xl font-bold uppercase tracking-tight mb-4"
      >
        Film Genealogy
      </motion.h2>

      {/* Influence Impact Quote */}
      {influence_impact && (
        <motion.div 
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.2 }}
          className="mb-12 pl-6 border-l-2 border-neutral-700"
        >
          <p className="text-lg md:text-xl font-serif italic text-neutral-300 leading-relaxed">
            {influence_impact}
          </p>
        </motion.div>
      )}

      {/* Timeline */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 relative">
        {/* Ancestors */}
        <div className="space-y-6">
          <h3 className="text-xs font-bold uppercase tracking-widest text-neutral-500 mb-6">Ancestors</h3>
          {ancestors.length > 0 ? (
            ancestors.map((film, index) => (
              <FilmCard
                key={`ancestor-${index}`}
                title={film.title}
                year={film.year}
                type={film.type}
                reason={film.reason}
                variant="ancestor"
              />
            ))
          ) : (
            <div className="border border-dashed border-neutral-800 p-6 text-center">
              <p className="text-xs text-neutral-600 uppercase tracking-widest">No ancestors identified</p>
            </div>
          )}
        </div>

        {/* Current Film (Center) */}
        <div className="flex flex-col justify-center items-center">
          <motion.div
            initial={{ scale: 0.9, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{ delay: 0.3 }}
            className="border-2 border-white bg-black p-8 text-center w-full"
          >
            <span className="block text-[10px] font-bold uppercase tracking-widest text-neutral-500 mb-3">Current Film</span>
            <h3 className="text-2xl font-bold uppercase tracking-tight mb-2">{movieTitle}</h3>
            <span className="text-lg text-neutral-500 font-mono">{movieYear}</span>
          </motion.div>

          {/* Timeline Arrows (Desktop only) */}
          <div className="hidden lg:flex absolute top-1/2 -translate-y-1/2 w-full justify-between px-4 pointer-events-none">
            <span className="text-4xl text-neutral-700">←</span>
            <span className="text-4xl text-neutral-700">→</span>
          </div>
        </div>

        {/* Descendants */}
        <div className="space-y-6">
          <h3 className="text-xs font-bold uppercase tracking-widest text-neutral-500 mb-6">Descendants</h3>
          {descendants.length > 0 ? (
            descendants.map((film, index) => (
              <FilmCard
                key={`descendant-${index}`}
                title={film.title}
                year={film.year}
                type={film.type}
                reason={film.reason}
                variant="descendant"
              />
            ))
          ) : (
            <div className="border border-dashed border-neutral-800 p-6 text-center">
              <p className="text-xs text-neutral-600 uppercase tracking-widest">No descendants identified</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
