import { getTranslations } from "next-intl/server";

import type { LibraryEdition, LibraryFilmDetail } from "@/types/movie";
import ExternalScoreStrip from "../../components/ExternalScoreStrip";
import FilmGraphPanel from "./FilmGraphPanel";
import LibraryEditionActions from "./LibraryEditionActions";
import MovieAnalysisSection from "./MovieAnalysisSection";
import {
  MovieArtworkBackdrop,
  MovieArtworkPoster,
  MovieArtworkProvider,
} from "./MovieArtworkProvider";
import MovieHeroTitle from "./MovieHeroTitle";
import MovieRefreshButton from "./MovieRefreshButton";
import MovieViewingSection from "./MovieViewingSection";
import FilmPersonalState from "@/components/FilmPersonalState";
import FilmMetadataEditor from "@/components/FilmMetadataEditor";

function formatResolution(width?: number | null, height?: number | null) {
  return width && height ? `${width} × ${height}` : null;
}

function formatResolutionTier(width?: number | null, height?: number | null) {
  if (!width && !height) return null;
  const w = width || 0;
  const h = height || 0;
  if (w >= 3800 || h >= 2100) return "4K UHD";
  if (w >= 2500 || h >= 1400) return "2K QHD";
  if (w >= 1900 || h >= 1000) return "1080p HD";
  if (w >= 1200 || h >= 700) return "720p HD";
  return "SD";
}

function formatAspectRatio(width?: number | null, height?: number | null) {
  if (!width || !height) return null;
  return `${(width / height).toFixed(2)}:1`;
}

function formatBitrate(value?: number | null) {
  if (!value) return null;
  return value >= 1_000_000 ? `${(value / 1_000_000).toFixed(1)} Mbps` : `${Math.round(value / 1000)} Kbps`;
}

function formatDuration(seconds?: number | null) {
  if (!seconds) return null;
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const totalMinutes = Math.round(seconds / 60);
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  return hours ? `${hours}h ${minutes}m` : `${minutes}m`;
}

function formatFileSize(bytes?: number | null) {
  if (!bytes) return null;
  return bytes >= 1024 ** 3 ? `${(bytes / 1024 ** 3).toFixed(2)} GB` : `${(bytes / 1024 ** 2).toFixed(1)} MB`;
}

function editionLabel(edition: LibraryEdition, fallback: string) {
  return edition.display_name || fallback;
}

