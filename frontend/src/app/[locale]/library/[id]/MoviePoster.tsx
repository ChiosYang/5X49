"use client";

import Image from "next/image";
import { motion } from "framer-motion";
import { useState } from "react";

interface MoviePosterProps {
  sources: string[];
  title: string;
}

export default function MoviePoster({ sources, title }: MoviePosterProps) {
  const [sourceIndex, setSourceIndex] = useState(0);
  const src = sources[sourceIndex];
  if (!src) return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 24 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-80px" }}
      transition={{ duration: 0.16, ease: "circOut" }}
      className="w-full"
    >
      <div className="w-full max-w-[19rem] overflow-hidden rounded-control border border-line bg-surface">
        <Image
          src={src}
          alt={`${title} Poster`}
          width={780}
          height={1170}
          sizes="(min-width: 1024px) 19rem, 70vw"
          unoptimized
          onError={() => setSourceIndex((current) => current + 1)}
          className="h-auto w-full object-cover"
        />
      </div>
    </motion.div>
  );
}
