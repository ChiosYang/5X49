"use client";

import { useEffect, useLayoutEffect, useRef, useSyncExternalStore } from "react";
import { X } from "lucide-react";
import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/Button";
import { discoveryHref, discoveryReason } from "@/lib/discovery-search";
import { correctedExploreOffset, formatExploreFacetLabel, parseExploreQuery } from "@/lib/explore";
import { emptySearchPlan, formatSearchRange, removePersonSelection, removeSearchCondition, type SearchPlan } from "@/lib/search-plan";
import { ResultStage } from "../ExploreViews";
import type { ConditionResultsProps } from "./ConditionSearchResults";
import { useDiscoverySearchSession } from "../DiscoverySearchSession";

const subscribe = () => () => {};
export default function ExtendedConditionResults({ query, resolution, state, locale, pending, navigate, replace, plan }:
  ConditionResultsProps & { plan: SearchPlan }) {
  const t = useTranslations("Discovery"), exploreT = useTranslations("Explore");
  const session = useDiscoverySearchSession();
  const localized = useSyncExternalStore(subscribe, () => true, () => false);
  const section = useRef<HTMLElement>(null), heading = useRef<HTMLHeadingElement>(null), pageFocus = useRef(false);
  const editing = useRef(false);
  useLayoutEffect(() => { if (!pending) editing.current = false; }, [pending, resolution]);
  const results = resolution.results, offset = state.offset ?? 0;
  const ids = resolution.people_ids ?? {};
  const semantic = resolution.semantic;
  const semanticOrder = state.semanticOrder ?? "relevance";
  const view = parseExploreQuery({ view: plan.view, sort: plan.sort, dir: plan.direction, offset: String(offset) });
  const href = (next = plan, peopleIds = ids, nextOffset = 0, edited = true, order = semanticOrder) =>
    discoveryHref(query, { plan: next, peopleIds, offset: nextOffset, edited, source: state.source,
      semanticSnapshot: resolution.snapshot ?? state.semanticSnapshot, semanticOrder: order });
  function navigateExclusive(target: string) {
    if (pending || editing.current) return false;
    editing.current = true;
    navigate(target);
    return true;
  }
  function edit(next: SearchPlan, peopleIds = ids) {
    if (semantic?.requires_submit) {
      if (pending || editing.current) return;
      editing.current = true;
      void session.submit(query, locale, { people_ids: peopleIds, edited_plan: next, evaluation_only: true,
        ...(semantic.reference_id ? { reference_id: semantic.reference_id } : {}) });
      return;
    }
    if (navigateExclusive(href(next, peopleIds))) pageFocus.current = false;
  }
  useEffect(() => {
    if (pending || !results) return;
    const corrected = correctedExploreOffset(offset, results.total, results.limit);
    if (corrected !== offset) { replace(href(plan, ids, corrected, !!state.edited)); return; }
    if (pageFocus.current) {
      pageFocus.current = false;
      section.current?.scrollIntoView({ block: "start" }); heading.current?.focus({ preventScroll: true });
    }
  });
  return <div className="space-y-8">
    {semantic ? <div className="max-w-2xl space-y-2 text-sm leading-6 text-ink-muted" role="status">
      <p>{t("semanticEvaluation")}</p>
      {semantic.fallback ? <p>{t("semanticFallback")}</p> : null}
    </div> : null}
    <section aria-labelledby="discovery-conditions-title" aria-busy={pending} className="space-y-3 border-b border-line pb-5">
      <h2 id="discovery-conditions-title" className="type-label text-ink-muted">{t(state.edited ? "adjusted" : "conditions")}</h2>
      <div className="flex flex-wrap gap-2">
        {semantic ? <button type="button" disabled={pending} aria-label={t("remove", { condition: semantic.text })}
          onClick={() => navigateExclusive(discoveryHref(query, { plan, peopleIds: ids, edited: true, source: "local" }))}
          className="focus-ring inline-flex min-h-11 max-w-full items-center gap-2 rounded-pill border border-line-strong bg-surface-raised px-3 py-2 text-sm">
          <span className="min-w-0 break-words">{t("contentCondition", { value: semantic.text })}</span><X className="h-3.5 w-3.5 shrink-0" aria-hidden />
        </button> : null}
        {resolution.constraints.map(condition => {
          let label: string;
          if (condition.dimension === "year" || condition.dimension === "duration") {
            const bounds = formatSearchRange(condition);
            label = t(condition.dimension === "year" ? "yearCondition" : "durationCondition", { value: bounds });
          } else if (condition.dimension === "film") {
            label = condition.label;
            if (condition.exclude) label = t("excludedCondition", { value: label });
          } else {
            label = condition.labels?.[locale] ?? formatExploreFacetLabel(condition.dimension, condition.key, condition.label, locale, localized);
            if (condition.dimension === "person" && condition.role !== "any") label = `${t(`roles.${condition.role}`)}: ${label}`;
            if (condition.field === "countries" && plan.countries.length > 1 || condition.field === "genres" && plan.genres.length > 1)
              label = t("alternativeCondition", { value: label });
            if (condition.exclude) label = t("excludedCondition", { value: label });
          }
          return <button key={condition.id} type="button" disabled={pending} aria-label={t("remove", { condition: label })}
            onClick={() => edit(removeSearchCondition(plan, condition.field!, condition.index),
              condition.field === "people" ? removePersonSelection(ids, condition.index!) : ids)}
            className="focus-ring duration-standard inline-flex min-h-11 max-w-full items-center gap-2 rounded-pill border border-line-strong bg-surface-raised px-3 py-2 text-sm hover:bg-surface-hover">
            <span className="min-w-0 break-words">{label}</span><X className="h-3.5 w-3.5 shrink-0" aria-hidden />
          </button>;
        })}
        {plan.view !== "all" ? <button type="button" disabled={pending} aria-label={t("remove", { condition: exploreT(`views.${plan.view}`) })}
          onClick={() => edit({ ...plan, view: "all" })} className="focus-ring inline-flex min-h-11 items-center gap-2 rounded-pill border border-line-strong px-3 py-2 text-sm">
          {exploreT(`views.${plan.view}`)}<X className="h-3.5 w-3.5" aria-hidden />
        </button> : null}
      </div>
      <p className="text-xs leading-5 text-ink-subtle">{t("extendedConditions")}</p>
    </section>
    {resolution.status === "needs_clarification" ? <section aria-live="polite" className="max-w-2xl space-y-4">
      <h2 className="font-serif text-2xl">{t(resolution.issues.some(issue => issue.code === "choose_reference") ? "chooseReference" : "states.needs_clarification")}</h2>
      {resolution.issues.map(issue => <div key={`${issue.field}:${issue.index}`} className="space-y-3">
        <p className="break-words text-sm text-ink-muted">{issue.field === "people" ? plan.people[issue.index!]?.name + " · " : ""}
          {t(issue.code === "choose_reference" ? "chooseReference" : issue.code === "choose_person" ? "choosePerson" : "unknownValue")}</p>
        {issue.candidates.map(person => <Button key={person.key} disabled={pending} className="h-auto min-h-11 w-full justify-start whitespace-normal py-3 text-left normal-case"
          onClick={() => {
            if (semantic?.requires_submit || issue.code === "choose_reference") {
              if (pending || editing.current) return;
              editing.current = true;
              void session.submit(query, locale, { evaluation_only: true,
                people_ids: issue.field === "people" ? { ...ids, [String(issue.index)]: person.key } : ids,
                ...(state.edited ? { edited_plan: plan } : {}),
                ...(issue.code === "choose_reference" ? { reference_id: person.key }
                  : semantic?.reference_id ? { reference_id: semantic.reference_id } : {}) });
            } else navigateExclusive(href(plan, { ...ids, [String(issue.index)]: person.key }, 0, !!state.edited));
          }}>
          {person.label}{person.year ? ` (${person.year})` : ""}{person.films?.length ? ` · ${person.films.map(film => `${film.title}${film.year ? ` (${film.year})` : ""}`).join(" / ")}` : ""}
        </Button>)}
      </div>)}
    </section> : results ? <ResultStage query={view} results={results} pending={pending} locale={locale} localizeCountries={localized}
      hasConditions={resolution.constraints.length > 0 || plan.view !== "all"} controlsDisabled={pending} showMatchedFacts={false} sectionRef={section} headingRef={heading}
      relevance={semantic ? { active: semanticOrder === "relevance", label: t("relevance"),
        onSelect: () => navigateExclusive(href(plan, ids, 0, true, "relevance")) } : undefined}
      onView={value => edit({ ...plan, view: value })}
      onSort={sort => {
        if (semantic) navigateExclusive(href({ ...plan, sort, direction: sort === "year" ? "desc" : "asc" }, ids, 0, true, sort));
        else edit({ ...plan, sort, direction: sort === "year" ? "desc" : "asc" });
      }}
      onDirection={() => edit({ ...plan, direction: plan.direction === "asc" ? "desc" : "asc" })}
      onPage={next => { if (navigateExclusive(href(plan, ids, next, !!state.edited))) pageFocus.current = true; }}
      onClear={() => edit({ ...emptySearchPlan }, {})} /> : <section className="max-w-2xl space-y-3" aria-live="polite">
        <h2 className="font-serif text-2xl">{t(`states.${resolution.status}`)}</h2>
        <p className="text-sm text-ink-muted">{t(`reasons.${discoveryReason(resolution.reason)}`)}</p>
        {semantic?.requires_submit ? <Button disabled={pending} onClick={() => {
          if (pending || editing.current) return;
          editing.current = true;
          void session.submit(query, locale, { people_ids: ids, evaluation_only: true,
            ...(state.edited ? { edited_plan: plan } : {}),
            ...(semantic.reference_id ? { reference_id: semantic.reference_id } : {}) });
        }}>{t("resubmit")}</Button> : null}
      </section>}
  </div>;
}
