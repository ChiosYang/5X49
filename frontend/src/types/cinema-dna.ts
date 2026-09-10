export type DnaDimension = "genre" | "person" | "country" | "decade";
export type DnaMetric = "exposure" | "preference";

export interface DnaCoverage {
  total_films: number;
  covered_films: number;
  conflicted_films: number;
  missing_films: number;
}

export interface DnaBase {
  formula_version: string;
  projection_version: string;
  scope: string;
  thresholds: { global_rated_films: number; category_rated_films: number };
  totals: { watched_films: number; viewing_records: number; rated_films: number };
  needed_global_ratings: number;
}

export interface DnaOverview extends DnaBase {
  dimensions: { dimension: DnaDimension; coverage: DnaCoverage }[];
}

export interface DnaFacet {
  key: string;
  label: string;
  film_count: number;
  rated_count: number;
  viewing_count: number;
  denominator: number;
  share: number | null;
  preference: number | null;
  needed_category_ratings: number;
  roles: string[];
  source_kinds: string[];
}

export interface DnaPage<T> extends DnaBase {
  dimension: DnaDimension;
  metric: DnaMetric;
  items: T[];
  total: number;
  limit: number;
  offset: number;
  next_offset: number | null;
}

export interface DnaFacetPage extends DnaPage<DnaFacet> {
  coverage: DnaCoverage;
}

export interface DnaContributor {
  film_id: string;
  title: string;
  year: number | null;
  rating: number | null;
  viewing_count: number;
  in_library: boolean;
  fact: {
    dimension: DnaDimension;
    key: string;
    label: string;
    source: { source_kind?: string | null; policy_version: string; observed_at?: string | null; roles?: string[] };
  };
}

export interface DnaContributorPage extends DnaPage<DnaContributor> {
  key: string;
  facet: DnaFacet | null;
}
