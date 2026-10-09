"use client";

import { useId, useState } from "react";
import Image from "next/image";
import { useTranslations } from "next-intl";
import { Search } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { TextInput } from "@/components/ui/FormControls";

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
  selectLabel,
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
  selectLabel?: string;
  showCandidates?: boolean;
  showFewerLabel: string;
  showMoreLabel: (hiddenCount: number) => string;
}) {
  const t = useTranslations("LibraryManagement");
  const detailsId = useId();
  const [inspectedId, setInspectedId] = useState<number | null>(null);
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
          onChange={(event) => {
            setInspectedId(null);
            onInputChange(event.target.value);
          }}
          aria-label={placeholder}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.nativeEvent.isComposing) {
              event.preventDefault();
              if (!disabled && !lookupBusy && !selectionBusy && inputValue.trim()) {
                setInspectedId(null);
                onLookup();
              }
            }
          }}
          onFocus={onInputFocus}
          placeholder={placeholder}
          className="min-h-11 min-w-0 flex-1 px-3 py-2 text-sm"
        />
        <Button
          size="sm"
          onClick={() => { setInspectedId(null); onLookup(); }}
          disabled={disabled || selectionBusy || !inputValue.trim()}
          busy={lookupBusy}
          icon={<Search className="h-3 w-3" />}
          className="w-24"
        >
          {lookupLabel}
        </Button>
      </div>
      {showCandidates ? (
        <div className="space-y-2 pt-1">
          {visibleCandidates.map((candidate) => {
            const inspected = inspectedId === candidate.tmdb_id;
            const panelId = `${detailsId}-${candidate.tmdb_id}`;
            return (
              <div key={candidate.tmdb_id} className="border border-line-strong bg-surface-raised">
                <button
                  type="button"
                  onClick={() => setInspectedId(inspected ? null : candidate.tmdb_id)}
                  onKeyDown={(event) => {
                    if (event.key === "Escape" && inspected) {
                      event.stopPropagation();
                      setInspectedId(null);
                    }
                  }}
                  disabled={disabled || selectionBusy}
                  aria-expanded={inspected}
                  aria-controls={panelId}
                  className="focus-ring duration-standard block w-full px-3 py-3 text-left text-xs text-ink-muted transition-colors hover:text-ink disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <span className="block break-words font-bold tracking-widest uppercase">
                    {candidate.title} {candidate.year ? `(${candidate.year})` : ""}
                  </span>
                  <span className="mt-1 block text-ink-subtle">
                    TMDB {candidate.tmdb_id} · {Math.round(candidate.score)}%
                  </span>
                  <span className="mt-2 block text-ink-subtle">{t(inspected ? "candidateHideDetails" : "candidateViewDetails")}</span>
                </button>
                {inspected ? (
                  <div id={panelId} className="space-y-3 border-t border-line p-3 text-xs" onKeyDown={(event) => {
                    if (event.key === "Escape") {
                      event.stopPropagation();
                      setInspectedId(null);
                      (event.currentTarget.previousElementSibling as HTMLButtonElement | null)?.focus();
                    }
                  }}>
                    <div className="flex items-start gap-3">
                      {candidate.poster_path ? (
                        <Image
                          src={`https://image.tmdb.org/t/p/w185${candidate.poster_path}`}
                          alt=""
                          width={80}
                          height={120}
                          unoptimized
                          className="h-auto w-20 shrink-0"
                        />
                      ) : null}
                      <div className="min-w-0 space-y-2">
                        {candidate.original_title && candidate.original_title !== candidate.title ? (
                          <p className="break-words font-medium text-ink">{candidate.original_title}</p>
                        ) : null}
                        <p className="break-words whitespace-pre-line leading-5 text-ink-muted">{candidate.overview || t("candidateNoOverview")}</p>
                      </div>
                    </div>
                    <Button
                      size="sm"
                      variant="primary"
                      disabled={disabled || lookupBusy || selectionBusy}
                      busy={selectionBusy && (busyCandidateId == null || busyCandidateId === candidate.tmdb_id)}
                      onClick={() => onSelect(candidate)}
                    >
                      {selectLabel ?? t("candidateConfirmMatch")}
                    </Button>
                  </div>
                ) : null}
              </div>
            );
          })}
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
