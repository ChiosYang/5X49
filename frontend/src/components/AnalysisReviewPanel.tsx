"use client";

import { useState } from "react";
import useSWR, { mutate } from "swr";
import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { FormField, Select, TextInput } from "@/components/ui/FormControls";
import { InlineFeedback } from "@/components/ui/Feedback";
import { API } from "@/lib/api";
import type { FilmAnalysisTarget } from "@/types/movie";

const predicates = ["INFLUENCED_BY", "REMAKE_OF", "ADAPTED_FROM", "VISUALLY_SIMILAR_TO", "HAS_THEME", "HAS_MOVEMENT", "HAS_VISUAL_STYLE", "HAS_MICRO_GENRE"];
interface Relation {
  id: string; predicate: string; revision: string;
  direction: "subject_to_target" | "target_to_subject";
  target: FilmAnalysisTarget;
  rationale?: string | null;
  review_status: "proposed" | "accepted" | "rejected";
  evidence: Array<{ id: string; source_title: string; source_uri: string }>;
}
interface Review {
  id: string; predicate?: string | null; revision: string;
  candidate_kind: string; reason_code: string;
  candidate_summary: { target?: FilmAnalysisTarget; direction?: string; rationale?: string };
  status: "open" | "resolved" | "dismissed";
}
interface ReviewPage { relations: Relation[]; reviews: Review[]; next_offset: number | null }
type Editing = { kind: "relation"; item: Relation } | { kind: "review"; item: Review };

