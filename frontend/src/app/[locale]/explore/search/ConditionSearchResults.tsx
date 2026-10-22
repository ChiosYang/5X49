"use client";

import { useEffect, useRef, useSyncExternalStore } from "react";
import { X } from "lucide-react";
import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/Button";
import { emptyAskPlan, removeAskConstraint, type AskPlan } from "@/lib/ask";
import { discoveryHref, type DiscoveryResolution, type DiscoveryState } from "@/lib/discovery-search";
import { correctedExploreOffset, formatExploreFacetLabel, parseExploreQuery } from "@/lib/explore";
import { ResultStage } from "../ExploreViews";
import { isSearchPlan } from "@/lib/search-plan";
import ExtendedConditionResults from "./ExtendedConditionResults";

const subscribe = () => () => {};
export type ConditionResultsProps = {
  query: string; resolution: DiscoveryResolution; state: DiscoveryState; locale: string; pending: boolean;
  navigate: (href: string) => void; replace: (href: string) => void;
};
export default function ConditionSearchResults(props: ConditionResultsProps) {
  return isSearchPlan(props.resolution.plan) ? <ExtendedConditionResults {...props} plan={props.resolution.plan} />
    : <LegacyConditionResults {...props} />;
}
function LegacyConditionResults({ query, resolution, state, locale, pending, navigate, replace }: ConditionResultsProps) {
  const t = useTranslations("Discovery");
  const exploreT = useTranslations("Explore");
  const localized = useSyncExternalStore(subscribe, () => true, () => false);
  const section = useRef<HTMLElement>(null), heading = useRef<HTMLHeadingElement>(null);
  const pageFocus = useRef(false);
  const plan = resolution.plan as AskPlan;
  const results = resolution.results;
  const offset = state.offset ?? 0;
  const view = parseExploreQuery({ view: plan.view, sort: plan.sort, dir: plan.direction, offset: String(offset) });
  for (const condition of resolution.constraints) if (condition.dimension !== "year" && condition.dimension !== "duration") view[condition.dimension].push(condition.key);
  const href = (next: AskPlan, personId = resolution.person_id, nextOffset = 0, edited = true) => discoveryHref(query,
    { plan: next, personId, offset: nextOffset, edited, source: state.source });
  function edit(next: AskPlan, personId = resolution.person_id) {
    pageFocus.current = false; navigate(href(next, personId));
  }
  useEffect(() => {
    if (pending || !results) return;
    const corrected = correctedExploreOffset(offset, results.total, results.limit);
    if (corrected !== offset) { replace(href(plan, resolution.person_id, corrected, state.edited)); return; }
    if (pageFocus.current) {
      pageFocus.current = false;
      section.current?.scrollIntoView({ block: "start" }); heading.current?.focus({ preventScroll: true });
    }
  });
  return <div className="space-y-8">
    <section aria-labelledby="discovery-conditions-title" className="space-y-3 border-b border-line pb-5">
      <h2 id="discovery-conditions-title" className="type-label text-ink-muted">{t(state.edited ? "adjusted" : "conditions")}</h2>
      <div className="flex flex-wrap gap-2">
        {resolution.constraints.map(condition => {
          const dimension = condition.dimension as "genre" | "person" | "country" | "decade";
          const label = formatExploreFacetLabel(dimension, condition.key, condition.label, locale, localized);
          const value = condition.dimension === "person" && plan.person_role !== "any" ? `${t(`roles.${plan.person_role}`)}: ${label}` : label;
          return <button key={`${condition.dimension}:${condition.key}`} type="button" aria-label={t("remove", { condition: value })}
            onClick={() => edit(removeAskConstraint(plan, dimension), dimension === "person" ? null : resolution.person_id)}
            className="focus-ring duration-standard inline-flex min-h-11 max-w-full items-center gap-2 rounded-pill border border-line-strong bg-surface-raised px-3 py-2 text-sm hover:bg-surface-hover">
            <span className="min-w-0 break-words">{value}</span><X className="h-3.5 w-3.5 shrink-0" aria-hidden />
          </button>;
        })}
        {plan.view !== "all" ? <button type="button" aria-label={t("remove", { condition: exploreT(`views.${plan.view}`) })}
          onClick={() => edit({ ...plan, view: "all" })} className="focus-ring inline-flex min-h-11 items-center gap-2 rounded-pill border border-line-strong px-3 py-2 text-sm">
          {exploreT(`views.${plan.view}`)}<X className="h-3.5 w-3.5" aria-hidden />
        </button> : null}
      </div>
      <p className="text-xs leading-5 text-ink-subtle">{t("completeOnly")}</p>
    </section>
    {resolution.status === "needs_clarification" ? <section aria-live="polite" className="max-w-2xl space-y-4">
      <h2 className="font-serif text-2xl">{t("states.needs_clarification")}</h2>
      {resolution.issues.map(issue => <div key={issue.field} className="space-y-3">
        <p className="text-sm text-ink-muted">{t(issue.code === "choose_person" ? "choosePerson" : "unknownValue")}</p>
        {issue.candidates.map(person => <Button key={person.key} className="h-auto min-h-11 w-full justify-start whitespace-normal py-3 text-left normal-case"
          onClick={() => navigate(href(plan, person.key, 0, !!state.edited))}>{person.label} · {person.films.map(film => `${film.title}${film.year ? ` (${film.year})` : ""}`).join(" / ")}</Button>)}
      </div>)}
    </section> : results ? <ResultStage query={view} results={results} pending={pending} locale={locale} localizeCountries={localized}
      sectionRef={section} headingRef={heading} onView={value => edit({ ...plan, view: value })}
      onSort={sort => edit({ ...plan, sort, direction: sort === "year" ? "desc" : "asc" })}
      onDirection={() => edit({ ...plan, direction: plan.direction === "asc" ? "desc" : "asc" })}
      onPage={next => { pageFocus.current = true; navigate(href(plan, resolution.person_id, next, !!state.edited)); }}
      onClear={() => edit({ ...emptyAskPlan }, null)} /> : null}
  </div>;
}
