"use client";

import { useState } from "react";
import { useDirectories } from "@/hooks/useDirectories";

interface FileBrowserProps {
  initialPath?: string;
  onSelect: (path: string) => void;
  onCancel: () => void;
  isOpen: boolean;
}

export default function FileBrowser({ initialPath, onSelect, onCancel, isOpen }: FileBrowserProps) {
  const [currentPath, setCurrentPath] = useState(initialPath || "/");

  const { data, error, isLoading } = useDirectories(currentPath, isOpen);

  const handleNavigate = (path: string) => {
    setCurrentPath(path);
  };

  if (!isOpen) return null;

  return (
    <div className="scrim-backdrop z-modal fixed inset-0 flex items-center justify-center p-4">
      <div className="liquid-glass-modal relative flex max-h-[80vh] w-full max-w-2xl flex-col overflow-hidden border border-line/80 text-ink">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-line-strong bg-canvas/35 p-4">
          <h3 className="text-lg font-bold tracking-widest text-ink uppercase">Select Directory</h3>
          <button onClick={onCancel} className="focus-ring duration-standard text-ink-subtle transition-colors hover:text-ink">✕</button>
        </div>

        {/* Current Path & Navigation */}
        <div className="flex items-center gap-2 border-b border-line-strong bg-canvas/20 p-4">
          <button
            onClick={() => data?.parent_path && handleNavigate(data.parent_path)}
            disabled={!data?.parent_path}
            className="focus-ring duration-standard rounded-control bg-surface-hover px-3 py-1 text-sm text-ink transition-colors hover:bg-line-strong disabled:cursor-not-allowed disabled:opacity-30"
            title="Go Up"
          >
            ⬆ Up
          </button>
          <div className="min-w-0 flex-1 break-all border border-line-strong bg-canvas/35 px-3 py-2 font-mono text-sm text-ink-muted">
            {data?.current_path || currentPath}
          </div>
        </div>

        {/* Directory List */}
        <div className="min-h-[300px] flex-1 overflow-y-auto bg-canvas/25 p-2">
            {isLoading ? (
                <div className="flex h-full items-center justify-center text-sm text-ink-subtle animate-pulse">
                    Loading...
                </div>
            ) : error ? (
                <div className="flex h-full items-center justify-center break-words text-sm text-danger">
                    {error.message}
                </div>
            ) : !data?.directories || data.directories.length === 0 ? (
                <div className="flex h-full items-center justify-center text-sm text-ink-disabled italic">
                    No subdirectories found
                </div>
            ) : (
                <div className="grid grid-cols-1 gap-1">
                    {data.directories.map((dir) => (
                        <button
                            key={dir.path}
                            onClick={() => handleNavigate(dir.path)}
                            className="focus-ring duration-standard group flex items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-ink/5"
                        >
                            <span className="text-xl text-warning/70 group-hover:text-warning">📁</span>
                            <span className="truncate text-sm font-medium text-ink-muted group-hover:text-ink">{dir.name}</span>
                        </button>
                    ))}
                </div>
            )}
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-3 border-t border-line-strong bg-canvas/25 p-4">
            <button
                onClick={onCancel}
                className="focus-ring duration-fast px-4 py-2 text-xs font-medium tracking-widest text-ink-muted uppercase transition-colors hover:text-ink"
            >
                Cancel
            </button>
            <button
                onClick={() => onSelect(data?.current_path || currentPath)}
                className="focus-ring duration-fast bg-inverse px-6 py-2 text-xs font-bold tracking-widest text-inverse-ink uppercase transition-colors hover:bg-neutral-200"
            >
                Select Current Folder
            </button>
        </div>
      </div>
    </div>
  );
}
