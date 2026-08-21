import type { ExternalScore } from "@/types/movie";

interface ExternalScoreStripProps {
  scores?: ExternalScore[] | null;
  compact?: boolean;
  showLinks?: boolean;
}

const SOURCE_ORDER = ["letterboxd", "tspdt", "sight_sound", "sight_sound_critics", "sight_sound_directors"];

function sortedScores(scores: ExternalScore[]) {
  return [...scores].sort((a, b) => {
    const aIndex = SOURCE_ORDER.indexOf(a.source);
    const bIndex = SOURCE_ORDER.indexOf(b.source);
    return (aIndex === -1 ? 99 : aIndex) - (bIndex === -1 ? 99 : bIndex);
  });
}

function shortLabel(score: ExternalScore) {
  const label = score.label || score.source;
  if (score.source === "letterboxd") {
    return "LBXD";
  }
  if (score.source.startsWith("sight_sound")) {
    return "S&S";
  }
  return label;
}

function primaryValue(score: ExternalScore) {
  if (score.kind === "rank" && score.rank) {
    return `#${score.rank}`;
  }
  if (score.kind === "rating" && typeof score.value === "number") {
    return score.scale ? `${score.value}/${score.scale}` : String(score.value);
  }
  return null;
}

function movement(score: ExternalScore) {
  if (!score.rank || !score.previous_rank || score.rank === score.previous_rank) {
    return null;
  }
  const delta = score.previous_rank - score.rank;
  return delta > 0 ? `+${delta}` : String(delta);
}

export default function ExternalScoreStrip({
  scores,
  compact = false,
  showLinks = true,
}: ExternalScoreStripProps) {
  const visibleScores = sortedScores(scores || [])
    .filter((score) => primaryValue(score))
    .slice(0, compact ? 3 : 6);

  if (visibleScores.length === 0) {
    return null;
  }

  if (compact) {
    return (
      <div className="flex flex-wrap items-center gap-1.5">
        {visibleScores.map((score) => (
          <span
            key={score.source}
            className="inline-flex h-5 max-w-full items-center gap-1 rounded-control border border-ink/20 bg-ink/[0.07] px-1.5 text-[10px] leading-none font-black text-ink uppercase"
            title={[score.list_name, score.edition].filter(Boolean).join(" ")}
          >
            <span className="truncate text-ink-muted">{shortLabel(score)}</span>
            <span>{primaryValue(score)}</span>
          </span>
        ))}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
      {visibleScores.map((score) => {
        const value = primaryValue(score);
        const delta = movement(score);
        const content = (
          <div className="duration-standard min-w-0 border border-line-strong bg-surface px-4 py-3 transition-colors hover:border-ink-disabled">
            <div className="flex items-center justify-between gap-4">
              <span className="truncate text-[10px] font-bold tracking-widest text-ink-subtle uppercase">
                {score.label || score.source}
              </span>
              {score.edition && (
                <span className="shrink-0 text-[10px] font-bold tracking-widest text-ink-disabled uppercase">
                  {score.edition}
                </span>
              )}
            </div>
            <div className="mt-2 flex items-baseline gap-2">
              <span className="text-2xl leading-none font-black text-ink uppercase">{value}</span>
              {delta && (
                <span className="text-xs font-bold tracking-widest text-ink-muted uppercase">
                  {delta}
                </span>
              )}
            </div>
            {score.list_name && (
              <p className="mt-2 truncate text-xs font-medium text-ink-subtle">{score.list_name}</p>
            )}
          </div>
        );

        if (showLinks && score.url) {
          return (
            <a key={score.source} href={score.url} target="_blank" rel="noreferrer" className="focus-ring block">
              {content}
            </a>
          );
        }
        return <div key={score.source}>{content}</div>;
      })}
    </div>
  );
}
