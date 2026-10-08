"use client";

import { useSyncExternalStore } from "react";
import { readFilmReturn } from "@/lib/navigation-context";
import { ArrowLeft } from "lucide-react";
import { useParams, useRouter } from "next/navigation";
import { cn } from "@/lib/cn";

interface MovieDetailReturnProps {
  behavior: "history" | "library";
  label: string;
}

const controlClassName =
  "focus-ring duration-fast fixed z-sticky inline-flex min-h-11 max-w-[calc(100vw-2rem)] items-center gap-2 rounded-control border border-white/20 bg-black/70 px-4 type-label text-white backdrop-blur-md transition-colors hover:border-white/60 hover:bg-white hover:text-black";

const subscribe = () => () => {};

export default function MovieDetailReturn({ behavior, label }: MovieDetailReturnProps) {
  const router = useRouter();
  const params = useParams();
  const hydrated = useSyncExternalStore(subscribe, () => true, () => false);
  const fallback = params.locale === "en" ? "/en/library" : "/library";
  const href = useSyncExternalStore(subscribe, () => {
    const context = readFilmReturn();
    return context && context.filmId === params.id ? context.href : fallback;
  }, () => fallback);
  const className = cn(
    controlClassName,
    behavior === "history" ? "top-4 left-4 sm:top-6 sm:left-6" : "top-24 left-8",
  );
  const content = (
    <>
      <ArrowLeft aria-hidden="true" className="h-4 w-4 shrink-0" />
      <span className="truncate">{label}</span>
    </>
  );

  if (behavior === "history") {
    return (
      <button
        type="button"
        data-dialog-initial-focus=""
        className={className}
        onClick={() => router.back()}
        aria-label={label}
        title={label}
      >
        {content}
      </button>
    );
  }

  return (
    <button type="button" disabled={!hydrated} className={className} aria-label={label} title={label}
      onClick={() => {
        const context = readFilmReturn();
        router.push(context && context.filmId === params.id ? context.href : href, { scroll: false });
      }}>
      {content}
    </button>
  );
}
