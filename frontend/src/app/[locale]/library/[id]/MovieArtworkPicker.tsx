"use client";

import { useState } from "react";
import Image from "next/image";
import { Check, ImageIcon, X } from "lucide-react";
import { useTranslations } from "next-intl";
import { useSWRConfig } from "swr";
import { Button, IconButton } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { InlineFeedback, Spinner } from "@/components/ui/Feedback";
import { API } from "@/lib/api";
import type { ArtworkImage, FilmArtworkOptions, FilmArtworkUpdateResponse } from "@/types/movie";
import { useMovieArtwork } from "./MovieArtworkProvider";

type ArtworkTab = "poster" | "backdrop";

interface MovieArtworkPickerProps {
  movieId: string;
}

const imageLabel = (image: ArtworkImage, noText: string, unknownSize: string) => {
  const language = image.language || noText;
  const size = image.width && image.height ? `${image.width}x${image.height}` : unknownSize;
  return `${language} - ${size}`;
};

export default function MovieArtworkPicker({ movieId }: MovieArtworkPickerProps) {
  const t = useTranslations("FilmDetail");
  const { mutate } = useSWRConfig();
  const { updateFromFilm } = useMovieArtwork();
  const [open, setOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<ArtworkTab>("poster");
  const [options, setOptions] = useState<FilmArtworkOptions | null>(null);
  const [selectedPoster, setSelectedPoster] = useState<string | null>(null);
  const [selectedBackdrop, setSelectedBackdrop] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");

  const loadArtwork = async () => {
    setLoading(true);
    setMessage("");
    try {
      const res = await fetch(API.filmArtwork(movieId));
      if (!res.ok) {
        const errorBody = await res.json().catch(() => null);
        throw new Error(errorBody?.detail || t("artworkLoadFailed"));
      }
      const data = (await res.json()) as FilmArtworkOptions;
      setOptions(data);
      setSelectedPoster(data.current_poster_path ?? null);
      setSelectedBackdrop(data.current_backdrop_path ?? null);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : t("artworkLoadFailed"));
    } finally {
      setLoading(false);
    }
  };

  const handleOpen = () => {
    setOpen(true);
    if (!options) {
      void loadArtwork();
    }
  };

  const handleSave = async () => {
    setSaving(true);
    setMessage("");
    try {
      const posterChanged = selectedPoster !== (options?.current_poster_path ?? null);
      const backdropChanged = selectedBackdrop !== (options?.current_backdrop_path ?? null);
      if (!posterChanged && !backdropChanged) {
        setMessage(t("chooseDifferentImage"));
        return;
      }

      const res = await fetch(API.filmArtwork(movieId), {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          poster_path: posterChanged ? selectedPoster : null,
          backdrop_path: backdropChanged ? selectedBackdrop : null,
        }),
      });
      if (!res.ok) {
        const errorBody = await res.json().catch(() => null);
        throw new Error(errorBody?.detail || t("artworkSaveFailed"));
      }

      const data = (await res.json()) as FilmArtworkUpdateResponse;
      updateFromFilm(data.film);
      await mutate(API.libraryFilm(movieId), data.film, false);
      setOptions(null);
      setOpen(false);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : t("artworkSaveFailed"));
    } finally {
      setSaving(false);
    }
  };

  const activeImages = activeTab === "poster" ? options?.posters : options?.backdrops;
  const activeSelection = activeTab === "poster" ? selectedPoster : selectedBackdrop;

  return (
    <>
      <IconButton
        onClick={handleOpen}
        aria-label={t("chooseArtwork")}
        title={t("chooseArtwork")}
        icon={<ImageIcon className="h-4 w-4" />}
      />

      <Dialog
        open={open}
        onClose={() => setOpen(false)}
        closeLabel={t("closeArtworkPicker")}
        closeOnBackdrop={false}
        closeOnEscape={false}
        lockScroll={false}
        size="xl"
        ariaLabelledBy="artwork-picker-title"
        panelClassName="flex max-h-[90vh] flex-col"
      >
            <div className="flex items-center justify-between border-b border-line-strong px-4 py-3 md:px-6">
              <div>
                <p className="type-label text-ink-subtle">{t("artwork")}</p>
                <p id="artwork-picker-title" className="text-lg font-bold tracking-widest text-ink uppercase">{t("chooseImages")}</p>
              </div>
              <IconButton
                onClick={() => setOpen(false)}
                variant="ghost"
                className="h-10 w-10"
                aria-label={t("closeArtworkPicker")}
                title={t("close")}
                icon={<X className="h-4 w-4" />}
              />
            </div>

            <div className="flex border-b border-line-strong bg-canvas/20 p-1">
              <button
                type="button"
                onClick={() => setActiveTab("poster")}
                className={`h-11 flex-1 rounded-sm border text-xs font-bold uppercase tracking-widest transition-colors ${
                  activeTab === "poster"
                    ? "border-ink/25 bg-ink/15 text-ink shadow-[inset_0_1px_0_rgba(255,255,255,0.08)]"
                    : "border-transparent text-ink-subtle hover:bg-ink/5 hover:text-ink-muted"
                }`}
              >
                {t("posters")}
              </button>
              <button
                type="button"
                onClick={() => setActiveTab("backdrop")}
                className={`h-11 flex-1 rounded-sm border text-xs font-bold uppercase tracking-widest transition-colors ${
                  activeTab === "backdrop"
                    ? "border-ink/25 bg-ink/15 text-ink shadow-[inset_0_1px_0_rgba(255,255,255,0.08)]"
                    : "border-transparent text-ink-subtle hover:bg-ink/5 hover:text-ink-muted"
                }`}
              >
                {t("backdrops")}
              </button>
            </div>

            <div className="min-h-0 flex-1 overflow-y-auto p-4 md:p-6">
              {loading && (
                <div className="flex h-64 items-center justify-center text-ink-subtle">
                  <Spinner className="h-6 w-6" />
                </div>
              )}

              {!loading && message && (
                <InlineFeedback tone="error" className="mb-4 font-bold tracking-widest uppercase">{message}</InlineFeedback>
              )}

              {!loading && options && (
                <div className={`grid gap-3 ${activeTab === "poster" ? "grid-cols-2 sm:grid-cols-3 md:grid-cols-5 lg:grid-cols-6" : "grid-cols-1 sm:grid-cols-2 lg:grid-cols-3"}`}>
                  {(activeImages ?? []).map((image) => {
                    const selected = image.file_path === activeSelection;
                    return (
                      <button
                        key={image.file_path}
                        type="button"
                        onClick={() => {
                          if (activeTab === "poster") {
                            setSelectedPoster(image.file_path);
                          } else {
                            setSelectedBackdrop(image.file_path);
                          }
                        }}
                        className={`group relative overflow-hidden border bg-surface text-left ${
                          selected ? "border-ink" : "border-line-strong hover:border-ink-disabled"
                        }`}
                      >
                        <Image
                          src={image.thumbnail_url}
                          alt={imageLabel(image, t("noText"), t("unknownSize"))}
                          width={image.width || 500}
                          height={image.height || (activeTab === "poster" ? 750 : 281)}
                          sizes={activeTab === "poster" ? "(min-width: 1024px) 16vw, 50vw" : "(min-width: 1024px) 33vw, 100vw"}
                          unoptimized
                          className={`w-full object-cover ${activeTab === "poster" ? "aspect-[2/3]" : "aspect-video"}`}
                        />
                        <span className="block border-t border-line-strong px-2 py-2 text-[10px] font-bold tracking-widest text-ink-muted uppercase">
                          {imageLabel(image, t("noText"), t("unknownSize"))}
                        </span>
                        {selected && (
                          <span className="absolute top-2 right-2 flex h-7 w-7 items-center justify-center bg-inverse text-inverse-ink">
                            <Check className="h-4 w-4" />
                          </span>
                        )}
                      </button>
                    );
                  })}
                </div>
              )}
            </div>

            <div className="flex items-center justify-end gap-3 border-t border-line-strong px-4 py-3 md:px-6">
              <Button
                onClick={() => setOpen(false)}
                className="h-10"
              >
                {t("cancel")}
              </Button>
              <Button
                onClick={handleSave}
                disabled={loading || saving || !options}
                busy={saving}
                variant="primary"
                className="h-10"
              >
                {t("save")}
              </Button>
            </div>
      </Dialog>
    </>
  );
}
