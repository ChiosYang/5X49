import { motion } from 'framer-motion';

interface FilmCardProps {
  title: string;
  year: number;
  type: string;
  reason: string;
  variant: 'ancestor' | 'descendant';
}

export default function FilmCard({ title, year, type, reason, variant }: FilmCardProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.6 }}
      className="group cursor-default"
    >
      {/* A24-style: Small grey uppercase label */}
      <div className="mb-3">
        <span className="text-[11px] font-medium uppercase tracking-[0.1em] text-neutral-500">
          {variant === 'ancestor' ? 'BEFORE' : 'AFTER'} {year}
        </span>
      </div>

      {/* A24-style: Large, bold title */}
      <h4 className="text-[28px] font-bold leading-[1.1] mb-4 tracking-tight group-hover:opacity-70 transition-opacity">
        {title}
      </h4>

      {/* Relationship type badge - subtle */}
      <div className="mb-3">
        <span className="inline-block px-3 py-1 text-[10px] font-medium uppercase tracking-widest border border-neutral-800 text-neutral-600">
          {type}
        </span>
      </div>

      {/* Reason - clean typography */}
      <p className="text-sm leading-relaxed text-neutral-400">
        {reason}
      </p>

      {/* Subtle bottom border like A24 dividers */}
      <div className="mt-6 pt-6 border-t border-neutral-900" />
    </motion.div>
  );
}
