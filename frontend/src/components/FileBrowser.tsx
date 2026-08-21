"use client";

import { useState } from "react";
import { X } from "lucide-react";
import { useDirectories } from "@/hooks/useDirectories";
import { Button, IconButton } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { StateMessage } from "@/components/ui/Feedback";

interface FileBrowserProps {
  initialPath?: string;
  onSelect: (path: string) => void;
  onCancel: () => void;
  isOpen: boolean;
}

export default function FileBrowser({ initialPath, onSelect, onCancel, isOpen }: FileBrowserProps) {
  const [currentPath, setCurrentPath] = useState(initialPath || "/");
  const { data, error, isLoading } = useDirectories(currentPath, isOpen);

  return (
    <Dialog
      open={isOpen}
      onClose={onCancel}
      closeLabel="Close directory browser"
      closeOnBackdrop={false}
      closeOnEscape={false}
      lockScroll={false}
      ariaLabelledBy="file-browser-title"
      panelClassName="flex max-h-[80vh] flex-col"
    >
      <div className="flex items-center justify-between border-b border-line-strong bg-canvas/35 p-4">
        <h3 id="file-browser-title" className="text-lg font-bold tracking-widest text-ink uppercase">
          Select Directory
        </h3>
        <IconButton
          variant="ghost"
          onClick={onCancel}
          aria-label="Close directory browser"
          icon={<X className="h-4 w-4" />}
          className="h-8 w-8"
        />
      </div>

      <div className="flex items-center gap-2 border-b border-line-strong bg-canvas/20 p-4">
        <Button
          size="sm"
          onClick={() => data?.parent_path && setCurrentPath(data.parent_path)}
          disabled={!data?.parent_path}
        >
          ⬆ Up
        </Button>
        <div className="min-w-0 flex-1 break-all border border-line-strong bg-canvas/35 px-3 py-2 font-mono text-sm text-ink-muted">
          {data?.current_path || currentPath}
        </div>
      </div>

      <div className="min-h-[300px] flex-1 overflow-y-auto bg-canvas/25 p-2">
        {isLoading ? (
          <StateMessage state="loading" className="h-full border-0 bg-transparent">Loading...</StateMessage>
        ) : error ? (
          <StateMessage state="error" className="h-full border-0 bg-transparent">{error.message}</StateMessage>
        ) : !data?.directories?.length ? (
          <StateMessage className="h-full border-0 bg-transparent italic">No subdirectories found</StateMessage>
        ) : (
          <div className="grid grid-cols-1 gap-1">
            {data.directories.map((dir) => (
              <button
                key={dir.path}
                type="button"
                onClick={() => setCurrentPath(dir.path)}
                className="focus-ring duration-standard group flex items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-ink/5"
              >
                <span className="text-xl text-warning/70 group-hover:text-warning">📁</span>
                <span className="truncate text-sm font-medium text-ink-muted group-hover:text-ink">{dir.name}</span>
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="flex justify-end gap-3 border-t border-line-strong bg-canvas/25 p-4">
        <Button variant="ghost" onClick={onCancel}>Cancel</Button>
        <Button variant="primary" onClick={() => onSelect(data?.current_path || currentPath)}>
          Select Current Folder
        </Button>
      </div>
    </Dialog>
  );
}
