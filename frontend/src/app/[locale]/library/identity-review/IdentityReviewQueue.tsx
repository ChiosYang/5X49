"use client";

import { useRef, useState } from "react";
import { useTranslations } from "next-intl";
import useSWR from "swr";

import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { StateMessage } from "@/components/ui/Feedback";
import { Link } from "@/i18n/routing";
import { API } from "@/lib/api";
import type { IdentityDecisionPreview, IdentityReviewDetail, IdentityReviewFilm, IdentityReviewItem, IdentityReviewPage } from "@/types/identity-review";

const reasonKeys = new Set([
  "identity_conflict", "relink_identity_conflict", "relink_live_copy_conflict",
  "relink_file_disappeared", "relink_full_hash_no_match", "relink_full_hash_duplicate",
]);

function FilmSummary({ film, item }: { film: IdentityReviewFilm | null; item: IdentityReviewItem | null }) {
  const t = useTranslations("IdentityReview");
  return <div className="min-w-0 space-y-2 break-words">
    <h3 className="type-section-title">{film?.title ?? t("unavailable")}</h3>
    {film && <>
      <p className="text-sm text-ink-subtle">{film.year ?? t("unknownYear")}</p>
      <p className="text-sm text-ink-muted">{Object.entries(film.identities).map(([provider, id]) => `${provider}: ${id}`).join(" · ") || t("noIdentity")}</p>
      <p className="text-xs leading-6 text-ink-subtle">{t("personalData", { count: film.personal_data.viewings })}
        {film.personal_data.has_rating && ` · ${t("hasRating")}`}
        {film.personal_data.has_notes && ` · ${t("hasNotes")}`}
        {film.personal_data.favorite && ` · ${t("favorite")}`}
      </p>
    </>}
    {item && <p className="text-sm text-ink-subtle">{item.display_name || t("unnamedEdition")} · {t.has(`availability.${item.availability}`) ? t(`availability.${item.availability}`) : t("unavailable")}</p>}
  </div>;
}

