import useSWR from "swr";

import { API } from "@/lib/api";
import type { DnaQuery } from "@/lib/cinema-dna";
import type { DnaContributorPage, DnaFacetPage, DnaOverview } from "@/types/cinema-dna";

export function useCinemaDna(query: DnaQuery) {
  const overview = useSWR<DnaOverview>(API.cinemaDna());
  const facets = useSWR<DnaFacetPage>(API.cinemaDnaFacets(query.dimension, query.metric, query.offset));
  const contributors = useSWR<DnaContributorPage>(query.facet
    ? API.cinemaDnaContributors(query.dimension, query.facet, query.metric, query.contributorsOffset)
    : null);
  return { overview, facets, contributors };
}
