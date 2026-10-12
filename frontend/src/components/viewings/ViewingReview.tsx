"use client";

import { useTranslations } from "next-intl";
import type { ViewingView } from "@/types/movie";

export default function ViewingReview({ viewing }: { viewing: ViewingView }) {
  const t = useTranslations("Diary");
  if (viewing.rating == null && !viewing.notes) return null;
  return <div className="mt-4 min-w-0 space-y-2 text-sm" data-testid="viewing-review">
    {viewing.rating != null ? <p className="text-ink"><span className="text-ink-subtle">{t("viewingRating")}</span> · {viewing.rating}/5</p> : null}
    {viewing.notes ? <div><p className="type-label text-ink-subtle">{t("viewingNotes")}</p><p className="mt-1 whitespace-pre-wrap break-words leading-6 text-ink-muted [overflow-wrap:anywhere]">{viewing.notes}</p></div> : null}
  </div>;
}
