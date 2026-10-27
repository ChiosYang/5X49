# Deterministic search metadata coverage

Status: In Progress
Last updated: 2026-10-27
Related: Unified Explore search; native semantic evaluation remains separate

## Goal

Use imported source facts in the existing search box without depending on AI.

## Audit and scope

- Existing canonical/original/localized titles, stable Person aliases, exact-title
  priority, role combinations and strict unknown-fact SQL are retained.
- NFO and TMDB structured cast previously stopped at ten. Retain supplied credits
  beyond that preview cap without expanding the existing card/metadata previews.
- The database already supported alternative FilmTitle values, but TMDB import
  never supplied them. Append the optional block to the existing explicit details
  request and track its own complete/absent/malformed lifecycle.
- Include effective synopsis text in local literal keyword lookup. Synopsis
  matches are soft text evidence, never director/country/genre/year predicates.
- Kodi typed Film IDs supplement missing legacy scalar IDs conservatively.
- Complete deterministic requests precede loading the optional semantic runtime.
  Invalid evaluation configuration cannot block normal local results; special
  evaluation/edit/reference submissions still require all existing proof.

## Decisions

No schema migration, parser expansion, fuzzy identity merge, UI change or model
call. Projection v3 rebuilds locally from existing canonical data. Historical
truncated credits need a normal explicit source refresh, not invented backfill.
Default runtime and semantic egress/index approval are unchanged. No source scan,
scrape, user database change, evaluation execution or deployment is performed.

Alternative-title country codes do not imply a language. Global TMDB alternatives
use und; only a valid supplied snapshot can withdraw them. Missing or malformed
optional data cannot erase aliases. Localized response titles retain their own
locale-specific withdrawal rules. Primary display-title selection is unchanged.

## Acceptance

- [x] Later-billed actors participate in keyword and role-combination searches.
- [x] Alias refresh/removal is transactional and exact titles remain first.
- [x] Synopsis updates remove stale literal matches and do not satisfy hard facts.
- [x] Exact names and complete conditions remain model-free when AI is unavailable.
- [ ] Targeted and required repository checks pass; independent review and CI pass.

## Verification

Targeted import/projection/parser checks: 119 passed. Final local-first API,
runtime and coverage checks passed; the final 11 new coverage tests and 17
historical protocol tests passed together (28 total). Full backend: 716 tests,
three Windows platform skips, no failures. Python compilation and diff checks
passed. Search browser run: 58 passed, three Forward-readiness failures; after
adding an enabled-control wait, all 15 semantic browser tests passed with all
navigation, result and zero-additional-model-call assertions retained.

The initial shared-contract extension triggered historical protocol guards. It
was removed; completeness now lives in a TMDB-only observation subtype. Shared
contract bytes and original frozen corpus/protocol files are unchanged. Initial
Windows async tests blocked their own loopback socketpair; initialization now
precedes the unchanged per-request network block.

Lockfile-aligned Next/ESLint 16.4.2: 146 frontend unit tests passed, followed
by lint, TypeScript and production build. The workspace initially had 16.3.8
installed. Existing service locks prevented clean installation; an incremental
installation restored the declared versions without stopping that service or
changing dependency declarations/lockfile. Windows root-glob tests passed using
same-drive task-owned temporary directories; their assertions are unchanged.
The browser check preceded dependency alignment; same-head CI must run its full
browser suite with a fresh locked installation before merge. Tests use synthetic source payloads,
temporary databases/NFO files and blocked external network; no user library or
sealed quality labels are test inputs.

## Remaining limitations

Keyword synopsis lookup is literal, not semantic understanding. Unknown metadata
fails required predicates without proving the opposite fact. No new semantic
quality acceptance is claimed; previous failed assessments remain unchanged.

Source format references: [Kodi movie NFO](https://kodi.wiki/view/NFO_files/Movies)
and [TMDB alternative titles](https://developer.themoviedb.org/reference/movie-alternative-titles).
The optional alternative-title block is appended to the existing explicit detail
request; no additional HTTP request or bulk refresh is introduced.
