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
        return <div className="text-blue-400">[{log.timestamp}] [SYSTEM] {log.message}</div>;
      case "thought":
        return <div className="text-green-400">[{log.timestamp}] [AGENT THOUGHT] {log.message}</div>;
      case "tool_execution":
        return (
          <div className="text-purple-400 my-2 bg-purple-900/20 p-2 rounded border border-purple-900/50">
            <div>[{log.timestamp}] [TOOL: {log.tool_name}]</div>
            <div className="text-neutral-300 mt-1 pl-4 border-l-2 border-purple-500 whitespace-pre-wrap font-mono text-xs max-h-32 overflow-y-auto">
              {log.content}
            </div>
          </div>
        );
      case "done":
        return <div className="text-yellow-400 font-bold mt-4">[{log.timestamp}] [DONE] {log.message}</div>;
      case "error":
        return <div className="text-red-500 font-bold mt-4">[{log.timestamp}] [ERROR] {log.message}</div>;
      default:
        return <div className="text-neutral-400">[{log.timestamp}] Unknown log type</div>;
    }
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          initial={{ opacity: 0, scale: 0.95, y: 20 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.95, y: 20 }}
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm"
        >
          <div className="w-full max-w-4xl bg-neutral-950 border border-neutral-800 shadow-2xl rounded-xl overflow-hidden flex flex-col h-[70vh]">
            {/* Header */}
            <div className="px-4 py-3 border-b border-neutral-800 bg-neutral-900 flex items-center justify-between">
              <div className="flex items-center gap-2 text-neutral-400">
                <Terminal className="w-4 h-4" />
                <span className="text-sm font-mono tracking-wider uppercase">Librarian Agent Terminal</span>
                {isRunning && <Loader2 className="w-3 h-3 animate-spin ml-2 text-green-400" />}
              </div>
              <button
                onClick={onClose}
                className="text-neutral-500 hover:text-white transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Terminal Body */}
            <div 
              ref={scrollRef}
              className="flex-1 overflow-y-auto p-4 font-mono text-xs sm:text-sm bg-[#0a0a0a] space-y-1.5"
            >
              {logs.length === 0 && !isRunning ? (
                <div className="text-neutral-500 h-full flex flex-col items-center justify-center italic text-center">
                  <Terminal className="w-12 h-12 mb-4 opacity-20" />
                  <p>Agent is resting.</p>
                  <p className="mt-2 text-xs">Press 'Execute' to summon the Librarian Agent to clean your inbox.</p>
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
            <div className="p-4 border-t border-neutral-800 bg-neutral-900 flex justify-between items-center">
              <div className="text-xs text-neutral-500 font-mono">
                Model: ReAct Agent (LangGraph/LangChain)
              </div>
              <button
                onClick={isRunning ? stopAgent : startCleaning}
                className={`flex items-center gap-2 px-6 py-2 text-xs font-medium uppercase tracking-widest transition-colors ${
                  isRunning 
                    ? "bg-red-950 text-red-500 hover:bg-red-900 border border-red-900" 
                    : "bg-green-950 text-green-400 hover:bg-green-900 border border-green-900"
                }`}
              >
                {isRunning ? (
                  <>Stop Execution</>
                ) : (
                  <>
                    <Play className="w-3 h-3" />
                    Execute Agent
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
