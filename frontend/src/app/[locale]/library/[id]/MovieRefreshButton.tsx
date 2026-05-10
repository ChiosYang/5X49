"use client";

import { useRouter } from "next/navigation";
import { Loader2, RefreshCw } from "lucide-react";
import { useRefreshMovie } from "@/hooks/useMovie";

export default function MovieRefreshButton({ movieId }: { movieId: string }) {
  const router = useRouter();
  const { trigger, isMutating, error } = useRefreshMovie(movieId);

  const handleRefresh = async () => {
    await trigger();
    router.refresh();
  };

  return (
    <div className="p-8 md:px-16 flex items-center justify-between">
      <div className="space-y-2">
        <span className="block text-xs font-bold uppercase tracking-widest text-neutral-500">
          Metadata
        </span>
        {error && (
          <span className="block text-xs uppercase tracking-widest text-red-500">
            Refresh failed
          </span>
        )}
      </div>
      <button
        type="button"
        onClick={handleRefresh}
        disabled={isMutating}
        className="flex h-11 w-11 items-center justify-center border border-neutral-800 bg-neutral-950 text-white hover:border-neutral-500 hover:bg-neutral-900 disabled:cursor-not-allowed disabled:opacity-50"
        aria-label="Refresh metadata"
        title="Refresh metadata"
      >
        {isMutating ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <RefreshCw className="h-4 w-4" />
        )}
      </button>
    </div>
  );
}
