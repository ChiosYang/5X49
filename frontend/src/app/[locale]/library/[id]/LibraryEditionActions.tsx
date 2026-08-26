"use client";

import { EyeOff, RefreshCw } from "lucide-react";
import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { mutate } from "swr";

import { IconButton } from "@/components/ui/Button";
import { useIgnoreLibraryItem, useRefreshLibraryItem } from "@/hooks/useFilm";
import { API } from "@/lib/api";

export default function LibraryEditionActions({ filmId, itemId }: { filmId: string; itemId: string }) {
  const t = useTranslations("FilmDetail");
  const router = useRouter();
  const refresh = useRefreshLibraryItem(itemId);
  const ignore = useIgnoreLibraryItem(itemId);
  const busy = refresh.isMutating || ignore.isMutating;

  const refreshViews = async () => {
    await Promise.all([mutate(API.libraryFilm(filmId)), mutate(API.libraryFilms())]);
    router.refresh();
  };

  return (
    <div className="flex shrink-0 items-center gap-2">
      <IconButton
        onClick={async () => { await refresh.trigger(); }}
        disabled={busy}
        busy={refresh.isMutating}
        aria-label={t("refreshEdition")}
        title={t("refreshEdition")}
        icon={<RefreshCw className="h-4 w-4" />}
      />
      <IconButton
        onClick={async () => { await ignore.trigger(); await refreshViews(); }}
        disabled={busy || ignore.isMutating}
        busy={ignore.isMutating}
        aria-label={t("ignoreEdition")}
        title={t("ignoreEdition")}
        icon={<EyeOff className="h-4 w-4" />}
      />
    </div>
  );
}
