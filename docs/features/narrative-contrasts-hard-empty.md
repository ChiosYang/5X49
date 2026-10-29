# Narrative contrasts and local hard no-match results

Status: In Progress
Last updated: 2026-10-29
Related: search-content-boundaries.md

## Goal

Preserve supported story comparisons while keeping explicit metadata requirements
strict, and return locally proven hard no-match results without requiring an
optional semantic provider.

## Scope

- Bounded narrative role/event contrasts, positive focus corrections and
  conjunction-prefixed no-substitution controls.
- Strict current metadata eligibility before model-dependent retrieval.
- Snapshot restoration and edits re-check a saved hard-empty proof.
- Unreviewed or uncalibrated rerank models remain unavailable for nonempty scopes.

## Non-goals

No provider activation, model replacement, new production configuration, automatic
source refresh, private-library transfer or change to semantic relevance thresholds.

## Behavior contract

A complete referential narrative clause may describe a story event or participant.
Bare country/genre fragments and explicit production/cast/runtime facts keep their
existing hard parsing or clarification behavior. A positive focus correction is
not permission to drop arbitrary content bans. Unsupported mandatory clauses still
stop the request.

A no-substitution instruction is accepted only when the corresponding person/role
requirement is already bound. It cannot invent a director or actor condition.

After full parsing, identity resolution and reference choice, strict current SQL
eligibility may prove that there are no confirmed local candidates. That result is
local and carries semantic.no_match_basis: strict_metadata_eligibility. Missing or
conflicted facts remain ineligible; this is not a claim that their unknown values
are known not to match. A provider error or uncalibrated score never proves empty.

Restoration never infers. An empty snapshot must re-check eligibility; if edits or
new metadata make candidates eligible, it requires a new explicit submission.

## Acceptance criteria

- [x] Paired parser and hard-condition regression tests pass in isolation.
- [x] Empty SQL scope returns locally without calling any provider.
- [x] Nonempty uncalibrated scopes remain explicitly unavailable.
- [x] Restore/edit/data-change cases cannot reuse an obsolete empty proof.
- [ ] Relevant full checks and independent review have no blocking finding.

## Verification evidence

The targeted parser modules passed (31 tests), as did the search, model-contract
and hard-empty modules (36 tests), under disposable-default SQLite and
network/private-file guards. Existing native snapshot recovery assertions remain
unchanged. Full and exact-head CI checks are pending. Detailed private calibration
and diagnostic records remain outside the repository and are not training fixtures.

## Remaining risks

A ranking score is not factual entailment or a calibrated probability. This
change does not establish general semantic admission quality or register a new
score profile. Human judgment and separately frozen quality validation remain
necessary.

