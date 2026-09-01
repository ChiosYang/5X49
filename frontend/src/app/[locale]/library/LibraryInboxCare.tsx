"use client";

import { CheckCircle2, Clock3, FolderInput } from "lucide-react";
import { useTranslations } from "next-intl";

import { Link } from "@/i18n/routing";
import RootVideoReviewQueue from "./manage/RootVideoReviewQueue";

export default function LibraryInboxCare({
  actionableCount,
  waitingCount,
}: {
  actionableCount: number;
  waitingCount: number;
}) {
  const t = useTranslations("LibraryCare");
  const total = actionableCount + waitingCount;

  if (total === 0) {
    return (
      <div className="border-y border-line py-16 text-center">
        <CheckCircle2 className="mx-auto h-8 w-8 text-success" />
        <h2 className="mt-5 type-section-title text-ink">{t("inboxEmpty")}</h2>
        <p className="mx-auto mt-3 max-w-xl text-sm leading-6 text-ink-subtle">{t("inboxEmptyDesc")}</p>
        <Link href="/library" className="focus-ring mt-7 inline-flex min-h-10 items-center border border-line-strong px-4 type-label text-ink-muted hover:border-ink-disabled hover:text-ink">
          {t("backToFilms")}
        </Link>
      </div>
    );
  }

  return (
    <section className="min-w-0">
      <div className="flex flex-col gap-5 border-b border-line pb-6 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 className="type-section-title text-ink">{t("inboxTitle")}</h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-ink-subtle">{t("inboxDesc")}</p>
        </div>
        <div className="flex flex-wrap gap-3 type-badge">
          <span className="inline-flex items-center gap-2 border border-line-strong px-3 py-2 text-ink-muted">
            <FolderInput className="h-3.5 w-3.5" />{t("readyCount", { count: actionableCount })}
          </span>
          {waitingCount > 0 ? (
            <span className="inline-flex items-center gap-2 border border-warning/30 px-3 py-2 text-warning">
              <Clock3 className="h-3.5 w-3.5" />{t("waitingCount", { count: waitingCount })}
            </span>
          ) : null}
        </div>
      </div>
      <div className="pt-2">
        <RootVideoReviewQueue compact />
      </div>
    </section>
  );
}
