"use client";

import { useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import useSWR from "swr";
import { Button } from "@/components/ui/Button";
import { FormField, Select, TextArea, TextInput } from "@/components/ui/FormControls";
import { InlineFeedback } from "@/components/ui/Feedback";
import { Link } from "@/i18n/routing";
import { API } from "@/lib/api";
import { askErrorCode, askQueryPayload, emptyAskPlan, type AskPlan, type AskResolution } from "@/lib/ask";
import { formatExploreFacetLabel } from "@/lib/explore";
import LibraryMovieCard from "../library/LibraryMovieCard";

export default function AskClient() {
  const t = useTranslations("Ask");
  const locale = useLocale();
  const status = useSWR<{ configured: boolean }>(API.askStatus());
  const [mode, setMode] = useState<"question" | "form">("question");
  const [question, setQuestion] = useState("");
  const [draft, setDraft] = useState<AskPlan>({ ...emptyAskPlan });
  const [resolution, setResolution] = useState<AskResolution | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const reset = () => { setResolution(null); setError(""); };
  const change = (values: Partial<AskPlan>) => { setDraft((current) => ({ ...current, ...values })); reset(); };
  const switchMode = (next: "question" | "form") => { setMode(next); reset(); };
  const request = async (url: string, payload: object) => {
    setBusy(true); setError("");
    try {
      const response = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
      const body = await response.json().catch(() => null);
      if (!response.ok) throw new Error(askErrorCode(response.status, body));
      setResolution(body as AskResolution);
    } catch (issue) {
      setError(issue instanceof Error ? issue.message : "unavailable");
    } finally { setBusy(false); }
  };
  const prepare = () => {
    setResolution(null);
    if (mode === "question") void request(API.askInterpret(), { question: question.trim(), locale });
    else void request(API.askResolve(), { plan: draft });
  };
  const search = (offset = 0) => {
    if (resolution?.status === "ready") void request(API.askQuery(), askQueryPayload(resolution, offset));
  };
  const results = resolution?.results;

  return (
    <main className="page-x min-h-screen bg-canvas pb-20 pt-36 text-ink">
      <div className="max-w-4xl">
        <p className="type-label text-ink-subtle">{t("eyebrow")}</p>
        <h1 className="mt-3 type-display-editorial">{t("title")}</h1>
        <p className="mt-5 max-w-2xl leading-7 text-ink-muted">{t("description")}</p>
        <div className="my-7 flex flex-wrap gap-3" role="group" aria-label={t("mode")}>
          <Button disabled={busy} aria-pressed={mode === "question"} variant={mode === "question" ? "primary" : "secondary"} onClick={() => switchMode("question")}>{t("questionMode")}</Button>
          <Button disabled={busy} aria-pressed={mode === "form"} variant={mode === "form" ? "primary" : "secondary"} onClick={() => switchMode("form")}>{t("formMode")}</Button>
        </div>
        {status.error && <InlineFeedback tone="warning">{t("statusFailed")} <Button onClick={() => void status.mutate()}>{t("retry")}</Button></InlineFeedback>}
        {status.data?.configured === false && <InlineFeedback tone="warning">{t("noKey")} <Link href="/settings" className="focus-ring underline">{t("settings")}</Link></InlineFeedback>}
        <form onSubmit={(event) => { event.preventDefault(); prepare(); }} className="mt-6 space-y-6">
          {mode === "question" ? <>
            <FormField label={t("questionLabel")} description={t("privacy")}>
              <TextArea value={question} maxLength={600} rows={3} disabled={busy} onChange={(event) => { setQuestion(event.target.value); reset(); }} placeholder={t("example")} />
            </FormField>
            <button type="button" disabled={busy} className="focus-ring text-left text-sm text-ink-subtle underline" onClick={() => { setQuestion(t("example")); reset(); }}>{t("useExample")}</button>
          </> : <div className="grid gap-5 sm:grid-cols-2">
            <FormField label={t("fields.genre")}><TextInput value={draft.genre ?? ""} maxLength={100} disabled={busy} onChange={(event) => change({ genre: event.target.value || null })} placeholder={t("genreExample")} /></FormField>
            <FormField label={t("fields.country")}><TextInput value={draft.country ?? ""} maxLength={100} disabled={busy} onChange={(event) => change({ country: event.target.value || null })} placeholder={t("countryExample")} /></FormField>
            <FormField label={t("fields.person")}><TextInput value={draft.person ?? ""} maxLength={100} disabled={busy} onChange={(event) => change({ person: event.target.value || null, ...(!event.target.value ? { person_role: "any" as const } : {}) })} placeholder={t("personExample")} /></FormField>
            <FormField label={t("role")}><Select value={draft.person_role} disabled={busy || !draft.person} onChange={(event) => change({ person_role: event.target.value as AskPlan["person_role"] })}>
              {(["any", "director", "actor"] as const).map((value) => <option key={value} value={value}>{t(`roles.${value}`)}</option>)}
            </Select></FormField>
            <FormField label={t("fields.decade")} description={t("decadeHelp")}><TextInput type="number" min={1880} max={2190} step={10} value={draft.decade ?? ""} disabled={busy} onChange={(event) => change({ decade: event.target.value ? Number(event.target.value) : null })} placeholder="1990" /></FormField>
            <FormField label={t("view")}><Select value={draft.view} disabled={busy} onChange={(event) => change({ view: event.target.value as AskPlan["view"] })}>
              {(["all", "watched", "unwatched"] as const).map((value) => <option key={value} value={value}>{t(`views.${value}`)}</option>)}
            </Select></FormField>
            <FormField label={t("sort")}><Select value={`${draft.sort}:${draft.direction}`} disabled={busy} onChange={(event) => { const [sort, direction] = event.target.value.split(":"); change({ sort: sort as AskPlan["sort"], direction: direction as AskPlan["direction"] }); }}>
              <option value="title:asc">{t("sorts.titleAsc")}</option><option value="title:desc">{t("sorts.titleDesc")}</option><option value="year:desc">{t("sorts.yearDesc")}</option><option value="year:asc">{t("sorts.yearAsc")}</option>
            </Select></FormField>
          </div>}
          <p className="text-sm leading-6 text-ink-subtle">{t("supported")}</p>
          <Button type="submit" busy={busy} disabled={busy || (mode === "question" && (!question.trim() || !status.data?.configured))} variant="primary">{mode === "question" ? t("interpret") : t("preview")}</Button>
        </form>
        {error && <div className="mt-6"><InlineFeedback tone="error">{t(`errors.${["ask_not_configured", "ask_private_input", "ask_busy", "ask_timeout", "ask_invalid_response", "ask_provider_unavailable", "ask_invalid_selection", "projection_unavailable", "invalid_request"].includes(error) ? error : "unavailable"}`)}</InlineFeedback></div>}
        {resolution && <section className="mt-10 space-y-5 border-y border-line py-7" aria-label={t("preview")} aria-live="polite">
          <h2 className="type-section-title">{t("preview")}</h2>
          {(resolution.status === "unsupported" || resolution.status === "clarify") && <InlineFeedback tone="warning">{t(resolution.status)}</InlineFeedback>}
          {resolution.plan && <>
            <p className="text-sm text-ink-subtle">{t("confirmHint")}</p>
            <div className="flex flex-wrap gap-3">
              {resolution.constraints.map((constraint) => <span key={constraint.dimension} className="max-w-full break-words border border-line-strong px-3 py-2 text-sm">
                {t(`fields.${constraint.dimension}`)}: {formatExploreFacetLabel(constraint.dimension, constraint.key, constraint.label, locale)}
                {constraint.role && ` · ${t(`roles.${constraint.role}`)}`}
              </span>)}
              <span className="border border-line-strong px-3 py-2 text-sm">{t(`views.${resolution.plan.view}`)}</span>
              <span className="border border-line-strong px-3 py-2 text-sm">{t("sort")}: {t(`fields.${resolution.plan.sort}`)} · {t(resolution.plan.direction)}</span>
            </div>
            {resolution.issues.map((issue) => <div key={issue.field} className="space-y-3">
              <InlineFeedback tone="warning">{t(`fields.${issue.field}`)}: {resolution.plan![issue.field]} · {t(issue.code)}</InlineFeedback>
              <div className="grid gap-2 sm:grid-cols-2">
                {issue.candidates.map((candidate) => <Button key={candidate.key} disabled={busy} className="h-auto justify-start whitespace-normal py-3 text-left normal-case" onClick={() => void request(API.askResolve(), { plan: resolution.plan, person_id: candidate.key })}>
                  <span className="min-w-0 break-words">{candidate.label}<span className="mt-1 block text-xs font-normal text-ink-subtle">{candidate.films.map((film) => `${film.title}${film.year ? ` (${film.year})` : ""}`).join(" · ")}</span></span>
                </Button>)}
              </div>
            </div>)}
            <div className="flex flex-wrap gap-3">
              <Button variant="primary" disabled={busy || resolution.status !== "ready"} busy={busy} onClick={() => search()}>{t("search")}</Button>
              <Button disabled={busy} onClick={() => { setDraft(resolution.plan!); switchMode("form"); }}>{t("editFilters")}</Button>
            </div>
          </>}
        </section>}
      </div>
      {results && <section className="mt-10 space-y-6" aria-label={t("results")} aria-busy={busy}>
        <h2 className="type-section-title" role="status">{t("resultCount", { count: results.total })}</h2>
        {results.total === 0 && <p className="text-ink-muted">{t("empty")}</p>}
        <div className="grid gap-x-6 gap-y-10 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {results.items.map(({ film, matched_facts }) => <div key={`${film.id}:${film.profile_state.updated_at || "initial"}`} className="min-w-0">
            <LibraryMovieCard movie={film} readOnly />
            <div className="mt-3 space-y-2 border-t border-line pt-3 text-xs leading-5 text-ink-muted">
              <p className="font-bold">{t("why")}</p>
              {matched_facts.map((fact) => <p key={`${fact.dimension}:${fact.key}`} className="break-words">
                {t(`fields.${fact.dimension}`)}: {formatExploreFacetLabel(fact.dimension, fact.key, fact.label, locale)}
                {fact.dimension === "person" && ` · ${t(`roles.${resolution!.plan!.person_role}`)}`}
                {fact.source_kind && <span className="ml-1 text-ink-subtle">({t("source", { source: t(`sources.${fact.source_kind}`) })})</span>}
              </p>)}
              <p>{t(film.profile_state.watched ? "views.watched" : "views.unwatched")}</p>
              {!matched_facts.length && <p>{t("inLibrary")}</p>}
            </div>
          </div>)}
        </div>
        <div className="flex flex-wrap gap-3">
          {results.offset > 0 && <Button disabled={busy} onClick={() => search(Math.max(0, results.offset - 20))}>{t("previous")}</Button>}
          {results.next_offset !== null && <Button disabled={busy} onClick={() => search(results.next_offset!)}>{t("next")}</Button>}
        </div>
      </section>}
    </main>
  );
}