export default async function MovieDetailView({ film, routeFilmId }: { film: LibraryFilmDetail; routeFilmId: string }) {
  const t = await getTranslations("FilmDetail");
  const statusLabel = {
    available: t("editionAvailable"),
    missing: t("editionMissing"),
    ignored: t("editionIgnoredStatus"),
  };
  const sourceLabel: Record<string, string> = {
    local_folder: t("sourceLocalFolder"),
    local_nfo: t("sourceLocalNfo"),
  };
  const primary = film.primary_item;
  const video = primary.video;
  const resolution = formatResolution(video?.width, video?.height);
  const resolutionSubline = [
    formatResolutionTier(video?.width, video?.height),
    formatAspectRatio(video?.width, video?.height),
  ]
    .filter(Boolean)
    .join(" · ");
  const durationSeconds =
    (video?.duration_seconds && video.duration_seconds >= 60 ? video.duration_seconds : null) ||
    (film.runtime_minutes ? film.runtime_minutes * 60 : video?.duration_seconds || null);
  const specPills = [
    { label: t("dynamicRange"), value: video?.dynamic_range && video.dynamic_range !== "unknown" ? video.dynamic_range : null },
    { label: t("videoCodec"), value: video?.codec?.toUpperCase() || null },
    { label: t("bitDepth"), value: video?.bit_depth ? `${video.bit_depth}-bit` : null },
    { label: t("frameRate"), value: video?.fps ? `${video.fps} fps` : null },
  ].filter((item): item is { label: string; value: string } => Boolean(item.value));
  const metricItems = [
    { label: t("bitrate"), value: formatBitrate(video?.bitrate) },
    { label: t("duration"), value: formatDuration(durationSeconds) },
    { label: t("fileSize"), value: formatFileSize(video?.file_size) },
  ].filter((item): item is { label: string; value: string } => Boolean(item.value));
  const hasTechnicalDetails = Boolean(resolution || specPills.length > 0 || metricItems.length > 0);

  const archiveSummary = [
    resolution,
    video?.codec?.toUpperCase(),
    formatBitrate(video?.bitrate),
    video?.fps ? `${video.fps} fps` : null,
    t("editionsSummary", { count: film.editions.length }),
  ]
    .filter(Boolean)
    .join(" · ");

  const microGenreLabel = film.micro_genre || t("pending");
  const microGenreHasCjk = /[\u3000-\u9fff\uf900-\ufaff]/.test(microGenreLabel);

  const technicalDetails = hasTechnicalDetails ? (
    <div>
      <span className="type-label block text-ink-subtle">{t("technicalDetails")}</span>
      {resolution ? (
        <div className="mt-3">
          <p className="font-mono text-2xl font-light tracking-tight tabular-nums text-ink sm:text-3xl">{resolution}</p>
          {resolutionSubline ? (
            <p className="mt-1.5 font-mono text-xs tracking-wider tabular-nums text-ink-subtle">{resolutionSubline}</p>
          ) : null}
        </div>
      ) : null}
      {specPills.length > 0 ? (
        <div className="mt-4 flex flex-wrap gap-1.5">
          {specPills.map((pill) => (
            <span
              key={pill.label}
              title={pill.label}
              className="rounded-pill border border-line-strong px-2.5 py-1 font-mono text-[11px] tracking-wider tabular-nums text-ink-muted"
            >
              {pill.value}
            </span>
          ))}
        </div>
      ) : null}
      {metricItems.length > 0 ? (
        <dl className={`grid grid-cols-3 gap-3 ${resolution || specPills.length > 0 ? "mt-6 border-t border-line pt-4" : "mt-4"}`}>
          {metricItems.map((item) => (
            <div key={item.label} className="min-w-0">
              <dt className="type-meta text-ink-subtle">{item.label}</dt>
              <dd className="mt-1 truncate font-mono text-sm tabular-nums text-ink">{item.value}</dd>
            </div>
          ))}
        </dl>
      ) : null}
    </div>
  ) : undefined;

  const editionsDetails = (
    <div>
      <span className="type-label block text-ink-subtle">{t("editions")}</span>
      <div className="mt-4 grid gap-3">
        {film.editions.map((edition, index) => (
          <div key={edition.id} className="flex min-w-0 flex-col items-start justify-between gap-4 border border-line bg-white/[0.015] p-4 sm:flex-row sm:items-center">
            <div className="min-w-0 max-w-full sm:flex-1">
              <p className="truncate font-semibold text-ink">{editionLabel(edition, t("edition", { index: index + 1 }))}</p>
              <p className="type-meta mt-1 truncate font-mono text-ink-subtle">{edition.video?.file_name || sourceLabel[edition.source_type] || edition.source_type}</p>
              {(edition.video?.part_files?.length || 0) > 1 && <p className="type-meta mt-1 break-words text-ink-subtle">{t("splitParts", {count: edition.video!.part_files!.length})}</p>}
            </div>
            <div className="flex shrink-0 items-center gap-3">
              <span className="rounded-pill border border-line px-3 py-1 type-badge text-ink-muted">{statusLabel[edition.status]}</span>
              <LibraryEditionActions filmId={film.id} itemId={edition.id} primary={edition.id === film.primary_item.id} available={edition.status === "available"} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );

  return (
    <MovieArtworkProvider initialFilm={film}>
      <div className="min-h-screen bg-canvas text-ink selection:bg-inverse selection:text-inverse-ink">
        <div className="relative h-screen w-full overflow-hidden">
          <MovieArtworkBackdrop title={film.title} />
          <MovieHeroTitle title={film.original_title || film.title} titleCn={film.title} />
        </div>

        <div className="grid grid-cols-1 divide-y divide-line-strong border-t border-line-strong bg-canvas text-ink-muted md:grid-cols-3 md:divide-x md:divide-y-0">
          <div className="space-y-2 p-8 md:px-16">
            <span className="type-label block text-ink-subtle">{t("directedBy")}</span>
            <span className="block text-xl font-bold text-ink uppercase md:text-2xl">{film.directors[0] || "—"}</span>
          </div>
          <div className="space-y-2 p-8 md:px-16">
            <span className="type-label block text-ink-subtle">{t("released")}</span>
            <span className="block font-serif text-xl text-ink italic md:text-2xl">{film.year || "—"}</span>
          </div>
          {/* RSC can resolve this URL to a different canonical Film during a write. */}
          <MovieRefreshButton
            key={routeFilmId}
            film={film}
          />
        </div>

        <div className="grid grid-cols-1 gap-10 border-b border-line-strong p-8 md:p-16 lg:grid-cols-[minmax(0,19rem)_minmax(0,1fr)] lg:gap-16">
          <div className="space-y-7">
            <MovieArtworkPoster title={film.title} />
            <div className="space-y-3">
              <span className="type-label block text-ink-subtle">{t("microGenre")}</span>
              <span className={`block text-lg text-ink ${microGenreHasCjk ? "font-normal" : "font-serif italic"}`}>
                {microGenreLabel}
              </span>
            </div>
            {film.genres.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {film.genres.map((genre) => (
                  <span key={genre} className="rounded-pill border border-line px-3 py-1 type-meta text-ink-muted">{genre}</span>
                ))}
              </div>
            )}
          </div>
          <div className="min-w-0 space-y-12 md:space-y-14">
            <p className="max-w-3xl text-xl leading-snug font-bold text-ink-muted md:text-2xl lg:text-3xl">
              {film.overview || t("noDescription")}
            </p>
            {film.external_scores.length > 0 && (
              <div>
                <span className="mb-5 block type-label text-ink-subtle">{t("externalReception")}</span>
                <ExternalScoreStrip scores={film.external_scores} />
              </div>
            )}
          </div>
        </div>

        <section className="border-b border-line-strong px-8 py-10 md:px-16 lg:py-12">
          <div className="grid grid-cols-1 gap-10 lg:grid-cols-[minmax(0,22rem)_minmax(0,1fr)] lg:gap-12">
            <FilmPersonalState filmId={film.id} initialState={film.profile_state} embedded />
            <MovieViewingSection filmId={film.id} filmTitle={film.title} embedded />
          </div>
        </section>

        <MovieAnalysisSection filmId={film.id} initialFilm={film} />

        <FilmGraphPanel filmId={film.id} />

        <FilmMetadataEditor
          key={film.id}
          filmId={film.id}
          archiveSummary={archiveSummary}
          defaultExpanded={film.editions.length > 1}
          technicalDetails={technicalDetails}
          editionsDetails={editionsDetails}
        />
      </div>
    </MovieArtworkProvider>
  );
}
