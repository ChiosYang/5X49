"use client";

import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import {
  FIRST_RUN_INTRO_SESSION_KEY,
  shouldPlayFirstRunIntro,
} from "@/lib/library-onboarding";

const INTRO_DURATION_SECONDS = 1.3;
const INTRO_STATE_ATTRIBUTE = "data-first-run-intro-state";
const INTRO_BOOTSTRAP_ATTRIBUTE = "data-first-run-intro-bootstrap";
const INTRO_BOOTSTRAP_SCRIPT = `(() => {
  const root = document.documentElement;
  let hasPlayed = false;
  let reducedMotion = false;
  try {
    hasPlayed = window.sessionStorage.getItem("${FIRST_RUN_INTRO_SESSION_KEY}") === "1";
  } catch {}
  try {
    reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  } catch {}
  const shouldPlay = !hasPlayed && !reducedMotion;
  if (!hasPlayed) {
    try {
      window.sessionStorage.setItem("${FIRST_RUN_INTRO_SESSION_KEY}", "1");
    } catch {}
  }
  root.setAttribute("${INTRO_STATE_ATTRIBUTE}", shouldPlay ? "play" : "skip");
})();`;

export default function FirstRunIntro() {
  const reducedMotion = useReducedMotion();
  const [visible, setVisible] = useState(true);
  const overlayRef = useRef<HTMLDivElement>(null);
  const playing = useRef(false);

  useEffect(() => {
    if (playing.current) return;

    const root = document.documentElement;
    const bootstrapState = root.getAttribute(INTRO_STATE_ATTRIBUTE);
    let hasPlayed = false;

    try {
      hasPlayed = window.sessionStorage.getItem(FIRST_RUN_INTRO_SESSION_KEY) === "1";
    } catch {
      // The intro remains a safe progressive enhancement when storage is unavailable.
    }

    const shouldPlay =
      bootstrapState === "play" ||
      (bootstrapState === null &&
        shouldPlayFirstRunIntro({
          hasPlayed,
          reducedMotion: Boolean(reducedMotion),
        }));

    if (!hasPlayed) {
      try {
        window.sessionStorage.setItem(FIRST_RUN_INTRO_SESSION_KEY, "1");
      } catch {
        // A blocked storage write must never prevent onboarding from rendering.
      }
    }

    root.setAttribute(INTRO_STATE_ATTRIBUTE, "skip");

    if (shouldPlay) {
      playing.current = true;
      overlayRef.current?.removeAttribute(INTRO_BOOTSTRAP_ATTRIBUTE);
      return;
    }

    const animationFrame = window.requestAnimationFrame(() => setVisible(false));
    return () => window.cancelAnimationFrame(animationFrame);
  }, [reducedMotion]);

  return (
    <>
      <script
        data-first-run-intro-bootstrap-script
        dangerouslySetInnerHTML={{ __html: INTRO_BOOTSTRAP_SCRIPT }}
      />
      <AnimatePresence>
        {visible ? (
          <motion.div
            ref={overlayRef}
            data-first-run-intro
            data-first-run-intro-bootstrap
            aria-hidden="true"
            className="z-modal pointer-events-none fixed inset-0 overflow-hidden"
            initial={{ opacity: 1 }}
            animate={{ opacity: [1, 1, 1, 0] }}
            transition={{
              duration: INTRO_DURATION_SECONDS,
              times: [0, 0.08, 0.78, 1],
              ease: "linear",
            }}
            onAnimationComplete={() => setVisible(false)}
          >
            <motion.div
              className="absolute inset-0 bg-canvas"
              initial={{ opacity: 1 }}
              animate={{ opacity: [1, 1, 0] }}
              transition={{
                duration: INTRO_DURATION_SECONDS,
                times: [0, 0.58, 1],
                ease: "linear",
              }}
            />

            <motion.div
              className="absolute inset-x-0 top-0 h-1/2 border-b border-white/10 bg-canvas"
              initial={{ y: "0%" }}
              animate={{ y: "-102%" }}
              transition={{ delay: 0.75, duration: 0.55, ease: [0.4, 0, 1, 1] }}
            />
            <motion.div
              className="absolute inset-x-0 bottom-0 h-1/2 border-t border-white/10 bg-canvas"
              initial={{ y: "0%" }}
              animate={{ y: "102%" }}
              transition={{ delay: 0.75, duration: 0.55, ease: [0.4, 0, 1, 1] }}
            />

            <div className="glass-surface absolute inset-0 opacity-40" />
            <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(255,255,255,0.08),transparent_52%)]" />

            <motion.div
              className="absolute inset-0 flex items-center justify-center"
              initial={{ scale: 0.94 }}
              animate={{
                scale: [0.94, 1, 1.015, 1.02],
              }}
              transition={{
                delay: 0.15,
                duration: 0.8,
                times: [0, 0.38, 0.72, 1],
                ease: [0.2, 0, 0, 1],
              }}
            >
              <motion.span
                className="absolute font-serif text-5xl font-bold tracking-[-0.08em] text-ink blur-md md:text-8xl"
                initial={{ opacity: 0 }}
                animate={{ opacity: [0, 0.75, 0] }}
                transition={{ duration: 0.4, times: [0, 0.45, 1], ease: "easeOut" }}
              >
                5X49
              </motion.span>
              <motion.span
                className="font-serif text-5xl font-bold tracking-[-0.08em] text-ink md:text-8xl"
                initial={{ opacity: 0 }}
                animate={{ opacity: [0, 1, 1, 0] }}
                transition={{ duration: 0.8, times: [0, 0.38, 0.72, 1], ease: "easeOut" }}
              >
                5X49
              </motion.span>
            </motion.div>

            <motion.div
              className="absolute inset-y-0 left-0 w-[18vw] min-w-24 bg-gradient-to-r from-transparent via-white/20 to-transparent blur-xl"
              initial={{ x: "-30vw", opacity: 0 }}
              animate={{ x: "115vw", opacity: [0, 0.85, 0.85, 0] }}
              transition={{
                delay: 0.35,
                duration: 0.5,
                times: [0, 0.15, 0.8, 1],
                ease: "linear",
              }}
            />
            <motion.div
              className="absolute top-1/2 right-0 left-0 h-px bg-white/35 shadow-[0_0_22px_rgba(255,255,255,0.45)]"
              initial={{ scaleX: 0, opacity: 0 }}
              animate={{ scaleX: [0, 1, 1, 0], opacity: [0, 1, 1, 0] }}
              transition={{ delay: 0.25, duration: 0.72, times: [0, 0.2, 0.75, 1] }}
            />
          </motion.div>
        ) : null}
      </AnimatePresence>
    </>
  );
}
