"use client";

import Image from "next/image";
import { useSWRConfig } from "swr";
import { useEffect, useId, useRef, useState, useSyncExternalStore } from "react";
import { useTranslations } from "next-intl";
import { ArrowUpRight, Check, Globe2, Loader2, Star } from "lucide-react";
import { Link, useRouter } from "@/i18n/routing";
import { rememberFilmReturn } from "@/lib/navigation-context";
import { Button } from "@/components/ui/Button";
import { API } from "@/lib/api";
import { invalidateViewingCaches, useUpdateFilmProfileState } from "@/hooks/useFilm";
import { todayLocalDate, watchedActionFor } from "@/lib/diary";
import type { AudioTrack, FilmProfileState, LibraryFilmSummary } from "@/types/movie";
import ExternalScoreStrip from "../components/ExternalScoreStrip";

// An additional touchscreen must not disable hover for a primary mouse/trackpad.
const touchQuery = "(hover: none), (pointer: coarse)";
function subscribeTouchInput(callback: () => void) {
  const media = window.matchMedia(touchQuery);
  media.addEventListener("change", callback);
  return () => media.removeEventListener("change", callback);
}
const getTouchSnapshot = () => window.matchMedia(touchQuery).matches;
const getTouchServerSnapshot = () => false;

interface LibraryMovieCardProps {
  movie: LibraryFilmSummary;
  priority?: boolean;
  readOnly?: boolean;
  onProfileSaved?: (state: FilmProfileState) => void;
}

type MediaSpecBadge = {
  kind?: "dolby-vision" | "dts";
  label: string;
  variant: "solid" | "outline";
};

const COUNTRY_CODE_ALIASES: Record<string, string> = {
  america: "US",
  argentina: "AR",
  australia: "AU",
  austria: "AT",
  belgium: "BE",
  brazil: "BR",
  canada: "CA",
  china: "CN",
  denmark: "DK",
  finland: "FI",
  france: "FR",
  germany: "DE",
  gbr: "GB",
  hk: "HK",
  hongkong: "HK",
  hongkongchina: "HK",
  india: "IN",
  ireland: "IE",
  italy: "IT",
  japan: "JP",
  korea: "KR",
  mainlandchina: "CN",
  mexico: "MX",
  netherlands: "NL",
  newzealand: "NZ",
  norway: "NO",
  prc: "CN",
  russia: "RU",
  southkorea: "KR",
  sovietunion: "RU",
  spain: "ES",
  sweden: "SE",
  switzerland: "CH",
  taiwan: "TW",
  uk: "GB",
  unitedkingdom: "GB",
  unitedstates: "US",
  unitedstatesofamerica: "US",
  us: "US",
  usa: "US",
  中国: "CN",
  中国大陆: "CN",
  台湾: "TW",
  台灣: "TW",
  德国: "DE",
  日本: "JP",
  法国: "FR",
  美国: "US",
  英国: "GB",
  韩国: "KR",
  香港: "HK",
};

function formatAudioSpec(track?: AudioTrack | null) {
  if (!track?.codec) {
    return null;
  }

  const codecMap: Record<string, string> = {
    aac: "AAC",
    ac3: "AC-3",
    dts: "DTS",
    eac3: "E-AC-3",
    flac: "FLAC",
    truehd: "TRUEHD",
  };
  const codec = codecMap[track.codec.toLowerCase()] || track.codec.toUpperCase();

  return codec;
}

function getAudioSpecBadge(track?: AudioTrack | null): MediaSpecBadge | null {
  if (!track?.codec) {
    return null;
  }

  const codec = track.codec.toLowerCase();
  if (codec === "dts" || codec === "dca" || codec.startsWith("dts")) {
    return { kind: "dts", label: "DTS", variant: "outline" };
  }

  const label = formatAudioSpec(track);
  return label ? { label, variant: "outline" } : null;
}

function formatBitrate(bitRate?: number | null) {
  if (!bitRate) {
    return null;
  }

  if (bitRate >= 1_000_000) {
    return `${(bitRate / 1_000_000).toFixed(1)} Mbps`;
  }
  return `${Math.round(bitRate / 1000)} Kbps`;
}

function formatDynamicRange(value?: string | null) {
  if (!value || value === "unknown") {
    return null;
  }
  if (value.toLowerCase() === "dolby vision") {
    return "DOLBY VISION";
  }
  return value.toUpperCase();
}

