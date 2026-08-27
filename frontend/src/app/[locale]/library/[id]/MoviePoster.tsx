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
      initial={{ opacity: 0, y: 40 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-100px" }}
      transition={{ duration: 0.16, ease: "circOut" }}
      className="w-full flex justify-start"
    >
      <div className="w-full md:w-[37.5%]">
        <Image
          src={src}
          alt={`${title} Poster`}
          width={780}
          height={1170}
          sizes="(min-width: 768px) 37.5vw, 100vw"
          unoptimized
          onError={() => setSourceIndex((current) => current + 1)}
          className="w-full h-auto object-cover"
        />
      </div>
    </motion.div>
  );
}
