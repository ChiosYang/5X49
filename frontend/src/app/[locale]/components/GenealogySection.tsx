import { motion } from 'framer-motion';
import { useTranslations } from "next-intl";
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
  tmdb_metadata?: Record<string, unknown>;
}

interface GenealogySectionProps {
  analysisData: AnalysisData | null;
  analysisStatus: string;
  onTriggerAnalysis?: () => void;
  analyzing?: boolean;
}

export default function GenealogySection({ 
  analysisData, 
  analysisStatus, 
  onTriggerAnalysis,
  analyzing = false
}: GenealogySectionProps) {
  const t = useTranslations("Genealogy");

  // Pending state with trigger button
  if (analysisStatus === 'pending' && onTriggerAnalysis) {
    return (
      <div className="border-b border-neutral-800 p-8 md:p-16">
        <h2 className="text-2xl md:text-3xl font-bold uppercase tracking-tight mb-8">Film Genealogy</h2>
        <div className="flex flex-col items-center justify-center py-16 space-y-6">
          <p className="text-sm text-neutral-500 uppercase tracking-widest text-center">
            {t("pendingStatus")}
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
                  {t("analyzing")}
                </span>
              </>
            ) : (
              t("trigger")
            )}
          </button>
          <p className="text-xs text-neutral-600 text-center max-w-md">
            The process typically takes 90-120 seconds.
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
            <p className="text-sm text-neutral-500 uppercase tracking-widest">{t("analyzing")}</p>
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
        <div className="flex flex-col items-center justify-center py-16 space-y-6">
          <p className="text-neutral-500 text-sm uppercase tracking-widest">{t("failedStatus")}</p>
          {onTriggerAnalysis && (
            <>
              <p className="text-xs text-neutral-600 text-center max-w-md">
                The previous analysis attempt failed. You can try again below.
              </p>
              <button
                onClick={onTriggerAnalysis}
                disabled={analyzing}
                className="px-8 py-4 border-2 border-neutral-700 bg-black text-neutral-400 font-bold uppercase tracking-widest text-sm hover:border-white hover:text-white transition-all duration-300 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {analyzing ? (
                  <span className="flex items-center gap-3">
                    <div className="animate-spin h-4 w-4 border-2 border-neutral-700 border-t-white rounded-full"></div>
                    Retrying...
                  </span>
                ) : (
                  'Retry Analysis'
                )}
              </button>
            </>
          )}
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
          className="mb-16"
        >
          <p className="text-xl md:text-2xl font-serif italic text-neutral-300 leading-relaxed">
            {influence_impact}
          </p>
        </motion.div>
      )}

      {/* A24-style Hairline Divider */}
      <div className="border-t border-neutral-900 mb-12" />

      {/* Genealogy Grid - A24 3-column style */}
      <div className="space-y-16">
        {/* Ancestors Section */}
        <div>
          <h3 className="text-[11px] font-medium uppercase tracking-[0.1em] text-neutral-500 mb-8">
            {t("ancestors")}
          </h3>
          {ancestors.length > 0 ? (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-x-8 gap-y-12">
              {ancestors.map((film, index) => (
                <FilmCard
                  key={`ancestor-${index}`}
                  title={film.title}
                  year={film.year}
                  type={film.type}
                  reason={film.reason}
                  variant="ancestor"
                />
              ))}
            </div>
          ) : (
            <div className="py-12 text-center border border-dashed border-neutral-900">
              <p className="text-xs text-neutral-600 uppercase tracking-widest">No ancestors identified</p>
            </div>
          )}
        </div>

        {/* Descendants Section */}
        <div>
          <h3 className="text-[11px] font-medium uppercase tracking-[0.1em] text-neutral-500 mb-8">
            {t("descendants")}
          </h3>
          {descendants.length > 0 ? (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-x-8 gap-y-12">
              {descendants.map((film, index) => (
                <FilmCard
                  key={`descendant-${index}`}
                  title={film.title}
                  year={film.year}
                  type={film.type}
                  reason={film.reason}
                  variant="descendant"
                />
              ))}
            </div>
          ) : (
            <div className="py-12 text-center border border-dashed border-neutral-900">
              <p className="text-xs text-neutral-600 uppercase tracking-widest">No descendants identified</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
