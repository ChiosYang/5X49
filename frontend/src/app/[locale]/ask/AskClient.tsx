"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import useSWR from "swr";
import { Button } from "@/components/ui/Button";
import { FormField, Select, TextArea, TextInput } from "@/components/ui/FormControls";
import { InlineFeedback } from "@/components/ui/Feedback";
import { Link } from "@/i18n/routing";
import { API } from "@/lib/api";
import { ASK_SESSION_KEY, parseAskSession, removeAskConstraint, askErrorCode, askQueryPayload, emptyAskPlan,
  validAskNumbers, askNumericConditions, createAskRequestGate, askInterpretPayload, askExploreSessionKey, type AskPlan, type AskResolution, type AskObservation } from "@/lib/ask";
import { exploreLocationContext, formatExploreFacetLabel } from "@/lib/explore";
import type { ExploreDimension } from "@/types/movie";
import ExploreFactFinder from "../explore/ExploreFactFinder";
import LibraryMovieCard from "../library/LibraryMovieCard";

interface AskStatus { configured: boolean; model: string | null; provider_host: string | null; disclosure_id: string | null }

export default function AskClient({ embedded = false, contextKey = "/explore", onActiveChange }: { embedded?: boolean; contextKey?: string; onActiveChange?: (active: boolean) => void }) {
  const t = useTranslations("Ask");
  const locale = useLocale();
  const status = useSWR<AskStatus>(API.askStatus(), { revalidateOnFocus: true, focusThrottleInterval: 0, dedupingInterval: 0 });
  const refreshStatus = status.mutate;
  const [sessionKey, setSessionKey] = useState<string | null>(embedded ? null : ASK_SESSION_KEY);
  const [sessionReady, setSessionReady] = useState(!embedded);
  const sessionScope = useRef<string | null>(null);
  const [chosenMode, setMode] = useState<"question" | "form" | null>(null);
  const mode = chosenMode ?? (embedded || status.data?.configured ? "question" : "form");
  const [finder, setFinder] = useState<ExploreDimension | null>(null);
  const [personId, setPersonId] = useState<string | null>(null);
  const gate = useRef(createAskRequestGate());
  const restored = useRef<string | null>(null);
  const lastAttempt = useRef<{ url: string; payload: object } | null>(null);
  const [retryKind, setRetryKind] = useState<"interpret" | "local" | null>(null);
  const [question, setQuestion] = useState("");
  const [composerOpen, setComposerOpen] = useState(false);
  const [consentFor, setConsentFor] = useState<string | null>(null);
  const consentRef = useRef<string | null>(null);
  const updateConsent = useCallback((value: string | null) => { consentRef.current = value; setConsentFor(value); }, []);
  const disclosureId = status.data?.disclosure_id ?? null;
  const configured = status.data?.configured ?? false;
  const disclosure = status.data?.provider_host && status.data.model ? `${status.data.provider_host} / ${status.data.model}` : null;
  const consent = disclosure !== null && disclosureId !== null && consentFor === disclosureId;
  const [draft, setDraft] = useState<AskPlan>({ ...emptyAskPlan });
  const [resolution, setResolution] = useState<AskResolution | null>(null);
  const [observation, setObservation] = useState<AskObservation | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const active = Boolean(resolution || busy || error || mode === "form" || composerOpen || question.trim());
  const compact = embedded && mode === "question" && !active;

  const clearSaved = () => { try { if (sessionKey) sessionStorage.removeItem(sessionKey); } catch { /* Optional storage. */ } };
  const reset = () => { gate.current.cancel(); setBusy(false); setResolution(null); setError(""); lastAttempt.current = null; setRetryKind(null); clearSaved(); };
  const cancel = () => { reset(); setMode("question"); setDraft({ ...emptyAskPlan }); setPersonId(null); setObservation(null); setQuestion(""); updateConsent(null); setComposerOpen(false); };
  const change = (values: Partial<AskPlan>) => { setMode("form"); if ("person" in values) setPersonId(null); setDraft(current => ({ ...current, ...values })); reset(); };
  const switchMode = (next: "question" | "form") => { setMode(next); setComposerOpen(next === "question"); reset(); };
  const request = useCallback(async (url: string, payload: object) => {
    let currentPayload = payload;
    if (url === API.askInterpret()) {
      try { currentPayload = askInterpretPayload(payload, disclosureId, consentRef.current, configured); }
      catch (issue) { setError(issue instanceof Error ? issue.message : "ask_consent_required"); return; }
    }
    const attempt = gate.current.begin();
    lastAttempt.current = { url, payload: currentPayload }; setRetryKind(url === API.askInterpret() ? "interpret" : "local"); setBusy(true); setError("");
    // Bound browser/proxy hangs as well as the provider timeout. Never retry automatically.
    const timer = setTimeout(() => { if (gate.current.current(attempt.id)) { gate.current.cancel(); setBusy(false); setError("ask_timeout"); } }, 25000);
    try {
      const response = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(currentPayload), signal: attempt.signal });
      const body = await response.json().catch(() => null);
      if (!gate.current.current(attempt.id)) return;
      if (body?.observation || body?.detail?.observation) setObservation(body.observation ?? body.detail.observation);
      if (!response.ok) {
        const code = askErrorCode(response.status, body);
        if (code === "ask_consent_changed") { updateConsent(null); void refreshStatus(); }
        throw new Error(code);
      }
      setResolution(body as AskResolution);
      if (body.plan) { setDraft(body.plan); setPersonId(body.person_id); setMode("form"); }
      if (url === API.askQuery() && body.status === "ready" && body.results) {
        try { if (sessionKey) sessionStorage.setItem(sessionKey, JSON.stringify(askQueryPayload(body, body.results.offset))); } catch { /* Optional storage. */ }
      }
    } catch (issue) {
      if (gate.current.current(attempt.id)) setError(issue instanceof Error ? issue.message : "unavailable");
    } finally { clearTimeout(timer); if (gate.current.current(attempt.id)) setBusy(false); }
  }, [sessionKey, disclosureId, configured, refreshStatus, updateConsent]);
  const prepare = () => {
    setResolution(null); clearSaved();
    if (mode === "question") { setObservation(null); void request(API.askInterpret(), { question: question.trim(), locale, provider_consent: true }); }
    else if (validAskNumbers(draft)) void request(API.askResolve(), { plan: draft, person_id: personId });
    else setError("invalid_request");
  };
  const search = (offset = 0) => { if (resolution?.status === "ready") void request(API.askQuery(), askQueryPayload(resolution, offset)); };
  useEffect(() => {
    if (!embedded) return;
    let mounted = true;
    const establish = () => {
      if (!mounted || exploreLocationContext(window.location.href) !== contextKey) return;
      const state = window.history.state ?? {};
      const prior = state["5x49.ask.context"];
      const entry = prior?.query === contextKey && /^[0-9a-f]{32}$/.test(prior.entry)
        ? prior.entry : Array.from(crypto.getRandomValues(new Uint8Array(16)), byte => byte.toString(16).padStart(2, "0")).join("");
      if (entry !== prior?.entry || prior?.query !== contextKey) {
        window.history.replaceState({ ...state, "5x49.ask.context": { query: contextKey, entry } }, "", window.location.href);
      }
      const next = askExploreSessionKey(contextKey, entry);
      if (sessionScope.current === next) return;
      const changed = sessionScope.current !== null;
      sessionScope.current = next;
      setSessionReady(false);
      // Initial scope discovery must not clobber a focus/input event arriving
      // during hydration. Later history-entry changes deliberately reset it.
      if (changed) {
        gate.current.cancel(); lastAttempt.current = null; setRetryKind(null); setBusy(false); setResolution(null);
        setDraft({ ...emptyAskPlan }); setPersonId(null); setQuestion(""); setMode(null); setComposerOpen(false);
        updateConsent(null); setError(""); setObservation(null);
      }
      setSessionKey(next);
    };
    void Promise.resolve().then(establish);
    window.addEventListener("popstate", establish);
    return () => { mounted = false; window.removeEventListener("popstate", establish); };
  }, [embedded, contextKey, updateConsent]);
  useEffect(() => { onActiveChange?.(active); }, [active, onActiveChange]);
  useEffect(() => {
    const requestGate = gate.current;
    return () => requestGate.cancel();
  }, []);
  useEffect(() => {
    if (!sessionKey || restored.current === sessionKey) return;
    let payload: ReturnType<typeof parseAskSession> = null;
    try { payload = parseAskSession(sessionStorage.getItem(sessionKey)); } catch { /* Optional storage. */ }
    let mounted = true;
    // The persisted plan was already confirmed. Revalidate it locally, never reuse Film data.
    void Promise.resolve().then(() => {
      if (!mounted) return;
      restored.current = sessionKey;
      if (payload) { setMode("form"); setDraft(payload.plan); setPersonId(payload.person_id); void request(API.askQuery(), payload); }
      setSessionReady(true);
    });
    return () => { mounted = false; };
  }, [request, sessionKey]);
  const edit = (plan: AskPlan, selectedPerson: string | null) => {
    const trigger = document.activeElement;
    setDraft(plan); setPersonId(selectedPerson); setMode("form"); reset();
    requestAnimationFrame(() => {
      // The form may render before this frame. Respect a field the user has
      // already focused instead of redirecting their next keystrokes to Genre.
      if (document.activeElement !== trigger && document.activeElement !== document.body) return;
      document.getElementById("ask-form")?.scrollIntoView({ block: "start" });
      document.getElementById("ask-genre")?.focus({ preventScroll: true });
    });
  };
  const results = resolution?.results;
  const Container = embedded ? "section" : "main";

  return (
    <Container className={embedded ? (compact ? "mt-4 min-w-0 text-ink" : "mt-6 min-w-0 border-b border-line pb-8 text-ink") : "page-x min-h-screen bg-canvas pb-20 pt-36 text-ink"} aria-label={embedded ? t("finder") : undefined}>
      <div className="max-w-4xl">
        {!embedded && <><p className="type-label text-ink-subtle">{t("eyebrow")}</p><h1 className="mt-3 type-display-editorial">{t("title")}</h1><p className="mt-5 max-w-2xl leading-7 text-ink-muted">{t("description")}</p></>}
        {!compact && <div className="my-5 flex flex-wrap gap-3" role="group" aria-label={t("mode")}>
          <Button aria-pressed={mode === "question"} variant={mode === "question" ? "primary" : "secondary"} onClick={() => switchMode("question")}>{t("questionMode")}</Button>
          <Button aria-pressed={mode === "form"} variant={mode === "form" ? "primary" : "secondary"} onClick={() => switchMode("form")}>{t("formMode")}</Button>
          {active && <Button onClick={cancel}>{busy ? t("cancelRequest") : t("cancel")}</Button>}
        </div>}
        {busy && mode === "question" && <p className="mb-3 text-xs leading-5 text-ink-subtle">{t("cancelHint")}</p>}
        {mode === "form" && question && <p className="mb-4 break-words text-sm leading-6 text-ink-muted">{t("originalQuestion")}: {question}</p>}
        {status.error && <InlineFeedback tone="warning">{t("statusFailed")} <Button onClick={() => void status.mutate()}>{t("retry")}</Button></InlineFeedback>}
        {!compact && status.data?.configured === false && <InlineFeedback tone="warning">{t("noKey")} <Link href="/settings" className="focus-ring underline">{t("settings")}</Link></InlineFeedback>}
        <form id="ask-form" onSubmit={event => { event.preventDefault(); prepare(); }} className={compact ? "flex min-w-0 items-center gap-3" : "mt-5 space-y-5"}>
          {mode === "question" ? <>
            <FormField label={compact ? <span className="sr-only">{t("questionLabel")}</span> : t("questionLabel")} description={compact ? undefined : t("privacy")}>
              <TextArea aria-label={t("questionLabel")} disabled={!sessionReady} value={question} maxLength={600} rows={compact ? 1 : embedded ? 2 : 3} onFocus={() => { if (embedded) setComposerOpen(true); }} onChange={event => { setMode("question"); setQuestion(event.target.value); updateConsent(null); reset(); }} placeholder={compact ? t("compactPlaceholder") : t("example")} />
            </FormField>
            {!compact && <button type="button" className="focus-ring text-left text-sm text-ink-subtle underline" onClick={() => { setQuestion(t("example")); updateConsent(null); reset(); }}>{t("useExample")}</button>}
            {!compact && disclosure && <label className="flex items-start gap-3 text-sm leading-6 text-ink-muted"><input type="checkbox" className="focus-ring mt-1 shrink-0" checked={consent} onChange={event => updateConsent(event.target.checked ? disclosureId : null)} /><span className="min-w-0 break-words">{t("providerConsent", { provider: disclosure })}</span></label>}
          </> : <div className="grid gap-5 sm:grid-cols-2">
            <FormField label={t("fields.genre")}><TextInput id="ask-genre" value={draft.genre ?? ""} maxLength={100} onChange={event => change({ genre: event.target.value || null })} placeholder={t("genreExample")} /></FormField>
            <FormField label={t("fields.country")}><TextInput value={draft.country ?? ""} maxLength={100} onChange={event => change({ country: event.target.value || null })} placeholder={t("countryExample")} /></FormField>
            <FormField label={t("fields.person")}><TextInput value={draft.person ?? ""} maxLength={100} onChange={event => change({ person: event.target.value || null, ...(!event.target.value ? { person_role: "any" as const } : {}) })} placeholder={t("personExample")} /></FormField>
            <FormField label={t("role")}><Select aria-label={t("role")} value={draft.person_role} disabled={!draft.person} onChange={event => change({ person_role: event.target.value as AskPlan["person_role"] })}>{(["any", "director", "actor"] as const).map(value => <option key={value} value={value}>{t(`roles.${value}`)}</option>)}</Select></FormField>
            <FormField label={t("fields.decade")} description={t("decadeHelp")}><TextInput aria-label={t("fields.decade")} type="number" min={1880} max={2190} step={10} value={draft.decade ?? ""} onChange={event => change({ decade: event.target.value ? Number(event.target.value) : null })} placeholder="1990" /></FormField>
            <FormField label={t("view")}><Select aria-label={t("view")} value={draft.view} onChange={event => change({ view: event.target.value as AskPlan["view"] })}>{(["all", "watched", "unwatched"] as const).map(value => <option key={value} value={value}>{t(`views.${value}`)}</option>)}</Select></FormField>
            {(["min", "max"] as const).map(bound => <div key={`duration-${bound}`} className="space-y-2">
              <FormField label={t(`duration_${bound}`)} description={t("durationHelp")}><TextInput aria-label={t(`duration_${bound}`)} type="number" min={1} max={10000} step={1} value={draft[`duration_${bound}`] ?? ""} onChange={event => change({ [`duration_${bound}`]: event.target.value ? Number(event.target.value) : null, ...(!event.target.value ? { [`duration_${bound}_inclusive`]: true } : {}) })} /></FormField>
              <label className="flex items-center gap-2 text-xs text-ink-muted"><input className="focus-ring" type="checkbox" checked={draft[`duration_${bound}_inclusive`]} disabled={draft[`duration_${bound}`] === null} onChange={event => change({ [`duration_${bound}_inclusive`]: event.target.checked })} />{t(`duration_${bound}_inclusive`)}</label>
            </div>)}
            {(["min", "max"] as const).map(bound => <FormField key={`rating-${bound}`} label={t(`rating_${bound}`)} description={t("ratingHelp")}><TextInput aria-label={t(`rating_${bound}`)} type="number" min={1} max={5} step={1} value={draft[`rating_${bound}`] ?? ""} onChange={event => change({ [`rating_${bound}`]: event.target.value ? Number(event.target.value) : null })} /></FormField>)}
            <FormField label={t("sort")}><Select aria-label={t("sort")} value={`${draft.sort}:${draft.direction}`} onChange={event => { const [sort, direction] = event.target.value.split(":"); change({ sort: sort as AskPlan["sort"], direction: direction as AskPlan["direction"] }); }}><option value="title:asc">{t("sorts.titleAsc")}</option><option value="title:desc">{t("sorts.titleDesc")}</option><option value="year:desc">{t("sorts.yearDesc")}</option><option value="year:asc">{t("sorts.yearAsc")}</option></Select></FormField>
          </div>}
          {mode === "form" && <div className="flex flex-wrap gap-2" role="group" aria-label={t("chooseLocal")}>{(["genre", "country", "person", "decade"] as const).map(dimension => <Button key={dimension} onClick={() => setFinder(dimension)}>{t("chooseFact", { field: t(`fields.${dimension}`) })}</Button>)}</div>}
          {!compact && <p className="text-sm leading-6 text-ink-subtle">{t("supported")}</p>}
          {compact ? <Button disabled={!sessionReady} title={status.data?.configured === false ? t("noKey") : undefined} onClick={() => switchMode("form")}>{t("formMode")}</Button> : <Button type="submit" busy={busy} disabled={!sessionReady || busy || (mode === "question" && (!question.trim() || !status.data?.configured || !consent))} variant="primary">{mode === "question" ? t("interpret") : t("preview")}</Button>}
        </form>
        {error && <div role="alert" className="mt-6 space-y-3"><InlineFeedback tone="error">{t(`errors.${["ask_not_configured", "ask_private_input", "ask_busy", "ask_timeout", "ask_invalid_response", "ask_provider_unavailable", "ask_provider_configuration", "ask_consent_required", "ask_consent_changed", "ask_invalid_selection", "projection_unavailable", "invalid_request"].includes(error) ? error : "unavailable"}`)}</InlineFeedback><div className="flex flex-wrap gap-3"><Button disabled={busy || (retryKind === "interpret" && !consent)} onClick={() => { if (lastAttempt.current) void request(lastAttempt.current.url, lastAttempt.current.payload); }}>{t("retry")}</Button><Button onClick={() => switchMode("form")}>{t("formMode")}</Button></div></div>}
        {observation && <p className="mt-5 break-words text-xs leading-5 text-ink-subtle" aria-label={t("usage")}>{t("observation", { model: observation.response_model ?? observation.requested_model ?? t("unknown"), latency: observation.latency_ms === null ? t("unknown") : Math.round(observation.latency_ms), tokens: observation.total_tokens ?? t("unknown"), cost: observation.cost_usd === null ? t("unknownCost") : `$${observation.cost_usd.toFixed(6)}` })}</p>}
        {resolution && <section className="mt-8 space-y-5 border-y border-line py-6" aria-label={t("preview")} aria-live="polite">
          <h2 className="type-section-title">{t("preview")}</h2>
          {(resolution.status === "unsupported" || resolution.status === "clarify") && <InlineFeedback tone="warning">{t(resolution.status)} {resolution.reason && t(`reasons.${resolution.reason}`)}</InlineFeedback>}
          {resolution.plan && <>
            <p className="text-sm text-ink-subtle">{t("confirmHint")}</p>
            <div className="flex flex-wrap gap-3">{resolution.constraints.map(constraint => <span key={constraint.dimension} className="max-w-full break-words border border-line-strong px-3 py-2 text-sm">{t(`fields.${constraint.dimension}`)}: {formatExploreFacetLabel(constraint.dimension, constraint.key, constraint.label, locale)}{constraint.role && ` · ${t(`roles.${constraint.role}`)}`}</span>)}
              {askNumericConditions(resolution.plan).map(condition => <span key={`${condition.field}:${condition.operator}`} className="border border-line-strong px-3 py-2 text-sm">{t(`fields.${condition.field}`)} {condition.operator} {condition.value} {t(condition.field === "duration" ? "minutes" : "stars")}</span>)}
              <span className="border border-line-strong px-3 py-2 text-sm">{t(`views.${resolution.plan.view}`)}</span><span className="border border-line-strong px-3 py-2 text-sm">{t("sort")}: {t(`fields.${resolution.plan.sort}`)} · {t(resolution.plan.direction)}</span>
            </div>
            {resolution.issues.map(issue => <div key={issue.field} className="space-y-3"><InlineFeedback tone="warning">{t(`fields.${issue.field}`)}: {resolution.plan![issue.field]} · {t(issue.code)}</InlineFeedback><div className="grid gap-2 sm:grid-cols-2">{issue.candidates.map(candidate => <Button key={candidate.key} disabled={busy} className="h-auto justify-start whitespace-normal py-3 text-left normal-case" onClick={() => { setPersonId(candidate.key); void request(API.askResolve(), { plan: resolution.plan, person_id: candidate.key }); }}><span className="min-w-0 break-words">{candidate.label}<span className="mt-1 block text-xs font-normal text-ink-subtle">{candidate.films.map(film => `${film.title}${film.year ? ` (${film.year})` : ""}`).join(" · ")}</span></span></Button>)}</div></div>)}
            <div className="flex flex-wrap gap-3"><Button variant="primary" disabled={busy || resolution.status !== "ready"} busy={busy} onClick={() => search()}>{t("search")}</Button><Button onClick={() => edit(resolution.plan!, resolution.person_id)}>{t("editFilters")}</Button></div>
          </>}
        </section>}
      </div>
      {results && <section className="mt-10 space-y-6" aria-label={t("results")} aria-busy={busy}>
        <h2 className="type-section-title" role="status">{t("resultCount", { count: results.total })}</h2>
        {results.total === 0 && <div className="space-y-3"><p className="text-ink-muted">{t("empty")}</p><p className="text-sm text-ink-subtle">{t("removeHint")}</p><div className="flex flex-wrap gap-2">{(["genre", "country", "person", "decade", "view", "duration", "rating"] as const).filter(field => field === "view" ? resolution!.plan!.view !== "all" : field === "duration" || field === "rating" ? resolution!.plan![`${field}_min`] !== null || resolution!.plan![`${field}_max`] !== null : resolution!.plan![field] !== null).map(field => <Button key={field} onClick={() => edit(removeAskConstraint(resolution!.plan!, field), field === "person" ? null : resolution!.person_id)}>{t("removeFilter", { field: field === "view" ? t("view") : t(`fields.${field}`) })}</Button>)}<Button onClick={() => edit(resolution!.plan!, resolution!.person_id)}>{t("editFilters")}</Button></div></div>}
        <div className="grid gap-x-6 gap-y-10 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">{results.items.map(({ film, matched_facts, matched_values }) => <div key={film.id} className="min-w-0"><LibraryMovieCard movie={film} readOnly /><div className="mt-3 space-y-2 border-t border-line pt-3 text-xs leading-5 text-ink-muted"><p className="font-bold">{t("why")}</p>{matched_facts.map(fact => <p key={`${fact.dimension}:${fact.key}`} className="break-words">{t(`fields.${fact.dimension}`)}: {formatExploreFacetLabel(fact.dimension, fact.key, fact.label, locale)}{fact.dimension === "person" && ` · ${t(`roles.${resolution!.plan!.person_role}`)}`}{fact.source_kind && <span className="ml-1 text-ink-subtle">({t("source", { source: t(`sources.${fact.source_kind}`) })})</span>}</p>)}
          {matched_values?.map(fact => <p key={fact.field}>{t(`fields.${fact.field}`)}: {fact.field === "duration" ? t("secondsValue", { value: fact.value }) : t("starsValue", { value: fact.value })} ({t(`valueSources.${fact.source}`)})</p>)}
          <p>{t(film.profile_state.watched ? "views.watched" : "views.unwatched")}</p>{!matched_facts.length && !matched_values?.length && <p>{t("inLibrary")}</p>}</div></div>)}</div>
        <div className="flex flex-wrap gap-3">{results.offset > 0 && <Button disabled={busy} onClick={() => search(Math.max(0, results.offset - 20))}>{t("previous")}</Button>}{results.next_offset !== null && <Button disabled={busy} onClick={() => search(results.next_offset!)}>{t("next")}</Button>}</div>
      </section>}
      <ExploreFactFinder open={finder !== null} dimension={finder ?? "genre"} locale={locale} localizeCountries reducedMotion onDimensionChange={setFinder} onClose={() => setFinder(null)} onSelect={(dimension, item) => { change({ [dimension]: dimension === "decade" ? Number(item.key) : dimension === "country" ? item.key : item.label }); if (dimension === "person") setPersonId(item.key); }} />
    </Container>
  );
}