function formatVideoCodec(codec?: string | null) {
  if (!codec) {
    return null;
  }

  const codecMap: Record<string, string> = {
    av1: "AV1",
    h264: "H.264",
    h265: "H.265",
    hevc: "HEVC",
    mpeg4: "MPEG-4",
    vp9: "VP9",
  };
  return codecMap[codec.toLowerCase()] || codec.toUpperCase();
}

function formatResolutionBadge(movie: LibraryFilmSummary) {
  const width = movie.primary_item.video?.width;
  const height = movie.primary_item.video?.height;
  if (!width || !height) {
    return null;
  }

  const longEdge = Math.max(width, height);
  const shortEdge = Math.min(width, height);

  if (longEdge >= 3200 || shortEdge >= 1800) {
    return "4K";
  }
  if (longEdge >= 2000 || shortEdge >= 1100) {
    return "2K";
  }
  if (longEdge >= 1600 || shortEdge >= 900) {
    return "1080p";
  }
  if (longEdge >= 1100 || shortEdge >= 600) {
    return "720p";
  }
  return "480p";
}

function countryCodeToFlag(code: string) {
  return code
    .toUpperCase()
    .replace(/./g, (char) => String.fromCodePoint(127397 + char.charCodeAt(0)));
}

function countryToCode(country?: string | null) {
  if (!country) {
    return null;
  }

  const trimmed = country.trim();
  if (/^[a-z]{2}$/i.test(trimmed)) {
    return trimmed.toUpperCase();
  }

  const normalized = trimmed.toLowerCase().replace(/[^a-z\u4e00-\u9fff]/g, "");
  return COUNTRY_CODE_ALIASES[normalized] || null;
}

function getMediaSpecBadges(movie: LibraryFilmSummary): MediaSpecBadge[] {
  const video = movie.primary_item.video;
  const resolution = formatResolutionBadge(movie);
  const dynamicRange = formatDynamicRange(video?.dynamic_range);
  const videoCodec = formatVideoCodec(video?.codec);
  const audioSpec = getAudioSpecBadge(video?.audio_tracks?.[0]);
  const bitrate = formatBitrate(video?.bitrate);
  const bitDepth = video?.bit_depth ? `${video.bit_depth}-bit` : null;

  const badges: Array<MediaSpecBadge | null> = [
    resolution ? { label: resolution, variant: "solid" as const } : null,
    dynamicRange
      ? {
          kind: dynamicRange === "DOLBY VISION" ? "dolby-vision" as const : undefined,
          label: dynamicRange,
          variant: "outline" as const,
        }
      : null,
    videoCodec ? { label: videoCodec, variant: "outline" as const } : null,
    audioSpec,
    bitrate ? { label: bitrate, variant: "outline" as const } : null,
    bitDepth ? { label: bitDepth, variant: "outline" as const } : null,
  ];

  return badges.filter((badge): badge is MediaSpecBadge => Boolean(badge)).slice(0, 5);
}

function getMetadataBadge(movie: LibraryFilmSummary) {
  const metadata = movie.primary_item.metadata;
  if (metadata.source !== "filename" && metadata.scrape_status !== "failed") {
    return null;
  }

  if (metadata.scrape_status === "needs_review") {
    return "metadataNeedsReview";
  }
  if (metadata.scrape_status === "failed") {
    return "metadataFailed";
  }
  return "metadataUnmatched";
}



