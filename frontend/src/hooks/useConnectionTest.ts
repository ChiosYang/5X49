"use client";

import { useEffect, useRef, useState } from "react";

export type ConnectionOutcome = "success" | "error" | null;

export function useConnectionTest(test: () => Promise<{ status: string }>) {
  const version = useRef(0);
  const running = useRef(false);
  const mounted = useRef(true);
  const [state, setState] = useState<{ busy: boolean; outcome: ConnectionOutcome }>({ busy: false, outcome: null });
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; version.current += 1; };
  }, []);
  const invalidate = () => {
    version.current += 1;
    setState(previous => ({ ...previous, outcome: null }));
  };
  const run = async () => {
    if (running.current) return;
    running.current = true;
    const requested = ++version.current;
    setState({ busy: true, outcome: null });
    let outcome: ConnectionOutcome = "error";
    try { outcome = (await test()).status === "success" ? "success" : "error"; }
    catch { /* Only a localized generic result is exposed; responses may contain credentials. */ }
    finally {
      running.current = false;
      if (mounted.current) setState({ busy: false, outcome: requested === version.current ? outcome : null });
    }
  };
  return { ...state, invalidate, run };
}
