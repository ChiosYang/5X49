"use client";

import { useState, useEffect } from "react";
import API from "@/lib/api";

interface FileBrowserProps {
  initialPath?: string;
  onSelect: (path: string) => void;
  onCancel: () => void;
  isOpen: boolean;
}

interface DirectoryItem {
  name: string;
  path: string;
}

export default function FileBrowser({ initialPath, onSelect, onCancel, isOpen }: FileBrowserProps) {
  const [currentPath, setCurrentPath] = useState(initialPath || "/");
  const [directories, setDirectories] = useState<DirectoryItem[]>([]);
  const [parentPath, setParentPath] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen) {
      if (initialPath) {
        setCurrentPath(initialPath);
        fetchDirectories(initialPath);
      } else {
        fetchDirectories("/");
      }
    }
  }, [isOpen, initialPath]);

  const fetchDirectories = async (path: string) => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API.systemListDirs()}?path=${encodeURIComponent(path)}`);
      if (res.ok) {
        const data = await res.json();
        setCurrentPath(data.current_path);
        setParentPath(data.parent_path);
        setDirectories(data.directories);
      } else {
        const err = await res.json();
        setError(err.detail || "Failed to list directories");
      }
    } catch (e) {
      setError("Network error");
    } finally {
      setLoading(false);
    }
  };

  const handleNavigate = (path: string) => {
    fetchDirectories(path);
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm">
      <div className="bg-neutral-900 border border-neutral-800 w-full max-w-2xl flex flex-col max-h-[80vh] shadow-2xl">
        {/* Header */}
        <div className="p-4 border-b border-neutral-800 flex justify-between items-center bg-neutral-950">
          <h3 className="text-lg font-bold uppercase tracking-widest text-white">Select Directory</h3>
          <button onClick={onCancel} className="text-neutral-500 hover:text-white transition-colors">✕</button>
        </div>

        {/* Current Path & Navigation */}
        <div className="p-4 bg-neutral-900 border-b border-neutral-800 flex items-center gap-2">
          <button
            onClick={() => parentPath && handleNavigate(parentPath)}
            disabled={!parentPath}
            className="px-3 py-1 bg-neutral-800 hover:bg-neutral-700 disabled:opacity-30 disabled:cursor-not-allowed text-white text-sm rounded transition-colors"
            title="Go Up"
          >
            ⬆ Up
          </button>
          <div className="flex-1 bg-black border border-neutral-800 px-3 py-2 text-sm text-neutral-300 font-mono truncate">
            {currentPath}
          </div>
        </div>

        {/* Directory List */}
        <div className="flex-1 overflow-y-auto p-2 min-h-[300px] bg-neutral-950">
            {loading ? (
                <div className="flex items-center justify-center h-full text-neutral-500 text-sm animate-pulse">
                    Loading...
                </div>
            ) : error ? (
                <div className="flex items-center justify-center h-full text-red-500 text-sm">
                    {error}
                </div>
            ) : directories.length === 0 ? (
                <div className="flex items-center justify-center h-full text-neutral-600 text-sm italic">
                    No subdirectories found
                </div>
            ) : (
                <div className="grid grid-cols-1 gap-1">
                    {directories.map((dir) => (
                        <button
                            key={dir.path}
                            onClick={() => handleNavigate(dir.path)}
                            className="flex items-center gap-3 px-4 py-3 text-left hover:bg-neutral-900 transition-colors group"
                        >
                            <span className="text-yellow-600 group-hover:text-yellow-500 text-xl">📁</span>
                            <span className="text-neutral-300 group-hover:text-white text-sm font-medium truncate">{dir.name}</span>
                        </button>
                    ))}
                </div>
            )}
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-neutral-800 bg-neutral-900 flex justify-end gap-3">
            <button
                onClick={onCancel}
                className="px-4 py-2 text-xs font-medium uppercase tracking-widest text-neutral-400 hover:text-white transition-colors"
            >
                Cancel
            </button>
            <button
                onClick={() => onSelect(currentPath)}
                className="px-6 py-2 bg-white text-black text-xs font-bold uppercase tracking-widest hover:bg-neutral-200 transition-colors"
            >
                Select Current Folder
            </button>
        </div>
      </div>
    </div>
  );
}
