"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { Terminal, X, Play, Loader2 } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

interface LogMessage {
  id: string;
  type: "info" | "thought" | "tool_execution" | "done" | "error";
  message?: string;
  tool_name?: string;
  content?: string;
  timestamp: string;
}

interface LibrarianTerminalProps {
  isOpen: boolean;
  onClose: () => void;
}

export default function LibrarianTerminal({ isOpen, onClose }: LibrarianTerminalProps) {
  const [logs, setLogs] = useState<LogMessage[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const eventSourceRef = useRef<EventSource | null>(null);

  const closeAgentConnection = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
  }, []);

  const stopAgent = useCallback(() => {
    closeAgentConnection();
    setIsRunning(false);
  }, [closeAgentConnection]);

  const handleClose = () => {
    stopAgent();
    onClose();
  };

  // Auto-scroll to bottom
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [logs]);

  // Cleanup on unmount or close
  useEffect(() => {
    if (!isOpen) {
      closeAgentConnection();
    }
    return () => closeAgentConnection();
  }, [isOpen, closeAgentConnection]);

  const startCleaning = () => {
    setLogs([]);
    setIsRunning(true);

    const es = new EventSource('/api/api/agents/clean-inbox');
    eventSourceRef.current = es;

    es.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        
        const now = new Date().toLocaleTimeString('en-US', { 
            hour12: false, 
            hour: "numeric", 
            minute: "numeric", 
            second: "numeric" 
        });

        const newLog: LogMessage = {
          id: Math.random().toString(36).substring(7),
          type: data.type,
          timestamp: now,
          message: data.message,
          tool_name: data.tool_name,
          content: data.content
        };

        setLogs((prev) => [...prev, newLog]);

        if (data.type === "done" || data.type === "error") {
          setIsRunning(false);
          es.close();
        }
      } catch (err) {
        console.error("Failed to parse SSE message", err);
      }
    };

    es.onerror = (err) => {
      console.error("SSE Error:", err);
      setIsRunning(false);
      es.close();
      setLogs((prev) => [
        ...prev,
        {
          id: Math.random().toString(),
          type: "error",
          timestamp: new Date().toLocaleTimeString(),
          message: "Connection lost to Librarian Agent."
        }
      ]);
    };
  };

  const renderLog = (log: LogMessage) => {
    switch (log.type) {
      case "info":
        return <div className="break-words text-ink-subtle">[{log.timestamp}] [SYSTEM] {log.message}</div>;
      case "thought":
        return <div className="break-words text-ink">[{log.timestamp}] [REASONING] {log.message}</div>;
      case "tool_execution":
        return (
          <div className="my-4 break-words border border-line-strong bg-surface p-4 text-ink-muted">
            <div>[{log.timestamp}] [SYSTEM_CALL: {log.tool_name}]</div>
            <div className="scrollbar-minimal mt-2 max-h-32 overflow-y-auto border-l-2 border-ink pl-4 font-mono text-xs whitespace-pre-wrap text-ink-muted">
              {log.content}
            </div>
          </div>
        );
      case "done":
        return <div className="mt-4 break-words font-bold tracking-widest text-success uppercase">[{log.timestamp}] [DONE] {log.message}</div>;
      case "error":
        return <div className="mt-4 break-words font-bold tracking-widest text-danger uppercase">[{log.timestamp}] [ERROR] {log.message}</div>;
      default:
        return <div className="text-ink-subtle">[{log.timestamp}] Unknown log type</div>;
    }
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          initial={{ opacity: 0, scale: 0.95, y: 20 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.95, y: 20 }}
          className="scrim-backdrop z-modal fixed inset-0 flex items-center justify-center p-4 lg:p-12"
        >
          <div className="liquid-glass-modal relative flex h-[80vh] w-full max-w-5xl flex-col overflow-hidden rounded-structural border border-line/80 font-mono text-ink-muted">
            {/* Header */}
            <div className="flex items-center justify-between border-b border-line bg-canvas/40 px-6 py-5">
              <div className="flex items-center gap-4 text-ink">
                <Terminal className="w-4 h-4" />
                <span className="text-sm tracking-widest uppercase">Librarian Console</span>
                {isRunning && <Loader2 className="ml-2 h-3 w-3 animate-spin text-ink-subtle" />}
              </div>
              <button
                onClick={handleClose}
                className="focus-ring duration-standard text-ink-disabled transition-colors hover:text-ink"
                title="Close"
              >
                <X className="w-6 h-6" />
              </button>
            </div>

            {/* Terminal Body */}
            <div 
              ref={scrollRef}
              className="flex-1 space-y-3 overflow-y-auto bg-canvas/65 p-6 text-xs sm:text-sm md:p-8"
            >
              {logs.length === 0 && !isRunning ? (
                <div className="flex h-full flex-col items-center justify-center text-center text-ink-disabled">
                  <Terminal className="w-12 h-12 mb-6 opacity-20" />
                  <p className="uppercase tracking-widest text-xs mb-2">Agent Dormant</p>
                  <p className="max-w-xs text-xs break-words text-ink-disabled/70">Awaiting initialization command to process the inbox through AI reasoning.</p>
                </div>
              ) : (
                logs.map((log) => (
                  <motion.div
                    key={log.id}
                    initial={{ opacity: 0, x: -10 }}
                    animate={{ opacity: 1, x: 0 }}
                  >
                    {renderLog(log)}
                  </motion.div>
                ))
              )}
            </div>

            {/* Footer Controls */}
            <div className="flex flex-col items-center justify-between gap-4 border-t border-line bg-canvas/40 px-6 py-5 sm:flex-row">
              <div className="flex items-center gap-3 text-xs tracking-widest text-ink-disabled uppercase">
                <span className="hidden sm:inline">System:</span>
                <span className="bg-surface-raised px-2 py-1 text-ink-muted">LangGraph / ReAct</span>
              </div>
              <button
                onClick={isRunning ? stopAgent : startCleaning}
                className={`focus-ring duration-standard flex items-center gap-3 px-8 py-3.5 text-xs font-semibold tracking-widest uppercase transition-all ${
                  isRunning 
                    ? "bg-surface-raised text-ink-subtle hover:bg-surface-hover hover:text-ink"
                    : "bg-inverse text-inverse-ink hover:bg-neutral-200"
                }`}
              >
                {isRunning ? (
                  <>Halt Sequence</>
                ) : (
                  <>
                    <Play className="w-3.5 h-3.5" />
                    Initialize
                  </>
                )}
              </button>
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
