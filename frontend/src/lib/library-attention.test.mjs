import assert from "node:assert/strict";
import test from "node:test";

import { getLibraryAttentionCounts } from "./library-attention.ts";

test("counts only Films needing metadata review and all pending root videos", () => {
  const films = [
    { primary_item: { metadata: { scrape_status: "needs_review" } } },
    { primary_item: { metadata: { scrape_status: "matched" } } },
    { primary_item: { metadata: { scrape_status: "needs_review" } } },
  ];

  assert.deepEqual(getLibraryAttentionCounts(films, 3), {
    metadataReviews: 2,
    rootVideos: 3,
  });
});

test("returns zero counts for an empty Library", () => {
  assert.deepEqual(getLibraryAttentionCounts([], 0), {
    metadataReviews: 0,
    rootVideos: 0,
  });
});