export default function AnalysisReviewPanel({ filmId }: { filmId: string }) {
  const t = useTranslations("AnalysisReview");
  const [offset, setOffset] = useState(0);
  const { data, error, isLoading, mutate: refresh } = useSWR<ReviewPage>(API.filmAnalysisReview(filmId, offset));
  const [editing, setEditing] = useState<Editing | null>(null);
  const [predicate, setPredicate] = useState(predicates[0]);
  const [direction, setDirection] = useState("subject_to_target");
  const [query, setQuery] = useState("");
  const [target, setTarget] = useState<FilmAnalysisTarget | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState("");
  const [saved, setSaved] = useState(false);
  const referenceOnly = editing?.kind === "review" && editing.item.candidate_kind === "entity_reference";
  const referenceType = referenceOnly ? editing.item.candidate_summary.target?.entity_type : undefined;
  const targets = useSWR<FilmAnalysisTarget[]>(editing ? API.filmAnalysisTargets(filmId, predicate, query, referenceType) : null);
  const filmTarget = predicates.indexOf(predicate) < 4;

  const edit = (entry: Editing) => {
    setEditing(entry);
    setPredicate(entry.item.predicate || predicates[0]);
    setDirection(entry.kind === "relation" ? entry.item.direction : "subject_to_target");
    setQuery(""); setTarget(null); setFailure(""); setSaved(false);
  };
  const submit = async (url: string, payload: object) => {
    if (busy) return;
    setBusy(true); setFailure(""); setSaved(false);
    try {
      const response = await fetch(url, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(body?.detail?.code === "stale_review" ? "stale" : response.status === 409 ? "conflict" : "failed");
      }
      setEditing(null); setSaved(true);
      await Promise.all([refresh(), mutate(API.filmAnalysis(filmId)), mutate(API.filmGraph(filmId)), mutate(API.libraryFilm(filmId))]);
    } catch (issue) {
      setFailure(issue instanceof Error ? issue.message : "failed");
    } finally { setBusy(false); }
  };
  const correct = () => {
    if (!editing || !target) return;
    const correction = { predicate, direction: filmTarget ? direction : "subject_to_target", target_entity_id: target.entity_id };
    if (editing.kind === "relation") {
      void submit(API.assertionReview(filmId, editing.item.id), { revision: editing.item.revision, decision: "rejected", correction });
    } else {
      void submit(API.analysisResolution(filmId, editing.item.id), { revision: editing.item.revision, action: "resolve", correction });
    }
  };

  return (
    <div className="space-y-5">
      <h3 className="type-section-title">{t("title")}</h3>
      <p className="max-w-3xl text-sm leading-6 text-ink-subtle">{t("policy")}</p>
      {isLoading && <p role="status">{t("loading")}</p>}
      {error && <InlineFeedback tone="error">{t("loadFailed")} <Button onClick={() => void refresh()}>{t("reload")}</Button></InlineFeedback>}
      {failure && !editing && <InlineFeedback tone="error">{t(failure === "stale" ? "stale" : failure === "conflict" ? "conflict" : "failed")} <Button onClick={() => { setFailure(""); void refresh(); }}>{t("reload")}</Button></InlineFeedback>}
      {saved && <InlineFeedback tone="success">{t("saved")}</InlineFeedback>}
      {data && !data.relations.length && !data.reviews.length && <p className="text-ink-subtle">{t("empty")}</p>}
      <div className="grid gap-4 lg:grid-cols-2">
        {data?.relations.map((row) => (
          <article key={row.id} className="min-w-0 space-y-4 border border-line p-5">
            <p className="text-xs text-ink-subtle">{t(`predicates.${row.predicate}`)} · {t(`states.${row.review_status}`)}</p>
            <h4 className="break-words font-bold">{row.target.display_name || row.target.entity_id} {row.target.release_year ? `(${row.target.release_year})` : ""}</h4>
            <p className="text-xs text-ink-subtle">{t(row.direction === "target_to_subject" ? "incoming" : "outgoing")}</p>
            {row.rationale && <p className="break-words text-sm text-ink-muted">{row.rationale}</p>}
            {row.evidence.map((item) => <a key={item.id} href={item.source_uri} target="_blank" rel="noreferrer" className="focus-ring block break-words text-sm underline">{item.source_title}</a>)}
            <div className="flex flex-wrap gap-2">
              {row.review_status !== "accepted" && <Button disabled={busy} onClick={() => void submit(API.assertionReview(filmId, row.id), { revision: row.revision, decision: "accepted" })}>{t("accept")}</Button>}
              {row.review_status !== "rejected" && <>
                <Button disabled={busy} onClick={() => void submit(API.assertionReview(filmId, row.id), { revision: row.revision, decision: "rejected" })}>{t("reject")}</Button>
                <Button disabled={busy} onClick={() => edit({ kind: "relation", item: row })}>{t("correct")}</Button>
              </>}
            </div>
          </article>
        ))}
        {data?.reviews.map((row) => (
          <article key={row.id} className="min-w-0 space-y-4 border border-line p-5">
            <p className="text-xs text-warning">{t(`states.${row.status}`)} · {t(`reasons.${row.reason_code}`)}</p>
            <h4 className="break-words font-bold">{row.candidate_summary.target?.display_name || row.candidate_summary.target?.entity_id || t("unresolved")}</h4>
            {row.candidate_summary.rationale && <p className="break-words text-sm text-ink-muted">{row.candidate_summary.rationale}</p>}
            <div className="flex flex-wrap gap-2">
              {row.status === "open" ? <>
                {["assertion", "entity_reference"].includes(row.candidate_kind) && <Button disabled={busy} onClick={() => edit({ kind: "review", item: row })}>{t("resolve")}</Button>}
                <Button disabled={busy} onClick={() => void submit(API.analysisResolution(filmId, row.id), { revision: row.revision, action: "dismiss" })}>{t("dismiss")}</Button>
              </> : <Button disabled={busy} onClick={() => void submit(API.analysisResolution(filmId, row.id), { revision: row.revision, action: "reopen" })}>{t("reopen")}</Button>}
            </div>
          </article>
        ))}
      </div>
      <div className="flex gap-3">
        {offset > 0 && <Button disabled={busy} onClick={() => setOffset(Math.max(0, offset - 50))}>{t("previous")}</Button>}
        {data?.next_offset != null && <Button disabled={busy} onClick={() => setOffset(data.next_offset!)}>{t("next")}</Button>}
      </div>
      <Dialog open={Boolean(editing)} onClose={() => { if (!busy) setEditing(null); }} closeLabel={t("cancel")} ariaLabelledBy="analysis-correction-title" size="md">
        <div className="space-y-5 p-6 sm:p-8">
          <h3 id="analysis-correction-title" className="type-section-title">{t("correct")}</h3>
          <p className="text-sm leading-6 text-ink-subtle">{t(referenceOnly ? "referenceHelp" : "correctionHelp")}</p>
          {!referenceOnly && <FormField label={t("predicate")}><Select value={predicate} disabled={busy} onChange={(event) => { setPredicate(event.target.value); setTarget(null); }}>
            {predicates.map((value) => <option key={value} value={value}>{t(`predicates.${value}`)}</option>)}
          </Select></FormField>}
          {filmTarget && !referenceOnly && <FormField label={t("direction")}><Select value={direction} disabled={busy} onChange={(event) => setDirection(event.target.value)}>
            <option value="subject_to_target">{t("outgoing")}</option><option value="target_to_subject">{t("incoming")}</option>
          </Select></FormField>}
          <FormField label={t("target")}><TextInput value={query} maxLength={200} disabled={busy} onChange={(event) => { setQuery(event.target.value); setTarget(null); }} placeholder={t("targetPlaceholder")} /></FormField>
          <div className="max-h-52 space-y-2 overflow-y-auto" aria-label={t("target")}>
            {targets.isLoading && <p role="status">{t("loading")}</p>}
            {targets.error && <InlineFeedback tone="error">{t("loadFailed")}</InlineFeedback>}
            {targets.data?.length === 0 && <p>{t("noTargets")}</p>}
            {targets.data?.map((item) => <button type="button" key={item.entity_id} disabled={busy} aria-pressed={target?.entity_id === item.entity_id} onClick={() => setTarget(item)} className={`focus-ring block min-h-11 w-full break-words border p-3 text-left ${target?.entity_id === item.entity_id ? "border-ink bg-surface-raised" : "border-line"}`}>
              {item.display_name} {item.release_year ? `(${item.release_year})` : ""}
            </button>)}
          </div>
          {target && <p className="break-words text-sm">{t("selected", { name: target.display_name || target.entity_id })}</p>}
          {failure && <InlineFeedback tone="error">{t(failure === "stale" ? "stale" : failure === "conflict" ? "conflict" : "failed")}</InlineFeedback>}
          <div className="flex flex-wrap justify-end gap-3">
            <Button disabled={busy} onClick={() => setEditing(null)}>{t("cancel")}</Button>
            <Button variant="primary" disabled={busy || !target} busy={busy} onClick={correct}>{t("saveCorrection")}</Button>
          </div>
        </div>
      </Dialog>
    </div>
  );
}
