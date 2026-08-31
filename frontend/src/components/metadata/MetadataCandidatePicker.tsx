"use client";

import { useState } from "react";
import { Search } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { TextInput } from "@/components/ui/FormControls";
import { Spinner } from "@/components/ui/Feedback";
import type { MetadataSearchResult } from "@/types/movie";
export {
  parseMetadataSearchInput,
  parseTmdbId,
  prependMetadataCandidate,
} from "@/lib/metadata-search";

const DEFAULT_VISIBLE_CANDIDATES = 5;

export function MetadataCandidatePicker({
  busyCandidateId,
  candidates,
  disabled = false,
  inputValue,
  lookupBusy = false,
  lookupLabel,
  onInputChange,
  onInputFocus,
  onLookup,
  onSelect,
  placeholder,
  selectionBusy = false,
  showCandidates = true,
  showFewerLabel,
  showMoreLabel,
}: {
  busyCandidateId?: number | null;
  candidates: MetadataSearchResult[];
  disabled?: boolean;
  inputValue: string;
  lookupBusy?: boolean;
  lookupLabel: string;
  onInputChange: (value: string) => void;
  onInputFocus?: () => void;
  onLookup: () => void;
  onSelect: (candidate: MetadataSearchResult) => void;
  placeholder: string;
  selectionBusy?: boolean;
  showCandidates?: boolean;
  showFewerLabel: string;
  showMoreLabel: (hiddenCount: number) => string;
}) {
  const [expandedCandidateKey, setExpandedCandidateKey] = useState<string | null>(null);
  const candidateKey = candidates.map((candidate) => candidate.tmdb_id).join(",");
  const showAll = expandedCandidateKey === candidateKey;

  const visibleCandidates = showAll
    ? candidates
    : candidates.slice(0, DEFAULT_VISIBLE_CANDIDATES);

  return (
    <div className="space-y-2">
      <div className="flex gap-2">
        <TextInput
          type="text"
          value={inputValue}
          onChange={(event) => onInputChange(event.target.value)}
          onFocus={onInputFocus}
          placeholder={placeholder}
          className="min-h-9 min-w-0 flex-1 px-3 py-2 text-xs"
        />
        <Button
          size="sm"
          onClick={onLookup}
          disabled={disabled || !inputValue.trim()}
          busy={lookupBusy}
          icon={<Search className="h-3 w-3" />}
          className="h-9 w-24"
        >
          {lookupLabel}
        </Button>
      </div>
      {showCandidates ? (
        <div className="space-y-2 pt-1">
          {visibleCandidates.map((candidate) => (
            <button
              key={candidate.tmdb_id}
              type="button"
              onClick={() => onSelect(candidate)}
              disabled={disabled || selectionBusy}
              className="focus-ring duration-standard block w-full border border-line-strong bg-surface-raised px-3 py-2 text-left text-xs text-ink-muted transition-colors hover:border-ink-disabled hover:text-ink disabled:cursor-not-allowed disabled:opacity-50"
            >
              <span className="flex items-start justify-between gap-3">
                <span className="min-w-0">
                  <span className="block truncate font-bold tracking-widest uppercase">
                    {candidate.title} {candidate.year ? `(${candidate.year})` : ""}
                  </span>
                  <span className="block text-ink-subtle">
                    TMDB {candidate.tmdb_id} · {Math.round(candidate.score)}%
                  </span>
                </span>
                {selectionBusy && (busyCandidateId == null || busyCandidateId === candidate.tmdb_id) ? (
                  <Spinner className="mt-0.5 h-3 w-3" />
                ) : null}
              </span>
            </button>
          ))}
          {candidates.length > DEFAULT_VISIBLE_CANDIDATES ? (
            <button
              type="button"
              onClick={() => setExpandedCandidateKey(showAll ? null : candidateKey)}
              className="focus-ring duration-standard type-badge text-ink-subtle transition-colors hover:text-ink"
            >
              {showAll
                ? showFewerLabel
                : showMoreLabel(candidates.length - DEFAULT_VISIBLE_CANDIDATES)}
            </button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
