import { motion } from 'framer-motion';

interface FilmCardProps {
  title: string;
  year: number;
  type: string;
  reason: string;
  variant: 'ancestor' | 'descendant';
}

const typeColors = {
  '视觉': 'bg-blue-500/20 text-blue-400 border-blue-500/30',
  'Visual': 'bg-blue-500/20 text-blue-400 border-blue-500/30',
  '叙事': 'bg-purple-500/20 text-purple-400 border-purple-500/30',
  'Narrative': 'bg-purple-500/20 text-purple-400 border-purple-500/30',
  '叙事/视觉': 'bg-gradient-to-r from-purple-500/20 to-blue-500/20 text-purple-300 border-purple-500/30',
  '叙事/主题': 'bg-gradient-to-r from-purple-500/20 to-orange-500/20 text-purple-300 border-purple-500/30',
  '主题': 'bg-orange-500/20 text-orange-400 border-orange-500/30',
  'Theme': 'bg-orange-500/20 text-orange-400 border-orange-500/30',
  'default': 'bg-neutral-500/20 text-neutral-400 border-neutral-500/30'
};

export default function FilmCard({ title, year, type, reason, variant }: FilmCardProps) {
  const colorClass = typeColors[type as keyof typeof typeColors] || typeColors.default;

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
      className="group relative border border-neutral-800 bg-black/40 backdrop-blur-sm p-6 hover:border-neutral-600 transition-all duration-300"
    >
      {/* Direction Arrow Indicator */}
      <div className="absolute -top-3 left-6 bg-black px-2 text-[10px] font-bold uppercase tracking-widest text-neutral-500">
        {variant === 'ancestor' ? '← Before' : 'After →'}
      </div>

      {/* Film Title & Year */}
      <div className="mb-3">
        <h4 className="text-xl font-bold uppercase tracking-tight text-white group-hover:text-neutral-300 transition-colors">
          {title}
        </h4>
        <span className="text-sm text-neutral-500 font-mono">{year}</span>
      </div>

      {/* Type Badge */}
      <div className="mb-4">
        <span className={`inline-block px-3 py-1 text-[10px] font-bold uppercase tracking-widest border ${colorClass} rounded-full`}>
          {type}
        </span>
      </div>

      {/* Reason */}
      <p className="text-sm leading-relaxed text-neutral-400 line-clamp-3 group-hover:line-clamp-none transition-all">
        {reason}
      </p>
    </motion.div>
  );
}
