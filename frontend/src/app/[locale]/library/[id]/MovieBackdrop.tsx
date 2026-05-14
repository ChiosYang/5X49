"use client";

import { useState } from "react";
import Image from "next/image";

interface MovieBackdropProps {
  src: string | null;
  title: string;
}

export default function MovieBackdrop({ src, title }: MovieBackdropProps) {
  const [loadedSrc, setLoadedSrc] = useState<string | null>(null);
  const loaded = !!src && loadedSrc === src;

  return (
    <div className="absolute inset-0">
      <div className="absolute inset-0 bg-neutral-950" />
      {src && (
        <div className="absolute inset-0">
          <Image
            src={src}
            alt={title}
            fill
            priority
            sizes="100vw"
            unoptimized
            onLoad={() => setLoadedSrc(src)}
            className={`object-cover transition-opacity duration-150 ease-out ${loaded ? "opacity-100" : "opacity-0"}`}
          />
        </div>
      )}
      <div className="absolute inset-0 bg-gradient-to-t from-black via-black/20 to-transparent" />
    </div>
  );
}
