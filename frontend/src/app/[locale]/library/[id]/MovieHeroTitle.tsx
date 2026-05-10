"use client";

import { motion } from "framer-motion";

interface MovieHeroTitleProps {
  title: string;
  titleCn?: string;
}

export default function MovieHeroTitle({ title, titleCn }: MovieHeroTitleProps) {
  return (
    <div className="absolute bottom-0 left-0 p-8 md:p-16 w-full z-40">
      <motion.h1
        initial={{ y: 100, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ duration: 0.18, ease: "circOut" }}
        className="text-6xl md:text-8xl lg:text-9xl font-bold uppercase tracking-tighter leading-none mb-6"
      >
        {titleCn || title}
      </motion.h1>
      {titleCn && (
        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.04, duration: 0.14 }}
          className="text-2xl md:text-3xl font-serif italic text-neutral-400"
        >
          {title}
        </motion.p>
      )}
    </div>
  );
}