export default function LibraryMovieCard({ movie, priority = false, readOnly = false, onProfileSaved }: LibraryMovieCardProps) {
  const t = useTranslations("Library");
  const { cache } = useSWRConfig();
  const router = useRouter();
  const { trigger, isMutating } = useUpdateFilmProfileState(movie.id);
  const artwork = movie.primary_item.artwork;
  const [localState, setLocalState] = useState<{ baseline: string | null | undefined; state: FilmProfileState } | null>(null);
  const profileState = localState && localState.baseline === movie.profile_state.updated_at ? localState.state : movie.profile_state;
  const setProfileState = (state: FilmProfileState) => setLocalState({ baseline: movie.profile_state.updated_at, state });
  const [actionsOpen, setActionsOpen] = useState(false);
  const [actionsDismissed, setActionsDismissed] = useState(false);
  const [feedback, setFeedback] = useState<"failed" | "refreshFailed" | null>(null);
  const [retryAction, setRetryAction] = useState<"favorite" | "watched" | null>(null);
  const submitting = useRef(false);
  const cardRoot = useRef<HTMLDivElement>(null);
  const filmTrigger = useRef<HTMLElement>(null);
  const touchInput = useSyncExternalStore(subscribeTouchInput, getTouchSnapshot, getTouchServerSnapshot);
  const touchControl = touchInput && !readOnly;
  const panelId = useId();
  useEffect(() => {
    if (!touchControl || !actionsOpen) return;
    const dismissOutside = (event: MouseEvent) => {
      if (!cardRoot.current?.contains(event.target as Node)) {
        setActionsOpen(false); setActionsDismissed(true);
      }
    };
    // Collapse after activation, so tapping another card cannot move its target mid-tap.
    document.addEventListener("click", dismissOutside);
    return () => document.removeEventListener("click", dismissOutside);
  }, [actionsOpen, touchControl]);
  const watched = Boolean(profileState.watched);
  const favorite = Boolean(profileState.favorite);
  const artworkVersion = movie.primary_item.metadata.updated_at
    ? `?v=${encodeURIComponent(movie.primary_item.metadata.updated_at)}`
    : "";
  const backdropPath = artwork.backdrop_thumb_local || artwork.backdrop_local;
  const backdropSrc = backdropPath
    ? `${API.mediaUrl(backdropPath)}${artworkVersion}`
    : artwork.backdrop_provider ? API.providerArtworkUrl(artwork.backdrop_provider) : null;
  const title = movie.title;
  const description = movie.overview || movie.micro_genre || "";
  const country = movie.countries?.[0];
  const countryCode = countryToCode(country);
  const countryFlag = countryCode ? countryCodeToFlag(countryCode) : null;
  const extraCountryCount = Math.max((movie.countries?.length || 0) - 1, 0);
  const mediaSpecBadges = getMediaSpecBadges(movie);
  const metadataBadge = getMetadataBadge(movie);
  const tags = [
    movie.micro_genre,
    ...(movie.genres || []),
    movie.directors?.[0] ? `Dir. ${movie.directors[0]}` : undefined,
  ]
    .filter(Boolean)
    .slice(0, 3);

  const updateState = async (kind: "favorite" | "watched") => {
    if (submitting.current) return;
    const action = watchedActionFor(profileState);
    if (kind === "watched" && action === "open_diary") {
      router.push(`/diary?film=${movie.id}`);
      return;
    }
    submitting.current = true;
    setFeedback(null);
    setRetryAction(null);
    let saved: FilmProfileState;
    try {
      saved = await trigger(kind === "favorite" ? { favorite: !favorite } : {
        watched: action === "mark_watched",
        watched_at: action === "mark_watched" ? profileState.watched_at || todayLocalDate() : null,
      });
    } catch {
      setFeedback("failed");
      setRetryAction(kind);
      submitting.current = false;
      return;
    }
    setProfileState(saved);
    onProfileSaved?.(saved);
    try { await invalidateViewingCaches(movie.id, cache.keys()); } catch { setFeedback("refreshFailed"); }
    submitting.current = false;
  };

  const retry = async () => {
    if (retryAction) { await updateState(retryAction); return; }
    try { await invalidateViewingCaches(movie.id, cache.keys()); setFeedback(null); } catch { setFeedback("refreshFailed"); }
  };

  const artworkContent = (
    <div className="relative h-full w-full overflow-hidden rounded-media">
      {backdropSrc ? (
        <Image
          src={backdropSrc!}
          alt={movie.title}
          fill
          priority={priority}
          sizes="(min-width: 1280px) 25vw, (min-width: 1024px) 33vw, (min-width: 640px) 50vw, 100vw"
          className="object-cover transition-transform delay-0 duration-standard ease-exit group-hover:scale-[1.05] group-hover:delay-inspection"
        />
      ) : (
        <div className="flex h-full w-full items-center justify-center border border-line-strong transition-transform delay-0 duration-standard ease-exit group-hover:scale-[1.05] group-hover:delay-inspection">
          <span className="font-serif text-4xl text-surface-hover">?</span>
        </div>
      )}
      {metadataBadge && (
        <span className="z-raised absolute top-3 left-3 rounded-small bg-canvas/80 px-2 py-1 text-[10px] font-black tracking-widest text-ink uppercase">
          {t(metadataBadge)}
        </span>
      )}
      {watched && (
        <span className="z-raised absolute top-3 right-3 text-ink drop-shadow-[0_1px_4px_rgba(0,0,0,0.9)]">
          <Check className="h-5 w-5 stroke-[3]" aria-label={t("watched")} />
        </span>
      )}
      {/* Hover Overlay */}
      <div className="library-card-shade absolute inset-0 bg-canvas/0 transition-colors duration-standard" />
      <div className="library-card-overlay invisible absolute inset-x-0 bottom-0 flex flex-col gap-1 bg-gradient-to-t from-canvas/80 via-canvas/35 to-transparent px-5 pt-12 pb-4 opacity-0 transition-[opacity,transform] duration-standard">
        <h3 className="line-clamp-1 text-2xl leading-none font-black text-ink uppercase">
          {title}
        </h3>
        <p className="line-clamp-1 text-xs font-bold tracking-wide text-ink uppercase">
          {movie.directors?.[0] || movie.title} {movie.year}
        </p>
      </div>
    </div>
  );

  return (
    <div ref={cardRoot} className="block" onKeyDown={(event) => {
      if (event.key === "Escape" && !readOnly) {
        event.stopPropagation(); setActionsOpen(false); setActionsDismissed(true);
        filmTrigger.current?.focus({ preventScroll: true });
      }
    }}>
      <div className="space-y-4">
        {/* Landscape Still */}
        <div className={`${readOnly ? "" : "library-card-media group"} relative aspect-video w-full bg-surface-raised`}
          data-actions-open={actionsOpen} data-actions-dismissed={actionsDismissed} data-touch-control={touchControl}
          onPointerEnter={() => setActionsDismissed(false)}
          onFocusCapture={(event) => {
            if (!event.currentTarget.contains(event.relatedTarget)) setActionsDismissed(false);
          }}
          onBlur={(event) => {
            if (!touchControl && !event.currentTarget.contains(event.relatedTarget)) setActionsOpen(false);
          }}>
          {touchControl ? <button ref={(node) => { filmTrigger.current = node; }} type="button"
            id={`film-link-${movie.id}`} aria-label={t("cardActions", { title })} aria-expanded={actionsOpen} aria-controls={panelId}
            onClick={() => { setActionsOpen(!actionsOpen); setActionsDismissed(actionsOpen); }}
            className="library-card-touch-image focus-ring relative block aspect-video w-full cursor-pointer overflow-hidden rounded-media bg-transparent p-0 text-left">
            <div className="absolute inset-0">{artworkContent}</div>
          </button> : <Link ref={(node) => { filmTrigger.current = node; }} href={`/library/${movie.id}`} aria-label={title}
            onClick={() => rememberFilmReturn(movie.id)} scroll={false} id={`film-link-${movie.id}`} className="focus-ring block h-full cursor-pointer rounded-media">
            {artworkContent}
          </Link>}

          {!readOnly && <div id={panelId} className="library-card-inspector liquid-glass-popover z-inspector invisible absolute top-full right-0 left-0 overflow-hidden rounded-b-media border border-line/80 p-5 text-ink opacity-0 transition-[opacity,transform] duration-standard">
            <div className="z-raised relative space-y-4">
              {touchControl && <Link href={`/library/${movie.id}`} onClick={() => rememberFilmReturn(movie.id)} scroll={false}
                className="focus-ring inline-flex min-h-11 items-center gap-2 text-sm font-medium text-ink underline underline-offset-4">
                {t("viewFilmDetails")}<ArrowUpRight className="h-4 w-4" aria-hidden="true" />
              </Link>}
              <div className="flex flex-wrap items-center gap-3">
                <button
                  type="button"
                  onClick={() => void updateState("watched")}
                  aria-disabled={isMutating}
                  className={`focus-ring duration-standard inline-flex min-h-11 items-center gap-2 rounded-pill px-4 text-sm font-black tracking-wide uppercase transition-colors ${
                    watched
                      ? "bg-inverse text-inverse-ink group-hover:bg-neutral-200"
                      : "border border-ink/55 text-ink hover:border-ink hover:bg-inverse hover:text-inverse-ink"
                  } disabled:cursor-not-allowed disabled:opacity-60`}
                  aria-label={watched && !profileState.manual_watched ? t("viewDiary") : watched ? t("markUnwatched") : t("markWatched")}
                  title={watched && !profileState.manual_watched ? t("viewDiary") : watched ? t("markUnwatched") : t("markWatched")}
                >
                  {isMutating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
                  {watched && !profileState.manual_watched ? t("viewDiary") : watched ? t("watched") : t("markWatched")}
                </button>
                <button
                  type="button"
                  onClick={() => void updateState("favorite")}
                  aria-disabled={isMutating}
                  className={`focus-ring duration-standard flex h-11 w-11 items-center justify-center rounded-pill border transition-colors ${
                    favorite
                      ? "border-inverse bg-inverse text-inverse-ink"
                      : "border-ink/55 text-ink hover:border-ink"
                  } disabled:cursor-not-allowed disabled:opacity-60`}
                  aria-label={favorite ? t("unfavorite") : t("favorite")}
                  title={favorite ? t("unfavorite") : t("favorite")}
                >
                  <Star className={`h-4 w-4 ${favorite ? "fill-current" : ""}`} />
                </button>
              </div>

              {feedback && <div role="status" className="space-y-2 text-sm text-warning">
                <p>{t(feedback === "failed" ? "cardSaveFailed" : "cardRefreshFailed")}</p>
                <Button size="sm" aria-disabled={isMutating} onClick={() => void retry()}>{t("retryAction")}</Button>
              </div>}
              <p className="overflow-hidden text-[15px] leading-snug text-ink-muted [display:-webkit-box] [-webkit-box-orient:vertical] [-webkit-line-clamp:4]">
                {description || `${title} (${movie.year})`}
              </p>

              <ExternalScoreStrip scores={movie.external_scores} compact showLinks={false} />

              {(mediaSpecBadges.length > 0 || country) && (
                <div className="flex flex-wrap items-center gap-1.5">
                  {mediaSpecBadges.map((badge) => (
                    <span
                      key={badge.label}
                      className={
                        badge.kind
                          ? "inline-flex h-5 items-center text-ink"
                          : badge.variant === "solid"
                          ? "inline-flex h-5 items-center rounded-control border border-ink/60 bg-ink/90 px-1.5 text-[10px] leading-none font-black text-line-strong uppercase shadow-[inset_0_1px_0_rgba(255,255,255,0.8),0_1px_6px_rgba(255,255,255,0.08)]"
                          : "inline-flex h-5 items-center rounded-control border border-ink/35 bg-ink/[0.06] px-1.5 text-[10px] leading-none font-black text-ink uppercase shadow-[inset_0_1px_0_rgba(255,255,255,0.14)]"
                      }
                    >
                      {badge.kind === "dolby-vision" ? (
                        <Image
                          src="/dolby-vision.svg"
                          alt="Dolby Vision"
                          width={56}
                          height={14}
                          className="h-3.5 w-auto opacity-90"
                        />
                      ) : badge.kind === "dts" ? (
                        <Image
                          src="/dts.svg"
                          alt="DTS"
                          width={34}
                          height={15}
                          className="h-3.5 w-auto opacity-90"
                        />
                      ) : (
                        badge.label
                      )}
                    </span>
                  ))}
                  {country && (
                    <span
                      className={
                        countryFlag
                          ? "inline-flex h-5 items-center gap-1 text-ink-muted"
                          : "inline-flex h-5 items-center gap-1 rounded-control border border-ink/35 bg-ink/[0.06] px-1.5 text-[10px] leading-none font-black text-ink uppercase shadow-[inset_0_1px_0_rgba(255,255,255,0.14)]"
                      }
                      title={movie.countries?.join(", ")}
                      aria-label={movie.countries?.join(", ")}
                    >
                      {countryFlag ? (
                        <span className="text-base leading-none">{countryFlag}</span>
                      ) : (
                        <>
                          <Globe2 className="h-3.5 w-3.5 text-ink-subtle" />
                          <span className="max-w-20 truncate">{country}</span>
                        </>
                      )}
                      {extraCountryCount > 0 && (
                        <span className="text-xs font-bold text-ink-muted">+{extraCountryCount}</span>
                      )}
                    </span>
                  )}
                </div>
              )}

              {tags.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {tags.map((tag) => (
                    <span
                      key={tag}
                      className="max-w-full truncate rounded-pill border border-ink/10 bg-ink/5 px-2.5 py-1 text-[10px] font-black tracking-widest text-ink-muted uppercase"
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>}
        </div>

        {/* Title & Info */}
        <Link href={`/library/${movie.id}`} onClick={() => rememberFilmReturn(movie.id)} onFocus={() => { if (!touchControl) { setActionsOpen(false); setActionsDismissed(true); } }} scroll={false} className="library-card-title focus-ring duration-standard flex min-w-0 cursor-pointer items-start justify-between gap-3 transition-opacity">
          <div className="min-w-0 space-y-1">
            <h3 className="break-words text-xl md:text-2xl font-bold uppercase leading-none tracking-tight">
              {title}
            </h3>
            {metadataBadge && (
              <p className="text-[10px] font-black tracking-widest text-ink-subtle uppercase">
                {t(metadataBadge)}
              </p>
            )}
          </div>
          <span className="shrink-0 font-serif text-xl text-ink-muted italic">
            {movie.year}
          </span>
        </Link>
      </div>
    </div>
  );
}
