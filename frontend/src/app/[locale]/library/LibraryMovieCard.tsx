"use client";

import Image from "next/image";
import { useState } from "react";
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

  return (
    <div className="block">
      <div className="space-y-4">
        {/* Landscape Still */}
        <div className="peer/card group relative z-0 aspect-video w-full bg-neutral-900 hover:z-30">
          <Link href={`/library/${movie.id}`} className="block h-full cursor-pointer">
            <div className="relative h-full w-full overflow-hidden rounded-md">
              {backdropSrc ? (
                <Image
                  src={backdropSrc!}
                  alt={movie.title}
                  fill
                  priority={priority}
                  sizes="(min-width: 1536px) 20vw, (min-width: 1280px) 25vw, (min-width: 1024px) 33vw, (min-width: 640px) 50vw, 100vw"
                  className="object-cover transition-transform delay-0 duration-200 ease-out group-hover:scale-[1.05] group-hover:delay-500"
                />
              ) : (
                <div className="flex h-full w-full items-center justify-center border border-neutral-800 transition-transform delay-0 duration-200 ease-out group-hover:scale-[1.05] group-hover:delay-500">
                  <span className="font-serif text-4xl text-neutral-800">?</span>
                </div>
              )}
              {metadataBadge && (
                <span className="absolute left-3 top-3 z-10 rounded-sm bg-black/80 px-2 py-1 text-[10px] font-black uppercase tracking-widest text-white">
                  {metadataBadge}
                </span>
              )}
              {watched && (
                <span className="absolute right-3 top-3 z-10 text-white drop-shadow-[0_1px_4px_rgba(0,0,0,0.9)]">
                  <Check className="h-5 w-5 stroke-[3]" aria-label={t("watched")} />
                </span>
              )}
              {/* Hover Overlay */}
              <div className="absolute inset-0 bg-black/0 transition-colors delay-0 duration-200 group-hover:bg-black/35 group-hover:delay-500" />
              <div className="invisible absolute inset-x-0 bottom-0 flex translate-y-1 flex-col gap-1 bg-gradient-to-t from-black/80 via-black/35 to-transparent px-5 pb-4 pt-12 opacity-0 transition-[opacity,transform] delay-0 duration-200 group-hover:visible group-hover:translate-y-0 group-hover:opacity-100 group-hover:delay-500">
                <h3 className="line-clamp-1 text-2xl font-black uppercase leading-none text-white">
                  {title}
                </h3>
                <p className="line-clamp-1 text-xs font-bold uppercase tracking-wide text-white">
                  {movie.director || movie.title} {movie.year}
                </p>
              </div>
            </div>
          </Link>

          <div className="liquid-glass-popover invisible absolute left-0 right-0 top-full z-20 origin-top translate-y-1 scale-95 overflow-hidden rounded-b-md border border-neutral-900/80 p-5 text-white opacity-0 transition-[opacity,transform] delay-0 duration-200 ease-out group-hover:visible group-hover:translate-y-0 group-hover:scale-100 group-hover:opacity-100 group-hover:delay-500">
            <div className="relative z-10 space-y-4">
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={() => updateUserState({ watched: !watched })}
                  disabled={isMutating}
                  className={`inline-flex h-10 items-center gap-2 rounded-full px-4 text-sm font-black uppercase tracking-wide transition-colors ${
                    watched
                      ? "bg-white text-black group-hover:bg-neutral-200"
                      : "border border-white/55 text-white hover:border-white hover:bg-white hover:text-black"
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
                  className={`flex h-8 w-8 items-center justify-center rounded-full border transition-colors ${
                    favorite
                      ? "border-white bg-white text-black"
                      : "border-white/55 text-white hover:border-white"
                  } disabled:cursor-not-allowed disabled:opacity-60`}
                  aria-label={favorite ? t("unfavorite") : t("favorite")}
                  title={favorite ? t("unfavorite") : t("favorite")}
                >
                  <Star className={`h-4 w-4 ${favorite ? "fill-current" : ""}`} />
                </button>
              </div>

              <p className="overflow-hidden text-[15px] leading-snug text-neutral-300 [display:-webkit-box] [-webkit-box-orient:vertical] [-webkit-line-clamp:4]">
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
                          ? "inline-flex h-5 items-center text-neutral-200"
                          : badge.variant === "solid"
                          ? "inline-flex h-5 items-center rounded-[4px] border border-white/60 bg-neutral-200 px-1.5 text-[10px] font-black uppercase leading-none text-neutral-700 shadow-[inset_0_1px_0_rgba(255,255,255,0.8),0_1px_6px_rgba(255,255,255,0.08)]"
                          : "inline-flex h-5 items-center rounded-[4px] border border-white/35 bg-white/[0.06] px-1.5 text-[10px] font-black uppercase leading-none text-neutral-200 shadow-[inset_0_1px_0_rgba(255,255,255,0.14)]"
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
                          ? "inline-flex h-5 items-center gap-1 text-neutral-300"
                          : "inline-flex h-5 items-center gap-1 rounded-[4px] border border-white/35 bg-white/[0.06] px-1.5 text-[10px] font-black uppercase leading-none text-neutral-200 shadow-[inset_0_1px_0_rgba(255,255,255,0.14)]"
                      }
                      title={movie.countries?.join(", ")}
                      aria-label={movie.countries?.join(", ")}
                    >
                      {countryFlag ? (
                        <span className="text-base leading-none">{countryFlag}</span>
                      ) : (
                        <>
                          <Globe2 className="h-3.5 w-3.5 text-neutral-500" />
                          <span className="max-w-20 truncate">{country}</span>
                        </>
                      )}
                      {extraCountryCount > 0 && (
                        <span className="text-xs font-bold text-neutral-400">+{extraCountryCount}</span>
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
                      className="max-w-full truncate rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-[10px] font-black uppercase tracking-widest text-neutral-300"
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
        <Link href={`/library/${movie.id}`} className="flex cursor-pointer items-start justify-between transition-opacity delay-0 duration-200 peer-hover/card:pointer-events-none peer-hover/card:opacity-0 peer-hover/card:delay-500">
          <div className="space-y-1">
            <h3 className="text-xl md:text-2xl font-bold uppercase leading-none tracking-tight">
              {title}
            </h3>
            {metadataBadge && (
              <p className="text-[10px] font-black uppercase tracking-widest text-neutral-500">
                {metadataBadge}
              </p>
            )}
          </div>
          <span className="font-serif text-xl italic text-neutral-400">
            {movie.year}
          </span>
        </Link>
      </div>
    </div>
  );
}
