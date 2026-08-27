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

function formatResolution(width?: number | null, height?: number | null) {
  return width && height ? `${width} × ${height}` : null;
}

function formatBitrate(value?: number | null) {
  if (!value) return null;
  return value >= 1_000_000 ? `${(value / 1_000_000).toFixed(1)} Mbps` : `${Math.round(value / 1000)} Kbps`;
}

function formatDuration(seconds?: number | null) {
  if (!seconds) return null;
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

export default async function MovieDetailView({ film }: { film: LibraryFilmDetail }) {
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
  const durationSeconds = video?.duration_seconds || (film.runtime_minutes ? film.runtime_minutes * 60 : null);
  const technicalItems = [
    { label: t("resolution"), value: formatResolution(video?.width, video?.height) },
    { label: t("dynamicRange"), value: video?.dynamic_range && video.dynamic_range !== "unknown" ? video.dynamic_range : null },
    { label: t("videoCodec"), value: video?.codec?.toUpperCase() },
    { label: t("bitrate"), value: formatBitrate(video?.bitrate) },
    { label: t("frameRate"), value: video?.fps ? `${video.fps} fps` : null },
    { label: t("bitDepth"), value: video?.bit_depth ? `${video.bit_depth}-bit` : null },
    { label: t("duration"), value: formatDuration(durationSeconds) },
    { label: t("fileSize"), value: formatFileSize(video?.file_size) },
  ].filter((item) => item.value);

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
          <MovieRefreshButton film={film} />
        </div>

        <div className="grid grid-cols-1 gap-12 border-b border-line-strong p-8 md:p-16 lg:grid-cols-3">
          <div className="space-y-8">
            <div className="space-y-3">
              <span className="type-label block text-ink-subtle">{t("microGenre")}</span>
              <span className="block font-serif text-lg text-ink italic">{film.micro_genre || t("pending")}</span>
            </div>
            {film.genres.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {film.genres.map((genre) => (
                  <span key={genre} className="rounded-pill border border-line px-3 py-1 type-meta text-ink-muted">{genre}</span>
                ))}
              </div>
            )}
          </div>
          <div className="lg:col-span-2">
            <p className="mb-12 text-xl leading-tight font-bold text-ink-muted md:mb-16 md:text-2xl lg:text-3xl">
              {film.overview || t("noDescription")}
            </p>
            {film.external_scores.length > 0 && (
              <div className="mb-12 md:mb-16">
                <span className="mb-5 block type-label text-ink-subtle">{t("externalReception")}</span>
                <ExternalScoreStrip scores={film.external_scores} />
              </div>
            )}
            <MovieArtworkPoster title={film.title} />
          </div>
        </div>

        {technicalItems.length > 0 && (
          <section className="border-b border-line-strong px-8 py-10 md:px-16">
            <span className="type-label block text-ink-subtle">{t("technicalDetails")}</span>
            <div className="mt-6 grid grid-cols-2 gap-x-8 gap-y-6 md:grid-cols-4">
              {technicalItems.map((item) => (
                <div key={item.label} className="min-w-0 space-y-1">
                  <span className="type-meta block text-ink-subtle">{item.label}</span>
                  <span className="block truncate text-base font-bold text-ink md:text-lg">{item.value}</span>
                </div>
              ))}
            </div>
          </section>
        )}

        <FilmGraphPanel filmId={film.id} />

        <section className="border-b border-line-strong px-8 py-10 md:px-16">
          <span className="type-label block text-ink-subtle">{t("editions")}</span>
          <div className="mt-6 grid gap-3 lg:grid-cols-2">
            {film.editions.map((edition, index) => (
              <div key={edition.id} className="flex min-w-0 items-center justify-between gap-4 border border-line p-4">
                <div className="min-w-0">
                  <p className="truncate font-bold text-ink">{editionLabel(edition, t("edition", { index: index + 1 }))}</p>
                  <p className="type-meta mt-1 truncate text-ink-subtle">{edition.video?.file_name || sourceLabel[edition.source_type] || edition.source_type}</p>
                </div>
                <div className="flex shrink-0 items-center gap-3">
                  <span className="rounded-pill border border-line px-3 py-1 type-badge text-ink-muted">{statusLabel[edition.status]}</span>
                  <LibraryEditionActions filmId={film.id} itemId={edition.id} />
                </div>
              </div>
            ))}
          </div>
        </section>

        <MovieAnalysisSection filmId={film.id} initialFilm={film} />
      </div>
    </MovieArtworkProvider>
  );
}
