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
  "focus-ring duration-fast absolute z-navigation inline-flex h-11 w-11 items-center justify-center rounded-full text-white/85 drop-shadow-[0_1px_8px_rgba(0,0,0,0.85)] transition-[color,transform] hover:-translate-x-0.5 hover:text-white";

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
    behavior === "history" ? "top-4 left-3 sm:top-6 sm:left-5" : "top-24 left-5",
  );
  const content = <ArrowLeft aria-hidden="true" className="h-5 w-5 shrink-0" />;

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
