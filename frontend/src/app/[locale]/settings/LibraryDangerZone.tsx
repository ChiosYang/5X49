"use client";

import { AlertTriangle, DatabaseZap } from "lucide-react";
import { useReducedMotion } from "framer-motion";
import { useTranslations } from "next-intl";
import { useState } from "react";
import useSWR, { useSWRConfig } from "swr";

import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { InlineFeedback } from "@/components/ui/Feedback";
import { useLibrary } from "@/hooks/useLibrary";
import { useClearLibraryData } from "@/hooks/useSettings";
import { useWorkflows } from "@/hooks/useWorkflows";
import { useRouter } from "@/i18n/routing";
import { API } from "@/lib/api";
import type {
  LibraryClearResult,
} from "@/hooks/useSettings";
import type { MissingLibraryItemsResponse, OrganizationCandidate } from "@/types/movie";

export default function LibraryDangerZone() {
  const t = useTranslations("LibraryCare.danger");
  const router = useRouter();
  const reducedMotion = useReducedMotion();
  const { mutate } = useSWRConfig();
  const library = useLibrary();
  const missing = useSWR<MissingLibraryItemsResponse>(API.libraryCleanupMissing());
  const organization = useSWR<OrganizationCandidate[]>(API.libraryOrganizationCandidates());
  const workflows = useWorkflows();
  const clear = useClearLibraryData();
  const [open, setOpen] = useState(false);
  const [phrase, setPhrase] = useState("");
  const [result, setResult] = useState<LibraryClearResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const activeWorkflow = (workflows.data ?? []).some(
    (workflow) => workflow.status === "queued" || workflow.status === "running",
  );
  const clearBlocked = activeWorkflow || Boolean(workflows.error);
  const expectedPhrase = t("phrase");

  const confirm = async () => {
    if (phrase !== expectedPhrase || clearBlocked) return;
    setError(null);
    try {
      const response = await clear.trigger();
      setResult(response);
      setPhrase("");
      setOpen(false);
      await Promise.all([
        library.mutate(),
        missing.mutate(),
        organization.mutate(),
        mutate(API.librarySyncStatus()),
        mutate(API.libraryScrapeStatus()),
        mutate(API.libraryExternalScoresStatus()),
        mutate(API.libraryOrganizeStatus()),
      ]);
      router.refresh();
    } catch (clearError) {
      setError(clearError instanceof Error ? clearError.message : t("failed"));
    }
  };

  return (
    <section id="danger-zone" className="scroll-mt-28 border-t border-danger/30 pt-8">
      <div className="mb-6">
        <p className="type-label text-danger">{t("eyebrow")}</p>
        <h3 className="mt-2 type-section-title text-ink">{t("title")}</h3>
        <p className="mt-2 max-w-2xl text-xs leading-5 text-ink-disabled">{t("description")}</p>
      </div>
      <div className="flex flex-col gap-5 border-b border-danger/20 pb-7 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <p className="text-sm font-medium tracking-widest text-danger uppercase">{t("clearTitle")}</p>
          <p className="mt-2 max-w-2xl text-xs leading-5 text-ink-disabled">{t("clearDesc")}</p>
          <div className="mt-3 min-h-5" aria-live="polite">
            {workflows.error ? <InlineFeedback tone="warning">{t("workflowUnavailable")}</InlineFeedback> : activeWorkflow ? <InlineFeedback tone="warning">{t("workflowBlocked")}</InlineFeedback> : null}
            {error ? <InlineFeedback tone="error">{error}</InlineFeedback> : null}
            {result ? (
              <InlineFeedback tone="success">
                {t("complete", {
                  films: result.deleted.films,
                  editions: result.deleted.library_items,
                  jobs: result.deleted.jobs,
                  events: result.deleted.events,
                })}
              </InlineFeedback>
            ) : null}
          </div>
        </div>
        <Button variant="danger" disabled={clearBlocked} icon={<DatabaseZap className="h-4 w-4" />} onClick={() => { setPhrase(""); setError(null); setOpen(true); }}>
          {t("clearButton")}
        </Button>
      </div>

      <Dialog animated={!reducedMotion} open={open} onClose={() => { if (!clear.isMutating) setOpen(false); }} closeLabel={t("close")} ariaLabelledBy="clear-library-title" size="sm" placement="bottom">
        <div className="p-6 sm:p-8">
          <span className="flex h-11 w-11 items-center justify-center rounded-full border border-danger/30 bg-danger/10 text-danger"><AlertTriangle className="h-4 w-4" /></span>
          <h3 id="clear-library-title" className="mt-5 type-section-title text-ink">{t("confirmTitle")}</h3>
          <p className="mt-3 text-sm leading-6 text-ink-subtle">{t("impact", { films: library.data?.length ?? 0, missing: missing.data?.count ?? 0 })}</p>
          <label className="mt-6 block">
            <span className="type-label text-ink-subtle">{t("typePhrase", { phrase: expectedPhrase })}</span>
            <input data-dialog-initial-focus autoComplete="off" value={phrase} onChange={(event) => setPhrase(event.target.value)} className="mt-3 min-h-11 w-full border border-danger/30 bg-canvas px-3 text-sm text-ink outline-none focus:border-danger" />
          </label>
          <div className="mt-7 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
            <Button disabled={clear.isMutating} onClick={() => setOpen(false)}>{t("cancel")}</Button>
            <Button variant="danger" busy={clear.isMutating} disabled={phrase !== expectedPhrase || clearBlocked} onClick={() => void confirm()}>{t("confirm")}</Button>
          </div>
        </div>
      </Dialog>
    </section>
  );
}
