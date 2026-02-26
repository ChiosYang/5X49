"use client";

import { useState, useRef, useEffect } from "react";
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

  // Auto-scroll to bottom
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [logs]);

  // Cleanup on unmount or close
  useEffect(() => {
    if (!isOpen) {
      stopAgent();
    }
    return () => stopAgent();
  }, [isOpen]);

  const stopAgent = () => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    setIsRunning(false);
  };

  const startCleaning = () => {
    setLogs([]);
    setIsRunning(true);

    const baseUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    const es = new EventSource(`${baseUrl}/api/agents/clean-inbox`);
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
        return <div className="text-neutral-500">[{log.timestamp}] [SYSTEM] {log.message}</div>;
      case "thought":
        return <div className="text-white">[{log.timestamp}] [REASONING] {log.message}</div>;
      case "tool_execution":
        return (
          <div className="text-neutral-400 my-4 bg-neutral-950 p-4 border border-neutral-800">
            <div>[{log.timestamp}] [SYSTEM_CALL: {log.tool_name}]</div>
            <div className="text-neutral-300 mt-2 pl-4 border-l-2 border-white whitespace-pre-wrap font-mono text-xs max-h-32 overflow-y-auto hidden-scrollbar">
              {log.content}
            </div>
          </div>
        );
      case "done":
        return <div className="text-white font-bold uppercase tracking-widest mt-4">[{log.timestamp}] [DONE] {log.message}</div>;
      case "error":
        return <div className="text-red-500 font-bold uppercase tracking-widest mt-4">[{log.timestamp}] [ERROR] {log.message}</div>;
      default:
        return <div className="text-neutral-500">[{log.timestamp}] Unknown log type</div>;
    }
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          initial={{ opacity: 0, scale: 0.95, y: 20 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.95, y: 20 }}
          className="fixed inset-0 z-50 flex items-center justify-center p-4 lg:p-12 bg-black/90 backdrop-blur-md"
        >
          <div className="w-full max-w-5xl bg-black border border-neutral-800 shadow-2xl rounded-none overflow-hidden flex flex-col h-[80vh] font-mono text-neutral-400">
            {/* Header */}
            <div className="px-6 py-5 border-b border-neutral-900 bg-black flex items-center justify-between">
              <div className="flex items-center gap-4 text-white">
                <Terminal className="w-4 h-4" />
                <span className="text-sm tracking-widest uppercase">Librarian Console</span>
                {isRunning && <Loader2 className="w-3 h-3 animate-spin ml-2 text-neutral-500" />}
              </div>
              <button
                onClick={onClose}
                className="text-neutral-600 hover:text-white transition-colors"
                title="Close"
              >
                <X className="w-6 h-6" />
              </button>
            </div>

            {/* Terminal Body */}
            <div 
              ref={scrollRef}
              className="flex-1 overflow-y-auto p-6 md:p-8 text-xs sm:text-sm bg-[#0a0a0a] space-y-3"
            >
              {logs.length === 0 && !isRunning ? (
                <div className="text-neutral-600 h-full flex flex-col items-center justify-center text-center">
                  <Terminal className="w-12 h-12 mb-6 opacity-20" />
                  <p className="uppercase tracking-widest text-xs mb-2">Agent Dormant</p>
                  <p className="text-xs text-neutral-700 max-w-xs">Awaiting initialization command to process the inbox through AI reasoning.</p>
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
            <div className="px-6 py-5 border-t border-neutral-900 bg-black flex flex-col sm:flex-row gap-4 justify-between items-center">
              <div className="text-xs text-neutral-600 uppercase tracking-widest flex items-center gap-3">
                <span className="hidden sm:inline">System:</span>
                <span className="bg-neutral-900 px-2 py-1 text-neutral-400">LangGraph / ReAct</span>
              </div>
              <button
                onClick={isRunning ? stopAgent : startCleaning}
                className={`flex items-center gap-3 px-8 py-3.5 text-xs font-semibold uppercase tracking-widest transition-all ${
                  isRunning 
                    ? "bg-neutral-900 text-neutral-500 hover:bg-neutral-800 hover:text-white" 
                    : "bg-white text-black hover:bg-neutral-200"
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