function ReviewDetail({ id, onClose, onDecided }: { id: string; onClose: () => void; onDecided: () => void }) {
  const t = useTranslations("IdentityReview");
  const { data, error, isLoading, mutate } = useSWR<IdentityReviewDetail>(API.identityReview(id));
  const inFlight = useRef(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [preview, setPreview] = useState<(IdentityDecisionPreview & { idempotency_key: string }) | null>(null);
  const errorText = (code: string) => t.has(`errors.${code}`) ? t(`errors.${code}`) : t("actionFailed");
  async function post(url: string, body: object) {
    const response = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const result = await response.json();
    if (!response.ok) throw new Error(result?.detail?.code ?? "action_failed");
    return result;
  }
  async function prepare(action: "keep_separate" | "reconnect", target_item_id: string | null = null) {
    if (inFlight.current) return;
    inFlight.current = true; setBusy(true); setFailure(null);
    try {
      const result: IdentityDecisionPreview = await post(API.identityPreview(id), { action, target_item_id });
      setPreview({ ...result, idempotency_key: crypto.randomUUID() });
    } catch (error) { setFailure(error instanceof Error ? error.message : "action_failed"); }
    finally { inFlight.current = false; setBusy(false); }
  }
  async function confirm() {
    if (inFlight.current || !preview) return;
    inFlight.current = true; setBusy(true); setFailure(null);
    try {
      await post(API.identityConfirm(id), { action: preview.action, target_item_id: preview.effects.target_item_id,
        confirmation_token: preview.confirmation_token, idempotency_key: preview.idempotency_key });
      onDecided();
    } catch (error) { setFailure(error instanceof Error ? error.message : "action_failed"); }
    finally { inFlight.current = false; setBusy(false); }
  }
  return <Dialog open onClose={() => { if (!inFlight.current) onClose(); }} closeOnEscape={!busy} closeOnBackdrop={!busy} closeLabel={t("close")} ariaLabel={t("detailTitle")} size="lg" glass={false} panelClassName="max-h-[calc(100dvh-2rem)] overflow-y-auto">
    <div className="min-w-0 space-y-6 p-5 sm:p-8">
      <div className="flex items-start justify-between gap-4">
        <h2 className="type-section-title">{t("detailTitle")}</h2>
        <Button variant="secondary" disabled={busy} onClick={onClose}>{t("close")}</Button>
      </div>
      {error ? <div className="space-y-3"><StateMessage state="error">{t("loadFailed")}</StateMessage><Button onClick={() => void mutate()}>{t("retry")}</Button></div> : isLoading ? <StateMessage state="loading">{t("loading")}</StateMessage> : data ? <>
        <p className="text-sm leading-6 text-ink-muted">{t(`reasons.${reasonKeys.has(data.reason_code) ? data.reason_code : "unknown"}`)}</p>
        <section className="border-y border-line py-5">
          <p className="mb-3 type-label text-ink-subtle">{t("currentRecord")}</p>
          <FilmSummary film={data.film} item={data.library_item} />
        </section>
        {Object.keys(data.incoming_identities).length > 0 && <p className="break-words text-sm text-ink-muted">{t("incoming")}: {Object.entries(data.incoming_identities).map(([provider, value]) => `${provider}: ${value}`).join(" · ")}</p>}
        <section className="space-y-4">
          <h3 className="type-label text-ink-muted">{t("candidates")}</h3>
          {!data.evidence_available ? <StateMessage>{t("legacyEvidence")}</StateMessage> : data.candidates.length === 0 ? <StateMessage>{t("noCandidates")}</StateMessage> : data.candidates.map((candidate) => <div key={candidate.library_item_id ?? candidate.film_id} className="space-y-3 border-b border-line pb-5">
            <FilmSummary film={candidate.film} item={candidate.library_item} />
            <p className={`text-xs leading-5 ${candidate.evidence_status === "current" ? "text-ink-subtle" : "text-warning"}`}>{t(`evidence.${candidate.evidence_status}`)}</p>
            {!preview && data.actions.includes("reconnect") && candidate.library_item && candidate.film_id === data.film?.id && candidate.evidence_status === "current" && ["available", "missing"].includes(candidate.library_item.availability) && <Button disabled={busy} onClick={() => void prepare("reconnect", candidate.library_item_id)}>{t("reconnect")}</Button>}
          </div>)}
          {data.candidates_truncated && <p className="text-sm text-warning">{t("truncated")}</p>}
        </section>
        {data.blocked_code && <p className="text-sm leading-6 text-warning">{errorText(data.blocked_code)}</p>}
        {!preview && data.actions.includes("keep_separate") && <Button disabled={busy} onClick={() => void prepare("keep_separate")}>{t("keepSeparate")}</Button>}
        {preview && <section className="space-y-4 border-t border-line pt-5" aria-label={t("confirmTitle")}>
          <h3 className="type-section-title">{t("confirmTitle")}</h3>
          <p className="text-sm leading-6 text-ink-muted">{t(preview.action === "reconnect" ? "reconnectEffects" : "keepEffects")}</p>
          {preview.action === "reconnect" && <p className="text-sm text-ink-muted">{t("targetEdition")}: {data.candidates.find(c => c.library_item_id === preview.effects.target_item_id)?.library_item?.display_name}</p>}
          {preview.effects.expiring_snapshot_ids.length > 0 && <p className="text-sm leading-6 text-warning">{t("undoEffects", { count: preview.effects.expiring_snapshot_ids.length })}</p>}
          <p className="text-sm leading-6 text-ink-subtle">{t("preserveData")}</p>
          <div className="flex flex-wrap gap-3">
            <Button disabled={busy} onClick={() => void confirm()}>{t(busy ? "saving" : "confirm")}</Button>
            <Button variant="secondary" disabled={busy} onClick={() => { setPreview(null); setFailure(null); }}>{t("cancel")}</Button>
          </div>
        </section>}
        {failure && <div role="alert" className="space-y-3"><p className="text-sm text-danger">{errorText(failure)}</p><Button disabled={busy} onClick={() => { setPreview(null); setFailure(null); void mutate(); }}>{t("refreshEvidence")}</Button></div>}
        <p className="text-sm leading-6 text-ink-subtle">{t("readOnly")}</p>
      </> : null}
    </div>
  </Dialog>;
}

export default function IdentityReviewQueue() {
  const t = useTranslations("IdentityReview");
  const [offset, setOffset] = useState(0);
  const [active, setActive] = useState<string | null>(null);
  const [completed, setCompleted] = useState(false);
  const { data, error, isLoading, mutate } = useSWR<IdentityReviewPage>(API.identityReviews(offset));
  return <main className="page-x min-h-screen bg-canvas py-6 text-ink md:py-12">
    <div className="w-full pt-32">
      <header className="space-y-5 border-b border-line pb-8">
        <Link href="/library" className="focus-ring inline-flex min-h-10 items-center type-label text-ink-subtle hover:text-ink">{t("back")}</Link>
        <h1 className="type-display-editorial break-words">{t("title")}</h1>
        <p className="max-w-3xl text-sm leading-6 text-ink-subtle">{t("description")}</p>
      </header>
      <section className="mt-8 space-y-5" aria-label={t("queue")}>
        {completed && <p role="status" className="text-sm text-success">{t("completed")}</p>}
        {error ? <div className="space-y-3"><StateMessage state="error">{t("loadFailed")}</StateMessage><Button onClick={() => void mutate()}>{t("retry")}</Button></div> : isLoading ? <StateMessage state="loading">{t("loading")}</StateMessage> : data ? <>
          <p className="type-label text-ink-subtle">{t("count", { count: data.total })}</p>
          {data.items.length === 0 ? <StateMessage>{t(offset > 0 ? "emptyPage" : "empty")}</StateMessage> : <ul className="divide-y divide-line border-y border-line">
            {data.items.map((review) => <li key={review.id} className="flex min-w-0 flex-col items-start gap-4 py-5 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0 space-y-2 break-words">
                <h2 className="type-section-title">{review.film?.title ?? t("unavailable")}</h2>
                <p className="text-sm leading-6 text-ink-subtle">{t(`reasons.${reasonKeys.has(review.reason_code) ? review.reason_code : "unknown"}`)}</p>
              </div>
              <Button variant="secondary" onClick={() => setActive(review.id)}>{t("inspect")}</Button>
            </li>)}
          </ul>}
          {(offset > 0 || offset + data.limit < data.total) && <nav className="flex justify-between gap-4" aria-label={t("pagination")}>
            <Button variant="secondary" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 40))}>{t("previous")}</Button>
            <Button variant="secondary" disabled={offset + data.limit >= data.total} onClick={() => setOffset(offset + 40)}>{t("next")}</Button>
          </nav>}
        </> : null}
      </section>
    </div>
    {active && <ReviewDetail key={active} id={active} onClose={() => setActive(null)} onDecided={() => { setActive(null); setCompleted(true); void mutate(); }} />}
  </main>;
}
