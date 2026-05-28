"use client";

import { useState } from "react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { Check, ImageIcon, Loader2, X } from "lucide-react";
import { API } from "@/lib/api";
import type { ArtworkImage, MovieArtworkOptions } from "@/types/movie";

type ArtworkTab = "poster" | "backdrop";

interface MovieArtworkPickerProps {
  movieId: string;
}

const imageLabel = (image: ArtworkImage) => {
  const language = image.language || "No text";
  const size = image.width && image.height ? `${image.width}x${image.height}` : "Unknown size";
  return `${language} - ${size}`;
};

export default function MovieArtworkPicker({ movieId }: MovieArtworkPickerProps) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<ArtworkTab>("poster");
  const [options, setOptions] = useState<MovieArtworkOptions | null>(null);
  const [selectedPoster, setSelectedPoster] = useState<string | null>(null);
  const [selectedBackdrop, setSelectedBackdrop] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");

  const loadArtwork = async () => {
    setLoading(true);
    setMessage("");
    try {
      const res = await fetch(API.libraryArtwork(movieId));
      if (!res.ok) {
        const errorBody = await res.json().catch(() => null);
        throw new Error(errorBody?.detail || "Failed to load artwork");
      }
      const data = (await res.json()) as MovieArtworkOptions;
      setOptions(data);
      setSelectedPoster(data.current_poster_path ?? null);
      setSelectedBackdrop(data.current_backdrop_path ?? null);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Failed to load artwork");
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
        setMessage("Choose a different image");
        return;
      }

      const res = await fetch(API.libraryArtwork(movieId), {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          poster_path: posterChanged ? selectedPoster : null,
          backdrop_path: backdropChanged ? selectedBackdrop : null,
        }),
      });
      if (!res.ok) {
        const errorBody = await res.json().catch(() => null);
        throw new Error(errorBody?.detail || "Failed to save artwork");
      }

      setOptions(null);
      setOpen(false);
      router.refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Failed to save artwork");
    } finally {
      setSaving(false);
    }
  };

  const activeImages = activeTab === "poster" ? options?.posters : options?.backdrops;
  const activeSelection = activeTab === "poster" ? selectedPoster : selectedBackdrop;

  return (
    <>
      <button
        type="button"
        onClick={handleOpen}
        className="flex h-11 w-11 items-center justify-center border border-neutral-800 bg-neutral-950 text-white hover:border-neutral-500 hover:bg-neutral-900 disabled:cursor-not-allowed disabled:opacity-50"
        aria-label="Choose artwork"
        title="Choose artwork"
      >
        <ImageIcon className="h-4 w-4" />
      </button>

      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="liquid-glass-modal relative flex max-h-[90vh] w-full max-w-6xl flex-col overflow-hidden border border-neutral-900/80 text-white">
            <div className="flex items-center justify-between border-b border-neutral-800 px-4 py-3 md:px-6">
              <div>
                <p className="text-xs font-bold uppercase tracking-widest text-neutral-500">Artwork</p>
                <p className="text-lg font-bold uppercase tracking-widest">Choose Images</p>
              </div>
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="flex h-10 w-10 items-center justify-center border border-neutral-800 bg-neutral-950 text-white hover:border-neutral-500"
                aria-label="Close artwork picker"
                title="Close"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="flex border-b border-neutral-800">
              <button
                type="button"
                onClick={() => setActiveTab("poster")}
                className={`h-12 flex-1 border-r border-neutral-800 text-xs font-bold uppercase tracking-widest ${
                  activeTab === "poster" ? "bg-white text-black" : "bg-black text-neutral-400 hover:text-white"
                }`}
              >
                Posters
              </button>
              <button
                type="button"
                onClick={() => setActiveTab("backdrop")}
                className={`h-12 flex-1 text-xs font-bold uppercase tracking-widest ${
                  activeTab === "backdrop" ? "bg-white text-black" : "bg-black text-neutral-400 hover:text-white"
                }`}
              >
                Backdrops
              </button>
            </div>

            <div className="min-h-0 flex-1 overflow-y-auto p-4 md:p-6">
              {loading && (
                <div className="flex h-64 items-center justify-center text-neutral-500">
                  <Loader2 className="h-6 w-6 animate-spin" />
                </div>
              )}

              {!loading && message && (
                <p className="mb-4 text-sm font-bold uppercase tracking-widest text-red-500">{message}</p>
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
                        className={`group relative overflow-hidden border bg-neutral-950 text-left ${
                          selected ? "border-white" : "border-neutral-800 hover:border-neutral-500"
                        }`}
                      >
                        <Image
                          src={image.thumbnail_url}
                          alt={imageLabel(image)}
                          width={image.width || 500}
                          height={image.height || (activeTab === "poster" ? 750 : 281)}
                          sizes={activeTab === "poster" ? "(min-width: 1024px) 16vw, 50vw" : "(min-width: 1024px) 33vw, 100vw"}
                          unoptimized
                          className={`w-full object-cover ${activeTab === "poster" ? "aspect-[2/3]" : "aspect-video"}`}
                        />
                        <span className="block border-t border-neutral-800 px-2 py-2 text-[10px] font-bold uppercase tracking-widest text-neutral-400">
                          {imageLabel(image)}
                        </span>
                        {selected && (
                          <span className="absolute right-2 top-2 flex h-7 w-7 items-center justify-center bg-white text-black">
                            <Check className="h-4 w-4" />
                          </span>
                        )}
                      </button>
                    );
                  })}
                </div>
              )}
            </div>

            <div className="flex items-center justify-end gap-3 border-t border-neutral-800 px-4 py-3 md:px-6">
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="h-10 border border-neutral-800 px-4 text-xs font-bold uppercase tracking-widest text-neutral-400 hover:border-neutral-500 hover:text-white"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleSave}
                disabled={loading || saving || !options}
                className="flex h-10 items-center gap-2 bg-white px-4 text-xs font-bold uppercase tracking-widest text-black disabled:cursor-not-allowed disabled:opacity-50"
              >
                {saving && <Loader2 className="h-4 w-4 animate-spin" />}
                Save
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
