export interface IdentityReviewFilm {
  id: string;
  title: string;
  year: number | null;
  lifecycle: string;
  identities: Record<string, string>;
  personal_data: { viewings: number; has_rating: boolean; has_notes: boolean; favorite: boolean };
}

export interface IdentityReviewItem {
  id: string;
  film_id: string;
  display_name: string | null;
  availability: string;
  resolution_status: string;
}

export interface IdentityReviewSummary {
  id: string;
  reason_code: string;
  status: "open" | "resolved" | "dismissed";
  created_at: string;
  resolved_at: string | null;
  film: IdentityReviewFilm | null;
  library_item: IdentityReviewItem | null;
}

export interface IdentityReviewDetail extends IdentityReviewSummary {
  incoming_identities: Record<string, string>;
  evidence_available: boolean;
  candidates_truncated: boolean;
  candidates: Array<{
    film: IdentityReviewFilm | null;
    library_item: IdentityReviewItem | null;
    film_id: string;
    library_item_id: string | null;
    evidence_status: "current" | "changed" | "unavailable";
  }>;
  revision: string;
  actions: string[];
  blocked_code: string | null;
  source_evidence_current: boolean;
}

export interface IdentityDecisionPreview {
  review_id: string;
  action: "keep_separate" | "reconnect";
  confirmation_token: string;
  effects: { film_id: string; source_item_id: string; target_item_id: string | null;
    source_after: string; target_after: string | null; personal_data_unchanged: boolean; files_unchanged: boolean;
    expiring_snapshot_ids: string[] };
}

export interface IdentityReviewPage {
  items: IdentityReviewSummary[];
  total: number;
  limit: number;
  offset: number;
}
