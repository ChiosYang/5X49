# Source-backed language and metadata enrichment

Status: In Progress
Last updated: 2026-10-27
Related: Unified Explore deterministic search

## Goal

Use source-backed titles, person aliases, complete cast and film-language facts
in the existing search box. Ordinary factual searches remain local.

## Behavior contract

- Original language and spoken dialogue are different facts. TMDB `original_language`
  and `spoken_languages` are retained as separate source snapshots. TMDB `cn` is
  explicitly normalized to `yue`; country, localized titles and edition audio
  never supply language facts. Unsupported NFO language tags remain unknown.
- EN/ZH bounded clauses include `original language English`, `films in Japanese`,
  `原始语言为英语的电影` and `不要日语电影`. Bare `French films` retains its country meaning.
  Positive language clauses are AND requirements, and an exclusion requires known
  data. Missing, explicit empty or conflicting language facts cannot qualify for
  either positive or negative filtering. The results expose missing/conflict counts.
- V2 plans may contain at most eight language clauses; contradictory/duplicate
  clauses are rejected. Old plans omit this optional field. Conditions survive
  URL restoration and can be removed without dropping other hard conditions.
- Language edits use the existing revision/idempotency metadata API. Manual
  values and explicit clears take precedence over automatic refresh; reset
  restores automatic observations. No new editor or external model is required.
- Complete TMDB cast may supplement a short NFO cast without replacing NFO
  directors or curated credits. Display previews remain bounded separately.
  Cast and crew refresh independently; missing/malformed blocks preserve their
  prior observations, valid replacements retract only their source/role.
- Explicit enrichment accepts pre-fetched movie/person responses bound to the
  film's existing public movie ID. Director aliases require the matching official
  person ID, movie credit and role. Alias and translated-title snapshots retract
  only names owned by that source. It performs no network or commit itself.
- Fresh provider IDs require a single-film, single-credit local provisional
  identity without aliases, graph assertions, curated evidence or other providers.
  Shared cross-film provisional IDs remain unresolved. Within that boundary,
  identity links require unique film/role evidence:
  actors require exact name, nonempty character and billing position; directors
  require official person-ID aliases. A local-only single-film director can be
  redirected to an existing verified identity only with that evidence and no
  curated credits, aliases or graph assertions. The old identity, source credits
  and audit event remain; verified identities and mere same-name people never merge.

## Storage and consistency

Schema v12 adds source-owned language and cast-completeness snapshots. The
`library-film.v3` and `film-detail.v3` projections refresh in the same transaction
as source changes, overrides, alias withdrawal and identity links. Normal startup
rebuilds obsolete projections from canonical facts without fetching metadata.
Malformed enrichment rolls back the caller's transaction, including projections.
No import, scan or source update runs automatically merely by importing this helper.

## Delivery boundaries

Development and synthetic browser checks use an isolated checkout and database.
Private source data, cached provider responses, backups and local comparison
results are not repository files. Existing data is not silently refreshed.
Applying the prepared enrichment to an active instance, synchronizing its watched
checkout and service restart/reload arrangements remain a separate operational step.
This deterministic regression work does not establish semantic search quality.

## Verification

- Focused language/source tests cover missing/null/empty/malformed snapshots,
  source conflicts, manual clear/reset, country/language distinctions, literal
  person protection, scoped withdrawal, same-name ambiguity, cast supplementation
  and transactional rollback.
- Frontend tests cover strict language URL validation and independent chip edits.
- Browser tests exercise EN/ZH, 320/1440px, actual local API filtering, unknown
  exclusion, chip removal, refresh and Back with provider requests blocked.
- `python -X utf8 -m unittest discover -s . -p "test_*.py" -q`:
  Baseline full suite before linkage hardening: 734 tests, success with 3
  Windows/platform skips, isolated database and normalized temporary directory.
  Revised linkage/language suite: 20 passed; related source/projection suite: 22 passed.
  Same-head CI runs the complete suite again.
- Frontend: 148 unit tests; lint, typecheck and production build passed.
- Browser: `language-search.spec.ts enhanced-search.spec.ts`: 20 passed.
- Local Docker Compose checks could not execute because Docker is absent; CI
  supplies the Linux/Docker environment. No container/runtime configuration changed.

## Remaining limits

The supported natural-language vocabulary is deliberately bounded; the typed API
accepts ISO 639-1 codes plus `yue`. Labels are source facts, not guarantees about a
particular dubbed media edition. Incomplete or ambiguous person evidence remains
unresolved. No model, private-library egress or production deployment is enabled.
