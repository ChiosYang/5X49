"use client";

import Image from "next/image";
import { type MouseEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { Check, Globe2, Loader2, Star } from "lucide-react";
import { mutate } from "swr";
import { Link } from "@/i18n/routing";
import { API } from "@/lib/api";
import { useUpdateMovieUserState } from "@/hooks/useMovie";
import type { AudioTrack, LibraryMovie, MovieUserState } from "@/types/movie";
import ExternalScoreStrip from "../components/ExternalScoreStrip";

interface LibraryMovieCardProps {
  movie: LibraryMovie;
  userState?: MovieUserState;
  priority?: boolean;
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

function formatResolutionBadge(movie: LibraryMovie) {
  const width = movie.video_width;
  const height = movie.video_height;
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

function getMediaSpecBadges(movie: LibraryMovie): MediaSpecBadge[] {
  const resolution = formatResolutionBadge(movie);
  const dynamicRange = formatDynamicRange(movie.video_dynamic_range);
  const videoCodec = formatVideoCodec(movie.video_codec);
  const audioSpec = getAudioSpecBadge(movie.audio_tracks?.[0]);
  const bitrate = formatBitrate(movie.video_bitrate);
  const bitDepth = movie.video_bit_depth ? `${movie.video_bit_depth}-bit` : null;

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

function getMetadataBadge(movie: LibraryMovie) {
  if (movie.metadata_source !== "filename" && movie.scrape_status !== "failed") {
    return null;
  }

  if (movie.scrape_status === "needs_review") {
    return "Needs review";
  }
  if (movie.scrape_status === "failed") {
    return "Match failed";
  }
  return "Unmatched";
}

function todayDateValue() {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export default function LibraryMovieCard({ movie, userState, priority = false }: LibraryMovieCardProps) {
  const t = useTranslations("Library");
  const router = useRouter();
  const { trigger, isMutating } = useUpdateMovieUserState(movie.id);
  const [watched, setWatched] = useState(Boolean(userState?.watched));
  const [favorite, setFavorite] = useState(Boolean(userState?.favorite));
  const artworkVersion = movie.metadata_updated_at ? `?v=${encodeURIComponent(movie.metadata_updated_at)}` : "";
  const backdropPath = movie.backdrop_thumb_local || movie.backdrop_local;
  const backdropSrc = backdropPath ? `${API.mediaUrl(backdropPath)}${artworkVersion}` : null;
  const title = movie.title_cn || movie.title;
  const description = movie.overview || movie.plot || movie.micro_genre || "";
  const country = movie.countries?.[0];
  const countryCode = countryToCode(country);
  const countryFlag = countryCode ? countryCodeToFlag(countryCode) : null;
  const extraCountryCount = Math.max((movie.countries?.length || 0) - 1, 0);
  const mediaSpecBadges = getMediaSpecBadges(movie);
  const metadataBadge = getMetadataBadge(movie);
  const tags = [
    movie.micro_genre,
    ...(movie.genres || []),
    movie.director ? `Dir. ${movie.director}` : undefined,
  ]
    .filter(Boolean)
    .slice(0, 3);

  const updateUserState = async (next: { watched?: boolean; favorite?: boolean }) => {
    const previousWatched = watched;
    const previousFavorite = favorite;
    const nextWatched = next.watched ?? watched;
    const nextFavorite = next.favorite ?? favorite;
    setWatched(nextWatched);
    setFavorite(nextFavorite);
    try {
      await trigger({
        watched: nextWatched,
        watched_at: nextWatched ? userState?.watched_at || todayDateValue() : null,
        favorite: nextFavorite,
      });
      await Promise.all([
        mutate(API.libraryMovieUserState(movie.id)),
        mutate(API.libraryUserStates()),
        mutate(API.watchHistory()),
      ]);
      router.refresh();
    } catch {
      setWatched(previousWatched);
      setFavorite(previousFavorite);
    }
  };

  const handleMovieLinkClick = (event: MouseEvent<HTMLAnchorElement>) => {
    if (
      event.defaultPrevented ||
      event.button !== 0 ||
      event.metaKey ||
      event.altKey ||
      event.ctrlKey ||
      event.shiftKey
    ) {
      return;
    }

    const href = event.currentTarget.getAttribute("href");
    if (!href) return;

    event.preventDefault();
    router.push(href, { scroll: false });
  };

  return (
    <div className="block">
      <div className="space-y-4">
        {/* Landscape Still */}
        <div className="peer/card group z-content hover:z-inspector relative aspect-video w-full bg-surface-raised">
          <Link href={`/library/${movie.id}`} scroll={false} onClick={handleMovieLinkClick} className="focus-ring block h-full cursor-pointer rounded-media">
            <div className="relative h-full w-full overflow-hidden rounded-media">
              {backdropSrc ? (
                <Image
                  src={backdropSrc!}
                  alt={movie.title}
                  fill
                  priority={priority}
                  sizes="(min-width: 1536px) 20vw, (min-width: 1280px) 25vw, (min-width: 1024px) 33vw, (min-width: 640px) 50vw, 100vw"
                  className="object-cover transition-transform delay-0 duration-standard ease-exit group-hover:scale-[1.05] group-hover:delay-inspection"
                />
              ) : (
                <div className="flex h-full w-full items-center justify-center border border-line-strong transition-transform delay-0 duration-standard ease-exit group-hover:scale-[1.05] group-hover:delay-inspection">
                  <span className="font-serif text-4xl text-surface-hover">?</span>
                </div>
              )}
              {metadataBadge && (
                <span className="z-raised absolute top-3 left-3 rounded-small bg-canvas/80 px-2 py-1 text-[10px] font-black tracking-widest text-ink uppercase">
                  {metadataBadge}
                </span>
              )}
              {watched && (
                <span className="z-raised absolute top-3 right-3 text-ink drop-shadow-[0_1px_4px_rgba(0,0,0,0.9)]">
                  <Check className="h-5 w-5 stroke-[3]" aria-label={t("watched")} />
                </span>
              )}
              {/* Hover Overlay */}
              <div className="absolute inset-0 bg-canvas/0 transition-colors delay-0 duration-standard group-hover:bg-canvas/35 group-hover:delay-inspection" />
              <div className="invisible absolute inset-x-0 bottom-0 flex translate-y-1 flex-col gap-1 bg-gradient-to-t from-canvas/80 via-canvas/35 to-transparent px-5 pt-12 pb-4 opacity-0 transition-[opacity,transform] delay-0 duration-standard group-hover:visible group-hover:translate-y-0 group-hover:opacity-100 group-hover:delay-inspection">
                <h3 className="line-clamp-1 text-2xl leading-none font-black text-ink uppercase">
                  {title}
                </h3>
                <p className="line-clamp-1 text-xs font-bold tracking-wide text-ink uppercase">
                  {movie.director || movie.title} {movie.year}
                </p>
              </div>
            </div>
          </Link>

          <div className="liquid-glass-popover z-inspector invisible absolute top-full right-0 left-0 origin-top translate-y-1 scale-95 overflow-hidden rounded-b-media border border-line/80 p-5 text-ink opacity-0 transition-[opacity,transform] delay-0 duration-standard ease-exit group-hover:visible group-hover:translate-y-0 group-hover:scale-100 group-hover:opacity-100 group-hover:delay-inspection">
            <div className="z-raised relative space-y-4">
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={() => updateUserState({ watched: !watched })}
                  disabled={isMutating}
                  className={`focus-ring duration-standard inline-flex h-10 items-center gap-2 rounded-pill px-4 text-sm font-black tracking-wide uppercase transition-colors ${
                    watched
                      ? "bg-inverse text-inverse-ink group-hover:bg-neutral-200"
                      : "border border-ink/55 text-ink hover:border-ink hover:bg-inverse hover:text-inverse-ink"
                  } disabled:cursor-not-allowed disabled:opacity-60`}
                  aria-label={watched ? t("markUnwatched") : t("markWatched")}
                  title={watched ? t("markUnwatched") : t("markWatched")}
                >
                  {isMutating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
                  {watched ? t("watched") : t("markWatched")}
                </button>
                <button
                  type="button"
                  onClick={() => updateUserState({ favorite: !favorite })}
                  disabled={isMutating}
                  className={`focus-ring duration-standard flex h-8 w-8 items-center justify-center rounded-pill border transition-colors ${
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
          </div>
        </div>

        {/* Title & Info */}
        <Link href={`/library/${movie.id}`} scroll={false} onClick={handleMovieLinkClick} className="focus-ring duration-standard flex cursor-pointer items-start justify-between transition-opacity delay-0 peer-hover/card:pointer-events-none peer-hover/card:opacity-0 peer-hover/card:delay-inspection">
          <div className="space-y-1">
            <h3 className="text-xl leading-none font-bold tracking-tight uppercase md:text-2xl">
              {title}
            </h3>
            {metadataBadge && (
              <p className="text-[10px] font-black tracking-widest text-ink-subtle uppercase">
                {metadataBadge}
              </p>
            )}
          </div>
          <span className="font-serif text-xl text-ink-muted italic">
            {movie.year}
          </span>
        </Link>
      </div>
    </div>
  );
}
