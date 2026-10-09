"use client";

import { Check, EyeOff, RefreshCw } from "lucide-react";
import { useTranslations } from "next-intl";

import { IconButton } from "@/components/ui/Button";
import { useIgnoreLibraryItem, useRefreshLibraryItem, useSelectPrimaryEdition } from "@/hooks/useFilm";
import { useFilmAction } from "@/hooks/useFilmAction";
import { InlineFeedback } from "@/components/ui/Feedback";

export default function LibraryEditionActions({ filmId, itemId, primary, available }: { filmId: string; itemId: string; primary: boolean; available: boolean }) {
  const t = useTranslations("FilmDetail");
  const action = useFilmAction(filmId);
  const refresh = useRefreshLibraryItem(itemId);
  const ignore = useIgnoreLibraryItem(itemId);
  const select = useSelectPrimaryEdition(filmId);
  const busy = action.pending || refresh.isMutating || ignore.isMutating || select.isMutating;

  return (
    <div className="flex min-w-0 flex-col items-end gap-2">
      <div className="flex items-center gap-2">
      {primary ? <span className="type-badge text-ink-muted">{t("primaryEdition")}</span> : available && <IconButton
        onClick={() => void action.run(() => select.trigger(itemId), t("primarySelectFailed"))}
        disabled={busy} busy={select.isMutating} aria-label={t("selectPrimaryEdition")} title={t("selectPrimaryEdition")}
        icon={<Check className="h-4 w-4" />} />}
      <IconButton
        onClick={() => void action.run(() => refresh.trigger(), t("editionRefreshFailed"), () => {}, t("editionRefreshQueued"))}
        disabled={busy}
        busy={refresh.isMutating}
        aria-label={t("refreshEdition")}
        title={t("refreshEdition")}
        icon={<RefreshCw className="h-4 w-4" />}
      />
      <IconButton
        onClick={() => void action.run(() => ignore.trigger(), t("ignoreFailed"), () => {}, t("editionIgnored"))}
        disabled={busy || ignore.isMutating}
        busy={ignore.isMutating}
        aria-label={t("ignoreEdition")}
        title={t("ignoreEdition")}
        icon={<EyeOff className="h-4 w-4" />}
      />
      </div>
      <div role="status" aria-live="polite" className="max-w-xs text-right">
        {action.feedback && <InlineFeedback tone={action.feedback.kind === "failed" ? "error" : action.feedback.kind === "refreshFailed" ? "warning" : "success"}>{action.feedback.message}</InlineFeedback>}
        {action.feedback?.kind === "refreshFailed" && <button type="button" disabled={busy} onClick={() => void action.retryRefresh()} className="focus-ring min-h-11 text-sm underline">{t("retryRefresh")}</button>}
      </div>
    </div>
  );
}
