# 5X49 Backend API

## Unified Explore search

`POST /explore/search/interpret` accepts `{question,locale:"en"|"zh",allow_ai:false}`
(text 1–600). Simple keywords return `status:"keyword"`; complete local rules return
resolved conditions with no provider call. Only an explicit client submission sets
`allow_ai:true`. If necessary it makes at most one existing Ask transport call, with
zero retries, only text/static schema, confidence >=0.9, literal grounding, complete
JSON and local entity validation. Typing, restoration and refresh never infer.

Responses are `{version:"discovery.v1"|"discovery.v2",status,source:"local"|"ai",reason,plan,
person_id,constraints,issues,results}`. Literal bindings may additionally return
`keyword_query`, the effective local term; the original question remains unchanged.
Statuses: `keyword`, `ready`,
`needs_clarification`, `clarify`, `unsupported`, `unavailable`, `needs_ai`. Plans use
Ask v1's single genre/person/role/country/decade, viewing state and sort remain
compatible. Extended local requests use the explicit v2 contract below. Literal
Person names survive filler/facet parsing; exact identities run directly, while
partial or duplicate names require a candidate choice. Unknown values do not broaden
results. Producer/writer/other unsupported roles and language requirements never
become director or production-country filters. "Produced in France"/"from France"
remain supported country clauses; "in French" is an unsupported language clause.

`POST /explore/search/query` accepts `{question,plan,person_id:null,edited:false,
offset:0}` and returns the same resolved envelope plus the strict Explore page,
40 Films/page. It only queries local data, including on saved-address reload. Offset
is 0–100000; boolean fields are strict. `edited:true` denotes explicit chip/view/sort
correction; the UI identifies adjusted conditions. Missing/conflicted facts never
match and Person roles apply before count/pagination. Unsupported original requests
cannot be converted into partial conditions. Private input fails 422 before any
provider, including home-relative, dot-relative, Windows-rooted, single-leaf
absolute and unprefixed relative media/sidecar paths. Directory separators plus
known extensions distinguish the latter from ordinary slash-containing titles.
Service errors have allowlisted codes, without question/provider bodies.

UI state lives at `/explore/search`, retaining original input and bounded validated
plan. For keyword lookup only, an explicit leading find/找 command is removed from
the effective term; the original input stays in the URL/input, with all inner title
words intact. Ordinary keyword fallback is explicit and labeled. Legacy `/ask` redirects to
Explore; legacy Ask APIs remain compatible (`/ask/status` now reports
`form_available:false`). PR28 is not integrated, merged or closed; its held live
evaluation remains separate. Jev is deferred; no new credential/provider dependency.


### Imported metadata search coverage

Complete local keyword/condition requests run before optional semantic runtime
configuration is loaded. Invalid evaluation configuration cannot block them;
explicit evaluation/edit/reference submissions retain their existing guards.

Local keyword lookup includes the effective synopsis as literal text, in addition
to existing titles and credited names. It does not infer themes, preferences or
hard metadata from synopsis words. Exact title/alias priority remains available
through `rank_exact=true`; strict role/country/year/runtime SQL is unchanged.
Search projection `film-search.v3` rebuilds from canonical data on normal startup
and refreshes transactionally after source edits; no provider request is needed.

Structured NFO/TMDB import retains the supplied cast beyond preview limits;
existing small actor previews remain unchanged. Kodi typed `uniqueid` tags can
supplement missing legacy TMDB/IMDb fields; ambiguous or unknown types are never
guessed. Existing explicit legacy IDs retain precedence.

Future explicit TMDB detail requests append alternative titles to that same
request. Source-backed alternatives use unknown language (`und`), never a
country-to-language guess. A valid complete alternative-title list replaces that
source's alternative snapshot; absent/malformed blocks preserve previous names,
and an explicit empty list retracts them. Other localized titles keep their
existing per-language lifecycle. No translation, name-based person merge, bulk
scrape, AI call, semantic-index rebuild or egress permission is introduced.

Older truncated source imports cannot be reconstructed from projections: the
missing cast/titles become available only on an ordinary explicit source refresh.

### Reliable names and extended local plans

Schema v11 adds source-backed `PersonAlias` records, linked to a stable active
ExternalIdentity, source Film, provenance and supersession. Existing TMDB credit
`name`/`original_name` are retained during the existing metadata flow, with no new
request. Name-only provisional people are never merged or assigned guessed aliases.
Localized Person names carry a normalized response-locale scope. Refreshing one
language withdraws only names removed in that language, preserving other languages;
removing/changing the credited stable identity withdraws all its names from that
Film/source. Original names have the shared `und` scope.
An explicit existing single-Film metadata refresh/scrape can replenish available
names; this change never starts bulk fetching or invents missing translations.
Existing active FilmTitle canonical/original/localized/alternative names are indexed
along with effective title/original_title and credited people. NFKC, case and
whitespace normalization apply; there is no automatic translation, transliteration
or fuzzy identity merge. A known exact Film or Person literal takes precedence over
words that resemble filter syntax. All results deduplicate by canonical ID.
Localized/alternative Film names from another response language survive refresh;
same-language withdrawals retract their old names. Current canonical/original
title selection retains its existing behavior.

`GET /library/films/page` adds optional `rank_exact=false`. Explore sets it true
to prioritize exact title/alias matches before broad literal matches. Existing
Library sorting stays unchanged by default. Source changes refresh the shared
search projection (`film-search.v3`); the new schema rebuilds it locally. Database
backups preserve aliases. The existing portable JSON v1 export still exports only
its documented subset and does not gain Person aliases or an import capability.

Discovery v2 plans require `version:"search-plan.v2"` and expose:

- `genres`, `countries`, `exclude_genres`, `exclude_countries`: at most ten
  literal vocabulary values per array; countries resolve to ISO codes and genres
  to active local concepts. Include arrays mean OR within that dimension.
- `people`: at most eight `{name,role:"any"|"actor"|"director",exclude:false}`
  clauses. Every clause combines with AND, including two roles for one identity.
  Exact canonical names or reliable aliases resolve locally. Partial/duplicate
  names require a choice. No unsupported producer/writer role is reinterpreted.
- `film_ids`, `exclude_film_ids`: optional, default empty; at most eight unique
  canonical Film IDs each. Exact local title/alias bindings supply these, never
  model output. Missing IDs require clarification before SQL executes. Positive
  IDs combine with all other requirements; negative IDs are strictly excluded.
  Old v2 URLs without either array retain their meaning. Restored unedited plans
  must equal the complete locally grounded request; explicit chip edits may remove
  an identity constraint.
- `year_min/max`: strict integers 1870–2100, inclusive, nullable.
- `duration_min/max`: strict integer minutes 1–10000, nullable;
  `duration_min_exclusive/max_exclusive` are strict booleans, default false.
  Duration uses positive primary-edition seconds, then positive metadata minutes;
  comparisons retain seconds. Missing values never satisfy a bound.
- `view`, `sort`, `direction` retain all/watched/unwatched, title/year and asc/desc.
  Reversed/empty ranges, duplicate values, extra keys and invalid types fail 422.

Multiple supported year clauses intersect regardless of order; contradictory
intersections clarify without execution. For example, `1990s before 1995` means
1990–1994, and never silently becomes the whole decade. Clause boundaries preserve
the literal person separately from supported year/runtime/negative-role clauses.

V2 responses add `people_ids:{"0":"person_..."}`. The keys identify the index
of each person clause. `/explore/search/query` accepts that bounded map instead
of v1's `person_id`. Selections must be local candidates for that literal name;
unknown/stale selections cannot broaden the result. All requirements must resolve
before execution. The SQL executor applies all conditions before count/sort/page,
returns 40 Films and clamps a shrunken last page. Negative facets require an
eligible known value for that dimension/role AND absence of the excluded value;
missing/conflicting data cannot prove an exclusion. A zero result stays zero.

Local examples: `Japanese or French films`, `films between 1994 and 1999`,
`films under 90 minutes`, `films not directed by Name`,
`films directed by Name and starring Other Name`, `日本或法国电影`,
`未看1994到1999年电影`, `少于90分钟的电影`, `由甲执导，由乙主演的电影`.
OR across whole clauses, unknown or unconsumed text, language, semantic themes,
subjective recommendations and unsupported roles are rejected/clarified in full.
The input is retained and ordinary keyword fallback stays explicit.

The expanded model schema/transport and completeness gate are available for
offline/mocked evaluation only. Production routing uses local rules for v2;
the existing guarded v1 AI fallback is unchanged. No real-model quality, accuracy,
cost or latency has been validated for the extension. Enabling that model path
requires a separately authorized live-quality evaluation; the PR28 hold is intact.
Restored v1/v2 plans, corrections, paging, refresh and Back/Return never infer.

Complete title wrappers and sentence terminators are resolved against local
identities before content routing. The full literal is checked first, preserving
punctuation-bearing titles. Unknown quoted/exact-only titles remain ordinary
literal searches, not semantic substitutes. Unconsumed qualifiers are not dropped.
Inside the opt-in semantic evaluation, v2 metadata clauses are segmented from
content before the legacy v1 guard. Supported reference expressions bind a local
Film ID and exclude it before retrieval/rerank and again on snapshot restoration.
Unresolved reference identities, unsupported content negation and incomplete
hard clauses produce specific clarification reasons rather than partial results.
Condition edits and identity choices serialize while their navigation is pending;
typing and explicit page navigation remain available, without stale plan overwrites.
See `docs/features/enhanced-search-phase-one.md` for exact verification evidence.

### Native semantic search: internal evaluation only

Ordinary instances retain the local/v1 behavior above. Both host settings
`SEARCH_INTERNAL_EVALUATION=1` and an absolute `SEARCH_EVALUATION_MANIFEST` must
explicitly enable the new runtime. There is no startup indexing, credential
lookup or model request. The selected free NVIDIA APIs permit internal
evaluation, not production or confidential/personal input. No setting silently
relaxes privacy or switches to paid/alternate providers.

The host manifest pins the public corpus or independently reviewed public scalar
values from the persistent test library, exact document/query hashes, separate
index/receipt databases, model revisions and an expiring shared authorization.
Question text and approved public excerpts are the only model inputs. File paths,
metadata overrides, personal notes, ratings and viewing history are excluded.
Historical automatic overview values require their own public-source review;
an edition-level TMDB flag does not establish field-level provenance. A changed
approved scalar invalidates its whitelist until reviewed again.

In this runtime, explicit `POST /explore/search/interpret` submission may use:

- `baseten/mammoth-1:free`, fixed `baseten`, native `/api/v1/systemone`:
  finite keyword/semantic/hybrid/clarify route and factual/exploratory mode.
- `nvidia/nemotron-3.5-embed-8b:free`, fixed `nvidia/bf16`, native embeddings
  with query/passage input type and 4096 dimensions.
- `nvidia/nemotron-3.5-rerank-8b:free`, fixed `nvidia/bf16`, native reranking
  of at most 20 candidates. No chat substitute or decision-generated SQL.

Every endpoint must pass active/zero-price/privacy preflight, with zero-price
ceilings and no fallback. NVIDIA logging consent is scoped to this evaluation.
One durable ledger counts all three APIs against the approved 320-POST maximum.
Unknown billing, malformed usage, changed routing/price or interrupted transport
halts dispatch. IDs/model/provider evidence is saved before usage validation;
known local cancellation/missing key before dispatch records `not_sent`.

Local exact identities and complete factual rules bypass the models. Explicit
EN/ZH content-clause boundaries preserve and execute all hard predicates through
the existing SQL executor. Unsupported/ambiguous hard requirements never become
an approximate positive-only query. Similarity first resolves an exact reference
Film, then compares its indexed content, excluding the reference itself.

The v3 envelope adds `snapshot:"ds_<32 hex>"`, `edited` and `semantic` with
`text,reference_id,route,mode,order,fallback,evaluation_only,indexed_films,
bounded_candidates`. Unevaluated identity choices also set `requires_submit`;
reference issues use `field:"reference",code:"choose_reference"` and bounded
local Film candidates. A choice is an explicit interpret POST with optional
`people_ids`, `reference_id`, `edited_plan` and `evaluation_only:true`.

Restore uses the existing query POST with `semantic_snapshot` and
`semantic_order:"relevance"|"title"|"year"`. It only reads cached vectors/scores,
reapplies current SQL eligibility and clamps a shrinking page. Filter edits,
watching mutations, refresh, Back/Return and sort never rerun a model. Snapshots
are question/model/policy/corpus bound, expire after at most 24 hours and are
limited to 100. Expired/stale/configuration failures retain ordinary keyword
search and explain the problem; rerank failures explicitly disclose cached
local ranking. A snapshot can never fall through to legacy chat interpretation.

Removing the content chip sends `semantic_removed:true` with `edited:true` and
the original `semantic_snapshot`. The token stays in the URL as proof, but no
content ranking/banner is retained. The server verifies the question, model,
policy and corpus binding, then executes all retained conditions through strict
local SQL. Missing/invalid proof is rejected; `edited` alone never authorizes
discarding arbitrary content. Bound-title edits similarly revalidate the complete
original literal request before executing the explicitly corrected plan.
Cancellation owners use 128 bits from browser `crypto.getRandomValues`, including
HTTP LAN origins without `randomUUID`; if secure entropy is unavailable, the
optional request ID is null and abort/disconnect cancellation still applies.

`POST /explore/search/index` is disabled outside that host configuration. Its
body is `{action:"begin"|"status"|"step"|"resume"|"cancel",job_id:null|"idx_<32 hex>"}`.
Begin/status/cancel/resume are local. Only an explicit step encodes a batch of at
most four approved chunks. Returned vectors are durable before cancellation;
publish the new active generation only when complete. Provider/model/text hashes
control reuse, and the canonical database is never written by the indexer.

These contracts and real interface checks do not establish unseen quality or
production readiness. See `docs/features/semantic-search-integration.md` for
the frozen configuration, independent validation and outstanding restrictions.

## Multiple media roots and scan coverage

`GET /settings/media-dirs` returns `{media_dirs: string[], roots: [{id, path,
state}]}`. The list is ordered; each opaque root ID is stable for its canonical
path. Availability is checked now, separately from the last scan. States are
`accessible`, `offline`, `permission_denied`, or `unavailable`.

`PUT /settings/media-dirs` accepts `{"media_dirs":["/media/movies","/archive"]}`.
Use absolute paths visible to the backend host; at most 32 roots are allowed.
Saving canonicalizes root aliases, deduplicates identical roots in order and
rejects parent/child overlaps with 400. Offline paths may be saved. An empty list
disables media access and scans. Saving does not scan or migrate files. Removing
a root stops future access/queued work and watching, while retaining its Films,
editions, manual corrections, Film reviews and Viewing records. Configuration
read failure fails closed instead of restoring a revoked environment root.

Legacy `GET /settings/media-dir` reports the first root. Its existing `PUT` still
requires an accessible directory and replaces only the first root, preserving
the others and applying overlap validation. When no list is saved, the old
`media_dir` setting or `MEDIA_DIR` environment value supplies the single root.
The root organizer UI continues to use the first root; automatic watchers use
their own root. Container users must mount each configured root separately.

`POST /library/scan` (also `/library/reconcile` and `/sys/scan-library`) queues
recursive discovery across all saved roots, including direct-root videos and
existing per-video NFO/multipart rules. The optional `media_dir` parameter selects
one **already configured exact root**, never an arbitrary path. No roots returns
400. Offline roots are queued so their failure appears in the result.
`POST /library/scan-folder?folder_path=...` requires a current configured root.
Queued root IDs/path manifests and refresh/file-write/identity operations are
revalidated against the current configuration before use. Removing and later
re-adding a root does not change Film or edition IDs.

`GET /library/sync/status` retains its `sync` and `watcher` containers. The sync
`last_result` adds `complete`, `incomplete_roots` and `roots` to `scanned`, `added`,
`missing`. Each root has `id,state,scanned,added,errors,skipped_links`. Root states
are `not_scanned`, `running`, `complete`, `partial`, `offline`,
`permission_denied`, `unavailable`, or `interrupted`. `scanned` counts observed
editions; `added` counts committed new editions after a successful root batch.
A failed persistence batch can leave `scanned` positive and `added` zero.
Missing is a whole-run
count. The last receipt survives restart; an unfinished receipt becomes
interrupted. `watcher.roots` reports each configured root and its current state.

Any inaccessible root, parse/traversal/persistence failure, or cancellation
suppresses missing reconciliation for that run. Positive discoveries may remain.
Only fully covered roots followed by successful enumeration proving a locator
absent can mark that edition missing. Existing-but-unparsed files, removed roots,
and inaccessible paths are never deletion evidence. Nothing here deletes records
or files. Same-Film reconnection and manual-correction cross-Film guards remain.

Scanning and watching skip hidden directories, symlinks and Windows junctions;
link aliases/cycles are not additional editions. A root/ancestor replaced with a
link after saving becomes unavailable. Artwork URLs use
`/media/_roots/{root_id}/{full-relative-path}` so nested/same-named folders cannot
collide. The legacy `/media/{relative-path}` route remains first-root compatible.
Both routes reject either OS's traversal/drive syntax and links. Namespaced URLs
immediately return 404 for removed roots; legacy relative URLs always resolve
against the current first root and cannot identify a previously configured root.
As with existing pathname-based operations, an
adversarial filesystem mutation between validation and OS access is not an atomic
cross-platform filesystem sandbox.

## Deterministic Library filters

`GET /library/films/page` combines every supplied condition with AND before
counting, sorting or pagination. Existing `q`, `filter=all|watched|unwatched|favorite`,
`sort=title|added|duration`, `direction`, `metadata_status`, `limit` and `offset`
remain supported. `favorite=true` independently narrows watched/unwatched results.
The response shape is unchanged.

- `duration_min` / `duration_max`: integer minutes, 1–10000. Compare against the
  primary edition's positive measured seconds, falling back to positive Film
  runtime minutes. Do not round measured seconds before comparison. Duration
  sorting uses this same value; unknown durations remain last in either direction.
- `year_min` / `year_max`: integer years, 1870–2100. Use the effective Film year,
  including a manually protected value or protected null, never the automatic
  source underneath an override.
- `rating_min` / `rating_max`: integer stars, 1–5, from FilmProfileState's personal
  overall rating only. External scores and per-Viewing reviews are independent
  and never substitute for a missing personal overall rating.
- Bounds are inclusive; omit either for an open bound. A Film with an unknown
  value is excluded only when a bound for that value is supplied. Without range
  conditions, unknown values remain eligible. A malformed/out-of-domain value or
  lower bound greater than upper bound returns 422. No writes/provider calls occur.
- `total` counts the entire intersection, `library_total` and `metadata_reviews`
  remain global. Pagination is bounded, stale offsets clamp to the final page,
  and sort ties retain the existing title/year/Film ID order.

The Library UI stores applied conditions in the URL. Apply resets pagination;
sort and care navigation preserve conditions. Clear all removes search, watched,
favorite and all three ranges, preserves sorting and returns to page one. Search offers a
Library handoff retaining `q`. Invalid URL ranges display an error without an
unfiltered result grid. Unsaved form drafts do not filter results.

## Identity review and conservative decisions

`GET /library/identity-reviews` lists identity/reconnection reviews, separately
from TMDB metadata candidates. Query: `status=open|resolved|dismissed|all`
(default open), `limit=1..100` (default 40), `offset=0..1000000`. Response:
`items,total,limit,offset`, ordered by creation time then opaque review ID.

`GET /library/identity-reviews/{review_id}` accepts `irev_<32 lowercase hex>`.
Invalid ID is 422; absent review is 404. Summary fields are `id,reason_code,status,
created_at,resolved_at,film,library_item`. Detail adds `incoming_identities`,
`evidence_available`, `candidates`, `candidates_truncated`, `source_evidence_current`,
`blocked_code`, `revision`, and `actions`.
Film previews contain title/year/lifecycle, safe TMDB/IMDb IDs and personal-data
counts/flags, never notes content. Candidate previews include Film/edition IDs,
summaries and `evidence_status=current|changed|unavailable` compared to captured
database state. They do not verify live file availability. Unrecognized reasons
are returned as `unknown`.

Schema v7 retains at most 50 candidates for newly created reviews. Older reviews
have `evidence_available=false`; original candidates cannot be inferred from a
hash. Truncated evidence is explicitly marked. All reads are side-effect free.
`actions` contains eligible `keep_separate` and/or `reconnect` actions, or is empty
with a `blocked_code`. Identity conflicts, unknown reasons, historical/incomplete
evidence and changed candidate/source records are inspection-only. Cross-Film
merge, split, provider reassignment and personal-data transfers are not exposed.

`POST /library/identity-reviews/{review_id}/preview` takes
`{"action":"keep_separate"}` or `{"action":"reconnect","target_item_id":"lib_..."}`.
It reads files under the configured root and returns `review_id,action,effects,
confirmation_token`. Effects identify the Film, source/target editions, resulting
availability, and preserved personal records/files. Preview writes nothing.

- `keep_separate` closes the review as `dismissed`, preserving all editions and
  identities. It verifies the observed source file before allowing confirmation.
- `reconnect` requires a captured target in the same Film/profile, a single video
  on each edition, a missing old path, and matching retained complete file hashes.
  It keeps the old target edition ID, attaches the new locator/assets, and retains
  the discovery edition/assets as retired history. Ratings, favorites, notes and
  Viewing rows remain on the same Film. A preferred edition pointing to the
  retired discovery is redirected to the preserved target edition. No media file
  is moved/deleted and no identity, metadata or personal record is merged.
  `effects.expiring_snapshot_ids` lists earlier undo snapshots tied to these two
  editions. Reconnect expires them atomically while retaining their history, so
  an old file-organization undo cannot move the reconnected file. Undo restores
  acquire the same lock and reject expired snapshots even with an old token.

`POST /library/identity-reviews/{review_id}/confirm` takes the preview request plus
its `confirmation_token` (64 lowercase hex) and `idempotency_key` (16..64 ASCII
letters, digits, underscore or hyphen). It revalidates evidence and live files,
then commits the decision, edition references and `IdentityReviewDecided` event
in one SQLite transaction. Response: `review_id,status,action,film_id,
library_item_id,event_id`. Same key/payload replay returns the exact saved response;
changed reuse gives `idempotency_conflict`, another key on a closed review gives
`already_decided`. Confirmations serialize with competing scan writes.

Invalid requests return 422, missing reviews 404, and state/file conflicts 409
with `detail.code` (for example `stale_review`, `evidence_missing`,
`identity_conflict_read_only`, `target_file_exists`, `full_hash_required`,
`source_file_changed`, `unsafe_locator`). Clients must refresh/preview after a
conflict. A network retry must reuse the same confirmation payload/key. Unknown
fields are rejected. Decisions never invoke metadata providers or modify files.

This document describes the Fresh Canonical resource API. The backend normally
listens on `http://127.0.0.1:8000`; the frontend proxies `/api/*` and `/media/*`
from port `5549`.

The staged Graph, Workflow and portability interfaces are tracked in
`docs/features/cinema-knowledge-architecture.md`. They are added here only when
their implementation slice is complete; the feature document is not a runtime
compatibility promise.

## Resource IDs

- Film IDs use `film_<32 lowercase hex>`.
- LibraryItem IDs use `lib_<32 lowercase hex>`.
- OperationSnapshot IDs use `snap_<32 lowercase hex>`.
- Film is the stable public work identity. A Film may own several LibraryItems.
- LibraryItem is used only for a concrete local edition or source item.

There are no Movie IDs, aliases, compatibility responses, or selectable read
sources. Invalid resource IDs return `400`; missing resources return `404`.

## Core and settings

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Process health. |
| `GET` | `/diagnostics` | Read-only database/schema, projection readiness, media access, estimated backup space and credential-presence checks. No private paths or secret values. |
| `GET` | `/diagnostics/providers` | Explicit bounded real TMDB detail and poster reads; reports only safe states and HTTP codes, preserving proxy/CA trust. |
| `GET` | `/` | Service information. |
| `GET` | `/settings` | Combined non-secret settings. |
| `GET/PUT` | `/settings/model` | Analysis and Ask model selection. |
| `GET/PUT` | `/settings/media-dir` | Local media root and non-secret availability. `PUT` requires an existing readable directory and applies immediately without an application restart. |
| `GET/PUT` | `/settings/media-dirs` | Ordered canonical roots and independent current accessibility; saving does not scan. |
| `GET` | `/media/{relative_path}` | Serve a file from the current media root with traversal and symlink-escape protection. |
| `GET/PUT` | `/settings/language` | Application language. |
| `GET/PUT` | `/settings/artwork-language` | Preferred artwork language. |
| `GET/PUT` | `/settings/library-watch` | Filesystem watcher state. |
| `GET/PUT` | `/settings/auto-organize-root` | Root-video automation. |
| `GET/PUT` | `/settings/scrape-confirmation` | Require confirmation before scraping. |
| `GET/PUT` | `/settings/tmdb` | TMDB configuration state/write. Reads never expose the secret. |
| `POST` | `/settings/tmdb/test` | Test TMDB access. |
| `GET/PUT` | `/settings/base-url` | OpenAI-compatible endpoint setting. |
| `POST` | `/settings/models/refresh` | Refresh model catalog. |
| `GET` | `/settings/test-api-key` | Test the configured analysis provider. |

`GET /settings/media-dir` returns the configured path without enumerating its
contents or exposing settings secrets:

```json
{
  "media_dir": "/media",
  "exists": true,
  "readable": true
}
```

`readable` is true only when the path exists, is a directory, and is readable by
the backend process. A successful `PUT` includes the same three fields plus its
existing `status` and `message` fields. Invalid targets return `400` with an
actionable `detail` string.

### Settings persistence and autosave boundaries

Existing preference PUT endpoints keep their request/response shapes. Each
preference setter writes only its owned Setting rows in one transaction; directory
writes update `media_dirs` and legacy `media_dir` together. Concurrent Base URL,
model, TMDB key and other preference saves do not replay a whole-settings snapshot
or delete unrelated rows. Clearing the TMDB key removes only that key.

Reading Base URL and ordinary preferences, and saving preferences, do not refresh
the model catalog or test provider credentials. Model-catalog reads/explicit
refresh and connection-test endpoints retain their separate behavior.

## Library Films

### `GET /library/films`

Returns `LibraryFilmSummary[]`, one row per visible Film. Each row includes the
selected title and metadata, `primary_item`, profile state, external scores and
analysis status. Films whose only editions are ignored are omitted. The
optional `q` query parameter filters the synchronous local search projection.

Primary edition selection is deterministic:

1. `available` before `missing` and `ignored`;
2. the explicitly selected default edition;
3. an edition with a present main video first;
4. `added_at` ascending, then LibraryItem ID ascending. Repeat scans do not change
   the default merely by updating observation timestamps.

Schema v6 preserves the previously projected default as an initial preference
when upgrading, without changing ratings or notes. Library/detail projections
advance to `library-film.v2` / `film-detail.v2` and rebuild before serving.

### `GET /library/films/page`

Bounded Library/search reads, while `/library/films` retains its array response.
Parameters: `q` (up to 200 characters), `filter=all|watched|unwatched|favorite`,
`sort=title|added|duration`, `direction=asc|desc`,
`metadata_status=all|pending|needs_review|failed|matched`, `limit=1..100` (default
40), and `offset=0..1000000`. Unknown sort values remain last in either direction;
ties use normalized title, year and Film ID. Filtering and search happen before
pagination. Literal wildcard characters do not broaden searches.

Returns `{items,total,library_total,metadata_reviews,limit,offset}`. The latter
two counts cover the whole visible library; `total` covers the requested filters.
An offset beyond the final page is clamped to the last valid page, or zero for
an empty result. Projection failure remains `503 projection_unavailable`.

### `PUT /films/{film_id}/primary-edition`

Body: `{"library_item_id":"lib_<32 lowercase hex>"}`. Returns the updated Film
detail. Selection belongs to the local profile and survives scans and restart.
The edition must belong to the requested active Film (`404` otherwise) and be
available (`409` otherwise). Missing/ignored preferences fall back to an available
edition while retaining the preference. Invalid IDs return `400`.

Scanning emits one edition per independent same-folder video, with stem-matched
NFO first, then `movie.nfo`. Another video's NFO is never reused in multi-video
folders. Common sample/trailer/teaser/featurette suffixes are excluded. Contiguous
CD/Disc/Disk/Part sequences starting at 1 form one edition unless every part has
its own NFO; `video.part_files` reports safe filenames. Edition source keys use
the video locator; existing folder-key editions are matched by their exact video
locator and retain their IDs and scrape state.

### Diagnostic boundaries

Local diagnostics do not migrate/rebuild, contact providers or validate every
projection hash. They report schema readiness, SQLite quick-check and eight
projection-state/version checks. The space estimate is not a backup guarantee.
The provider probe reads fixed TMDB Film `5511` and its small poster once each,
with timeouts, rate limiting, no redirects and normal TLS verification. States
include `not_configured`, `credentials_rejected`, `access_denied`, `rate_limited`,
`tls_failed`, `proxy_failed`, `timeout`, `connection_failed`, `invalid_response`,
`no_artwork`, `not_checked`, `unavailable` and `ready`. It never returns exception
strings, provider bodies or request URLs. Backend access does not certify browser
proxy-CA trust. Full backup/restore and portable export remain the existing CLI
capabilities, with guidance in Settings → Diagnostics and backups.

### `GET /library/films/{film_id}`

Returns `LibraryFilmDetail`, including every non-retired `LibraryEdition` for
the Film, selected structured metadata, profile state, scores and analysis
status.

Both Film endpoints read only versioned synchronous projections. Responses may
include `resolved_sources`, containing only source kind, observation time,
selection-policy version and conflict state. Missing or stale projections
return `503` with stable code `projection_unavailable`; the API does not fall
back to live Canonical joins.

### `GET /films/{film_id}/graph`

Returns a one-hop `FilmGraphView` assembled only from Graph read models. Under
`graph-visibility.v1`, the service includes Resolver-selected Director/Actor
Credits and active, accepted, factual Assertions. Proposed, rejected,
superseded and inferred Assertions are excluded server-side.

The response is bounded to 65 nodes and 64 edges, uses stable Genre/Director/
other-fact/Actor priority, and reports `truncated`, `visibility_policy` and
`projection_version`. Nodes expose only public identity and display fields;
edges expose public source kinds, review status, active Evidence count and
conflict state, never internal provenance references.

## Factual Explore

### Addressable local collections

`GET /explore/catalog` accepts `category=all|director|country|decade` (default
`all`), literal local `q` (maximum 200 characters), `featured=false`, `limit=24`
(1–24) and `offset=0` (nonnegative). Country names include bundled bilingual
aliases. The directory requires at least two eligible local Films per collection
and removes identical memberships within a category. Featured mode round-robins
categories, suppresses membership overlaps of 85% or more and uses distinct
preview Films across shelves. It does not rank quality or infer recommendations.

Response: `{visibility_policy,strict,total_films,categories,items,total,limit,
offset,next_offset}`. `categories` counts director/country/decade definitions after
the literal search and directory deduplication. Every item has
`{id,kind,key,label,count,unwatched_count,previews}`; previews contain up to four
existing public Library Film summaries. Catalog reads use at most six SQL statements,
including projection readiness checks, with no per-collection query loop.

`GET /explore/collections/{kind}/{key}` defines a stable collection, where kind is
`director|person|country|decade` and key is a Canonical Person ID, uppercase ISO
country code or release-year decade. Invalid identities are 422; absent/empty
definitions are 404. A valid direct collection can contain one Film even though
the directory only suggests larger sets. Director membership requires an eligible
director credit. Person membership includes eligible actor OR director credits,
deduplicated by Canonical identity. Missing or conflicted memberships fail closed.

Returns `{collection,results}`. Collection identity, count and description always
refer to the All set. Optional temporary `view=all|watched|unwatched`,
`sort=title|year`, `dir=asc|desc`, `limit=40` (1–100) and `offset=0` use the
existing strict Explore Film page contract for `results`. Viewing changes do not
rename or remove a collection. The frontend corrects invalid last-page offsets
with history replace. No new schema, persistent curated data, series inference,
external catalog or model request is involved. The historical endpoints below
retain their existing contracts.

All Explore routes read only the synchronous Schema v4 Explore projections and
use visibility policy `factual-explore.v1`. They never invoke a model, generate
similar results, relax constraints, or fall back to Canonical live joins. A
missing or stale Library/Explore projection returns `503` with stable code
`projection_unavailable`.

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/explore` | Return visible Film total, per-dimension coverage and the top 12 facets. |
| `GET` | `/explore/collections` | Return nonempty local collections with exact counts and representative artwork. |
| `GET` | `/explore/context` | Return deterministic next-step factual clues for the current strict query. |
| `GET` | `/explore/facets/{dimension}` | Search and paginate one `genre`, `person`, `country`, or `decade` facet set. |
| `GET` | `/explore/films` | Return the reproducible strict intersection selected by repeated fact filters. |

`GET /explore` separates each dimension into `covered_films`,
`conflicted_films`, and `missing_films`. Each facet includes owned, watched and
unwatched Film counts, merged Person roles, and safe source kinds. Top facets
sort by Film count descending, normalized label ascending, then stable facet
key. Responses identify both registered projections
(`factual-explore-film.v1` and `factual-explore-facet.v1`).

`GET /explore/context` accepts the same repeated Genre, Person, Country and
Decade filters as `/explore/films`, plus `view=all|watched|unwatched` and
`limit` (default 6 per dimension, 1–12). It returns `current_total` and one
entry for each dimension:

- when that dimension is empty, `operator=and` and each clue's `result_count`
  is the exact strict total after adding it;
- when that dimension already has a selected value, `operator=or` and
  `additional_count` is the number of Films newly admitted by that clue;
- with `person_match=all`, selected People instead use `operator=and` and
  `result_count` is the exact intersection after adding another Person;
- selected and ineligible facets are excluded, ordering is deterministic, and
  `has_more` indicates that Fact Finder can reveal more than the returned
  clues.

Each clue may include one deterministic `preview_film` drawn from the clue's
actual contribution set. OR clues prefer a newly added Film. Preview selection
prefers safe local thumbnails, then provider artwork, then a stable no-artwork
fallback. The response copies only public Film identity and the existing
Library read model's six safe artwork fields. Context calculation performs
fixed bulk reads rather than one query per facet, and preserves the same
unresolved, conflict, privacy and `503 projection_unavailable` semantics as the
other Explore endpoints.

`GET /explore/collections` accepts `view=all|watched|unwatched` (default `all`)
and `limit=1..12` (default 6). Each item contains `dimension`, `key`, `label`,
`view`, exact `count` and `preview_film`. Country collections use Unwatched when
the current view is All; other entries preserve the view. Decade, Person and
Genre collections alternate with Country entries, ranked by count and stable
label/key. Identical Film sets are shown only once. People collections mean
participation as Actor or Director, not a director-only filmography. Counts
exactly match `/explore/films` for that item's single filter and view. Only
eligible local facts are used, previews belong to their actual set, and empty
sets are omitted. `total_films` remains the visible Library size. An empty or
metadata-poor Library can return `items=[]`; no substitute suggestions are
invented. The implementation uses at most six bulk SQL statements without
per-collection queries and returns the same safe projection/policy metadata.

`GET /explore/facets/{dimension}` accepts optional `q` (at most 100
characters), `limit` (default 30, 1–100), and non-negative `offset`. The
response includes `total`, `next_offset`, and the complete coverage summary for
that dimension. Person Directors and Actors share one facet collection; roles
are returned as `director` and/or `actor`. Search is literal, case-insensitive
label matching plus the bundled bilingual Genre/Country aliases and decade
suffixes (`1990s`, `1990年代`); it is not natural-language semantic search.
The Explore UI debounces input and queries all four categories, with independent
pagination. No external catalogue or model is consulted.

`GET /explore/films` accepts repeated Canonical `genre=con_<id>` (and
normalizes the longer `concept_<id>` spelling),
`person=person_<id>`, `country=<ISO alpha-2>`, and `decade=<four-digit decade>`
parameters, with at most 20 unique values per dimension. It also accepts:

- `view=all|watched|unwatched` (default `all`);
- `person_match=any|all` (default `any`, also accepted by `/explore/context`);
- `sort=title|year` (default `title`);
- `dir=asc|desc` (default `asc` for title and `desc` for year);
- `limit` (default 40, 1–100) and non-negative `offset`.

Values are deduplicated and sorted. Values within one dimension are ORed, except
People with explicit `person_match=all`, which must all participate in each Film;
non-empty dimensions and the Viewing-derived watched state are ANDed. Empty
release years never match a decade. Malformed values return `422`. A validly
formatted but missing, deleted, conflicted, or otherwise unavailable facet is
preserved in `unresolved_filters`. A dimension containing only unresolved
values therefore matches zero Films; it is never removed from the query. Any
unavailable Person in `person_match=all` makes the intersection empty. Omitting
the parameter preserves historical OR links. Fresh UI searches start with All
and serialize `person_match=all` once a Person is selected; both modes are
explicitly selectable, preserved by history/refresh, and echoed in
`active_filters.person_match`. Actor/Director roles share the same Person
identity and never count as separate people.

The Film response includes normalized `active_filters`, display-ready filter
details, `unresolved_filters`, strict total/pagination fields, public
`LibraryFilmSummary` rows, and each Film's actually matched facts. Matched facts
expose only dimension, stable key, label, Person roles, safe source kind and
selection policy, or `release-year-decade.v1` derivation. Sorting always uses
Film ID as the final tie-breaker.

### `POST /library/items/{library_item_id}/refresh`

Queues `library.refresh_item`. The response is an accepted Job envelope.

### `POST /library/items/{library_item_id}/ignore`

Marks one edition ignored and returns the updated edition. Other editions and
the shared Film metadata/profile/analysis are unchanged.

### Scanning and lifecycle

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/library/scan` | Queue a full reconcile. |
| `POST` | `/library/reconcile` | Alias of the canonical reconcile command. |
| `POST` | `/library/scan-folder?folder_path=...` | Queue one controlled folder/file scan. |
| `GET` | `/library/sync/status` | Reconcile and watcher state. |
| `GET` | `/library/missing` | List path-safe summaries for every missing LibraryItem. |
| `DELETE` | `/library/missing` | Retire missing LibraryItems. |
| `DELETE` | `/library` | Retire all LibraryItems but preserve Film-level data. |
| `DELETE` | `/library/data` | Delete domain data while retaining settings, migration journal and fixed references. |
| `POST` | `/library/seed` | Insert normal demonstration Films for local development. |

Scan and organizer Job payloads expose only stable IDs, counts and controlled
manifest references. Absolute paths are held in Git-ignored private manifests,
not public Job/Event payloads.

`GET /library/missing` returns `{ count, items }`. Each item contains only
`library_item_id`, `film_id`, selected Film title/year, `display_name`, and
`missing_since`, sorted by missing time, title, and LibraryItem ID. It never
returns a source key, media locator, or absolute path.

## Profile state and Viewing

### `GET /films/{film_id}/profile-state`

Returns one `FilmProfileState` with:

```json
{
  "film_id": "film_0123456789abcdef0123456789abcdef",
  "favorite": false,
  "rating": null,
  "notes": null,
  "watched": false,
  "manual_watched": false,
  "watched_at": null,
  "updated_at": null
}
```

### `PUT /films/{film_id}/profile-state`

Accepts any subset of `favorite`, `rating` (1–5 or null), `notes` (up to 10,000
characters), `watched`, and `watched_at`.

- `watched=true` creates or restores a confirmed manual Viewing. Restoration keeps
  its date precision, rating and notes; it does not create a new Diary entry.
- `watched=false` revokes only the manual Viewing.
- Other confirmed sources, including future Diary entries, are preserved.
- Derived `watched` is true when any active confirmed Viewing exists.
- Derived `manual_watched` is true only while the singleton quick-toggle Viewing
  is active. Clients use it to avoid overwriting Diary-only watched state.

### Diary

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/profile/viewings?view=timeline|recent&limit=100&offset=0&film_id=...` | Return the complete timeline or one latest Viewing per Film; `film_id` is optional. |
| `GET` | `/films/{film_id}/viewings` | Return every active confirmed Viewing for one Film. |
| `POST` | `/films/{film_id}/viewings` | Create a new confirmed Diary Viewing. |
| `PATCH` | `/viewings/{viewing_id}` | Partially update date, rating or notes using the opened revision. |
| `DELETE` | `/viewings/{viewing_id}?revision=...` | Soft-delete one editable Viewing with a revision guard. |

Create requires `watched_at`; PATCH accepts any nonempty subset of `watched_at`,
`rating` and `notes`. Accepted date values are an
exact `YYYY-MM-DD` date, a four-digit year, a timezone-aware RFC 3339 timestamp,
or `null` for unknown. Duplicate dates remain independent records. Manual and
Diary sources are editable; other sources return `409` with code
`viewing_read_only`.

Rating is a strict integer 1–5 or null. Notes are text up to 10,000 Unicode
characters, without NUL; empty/whitespace-only text normalizes to null. Omitted
fields are preserved, explicit null clears. Changing only a review preserves
the exact timestamp and precision. Viewing reviews and Film profile reviews
are independent and never synchronize in either direction.

Every Viewing response includes an opaque 64-character `revision`. PATCH must
include the revision captured when opening the form; DELETE passes it as a
query parameter. Missing revisions return `409 viewing_revision_required`;
stale revisions return `409 viewing_changed`. Reload before submitting a new
edit. Unversioned historical forms cannot overwrite current state.

Clients should send `idempotency_key` (16–64 ASCII letters, digits, `_` or `-`)
on every POST/PATCH. It is required whenever rating or notes is supplied.
Date-only legacy POST remains accepted without a key. Persist the request and
key before sending; after an uncertain response retry the identical payload.
The SQLite transaction atomically commits the Viewing, event and retry receipt.
An identical retry returns the same Viewing with `replayed:true`; reused keys
with another payload return `409 viewing_retry_conflict`. If that saved Viewing
has subsequently changed or been deleted, retry returns 409 and never overwrites
or recreates it. Repeated DELETE on an already deleted row succeeds. Restored
manual records require their current revision. Database write failures return
503, allowing an identical retry. Review text is not copied into event payloads.

```json
{"watched_at":"2026-08-31","rating":4,"notes":"A different impression on rewatch.","idempotency_key":"viewing-create-0001"}
```

For PATCH, for example, send `{"rating":null,"revision":"<revision from GET>",
"idempotency_key":"viewing-update-0001"}` to clear only this Viewing's score.

`GET /profile/viewings` returns `items`, `total`, `limit`, `offset`, and
`next_offset`. Each item contains the Viewing, a lightweight Film identity with
`in_library`, and the derived Film profile state. `view=timeline` is the default
and returns every active confirmed Viewing. `view=recent` selects the latest
Viewing for each Film before pagination. Known dates sort descending, unknown
dates sort last, and the default/maximum page sizes are 100/200.

Viewing reads also include nullable `rating` (integer 1–5) and `notes` (up to
10,000 characters, without NUL). Schema v9 adds these columns without assigning historical
Film ratings/notes to any Viewing. Existing Film-level reviews remain in place.
Retry receipts survive restart and stay out of portable exports.
`library-export.v1` includes these two fields on each exported Viewing and
continues accepting older packages that omit either field. Explicit null means
no saved value; present invalid values and unknown fields are rejected.

## Metadata, artwork and external scores

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/metadata/search?query=...&year=...&language=...` | Search TMDB candidates. |
| `GET` | `/metadata/movie/{tmdb_id}` | Load one confirmation candidate. |
| `POST` | `/films/{film_id}/scrape` | Scrape one Film. |
| `GET` | `/films/{film_id}/scrape/candidates?language=...` | Find bounded TMDB candidates without changing Film, edition, Event, or file state. |
| `POST` | `/films/{film_id}/scrape/confirm?tmdb_id=...` | Scrape with an explicit candidate. |
| `GET` | `/films/{film_id}/artwork` | List TMDB artwork options. |
| `PUT` | `/films/{film_id}/artwork` | Apply validated poster/backdrop paths. |
| `POST` | `/films/{film_id}/external-scores/refresh` | Queue one Film score refresh. |
| `POST` | `/library/external-scores/refresh` | Queue library-wide score refresh. |
| `GET` | `/library/external-scores/status` | Latest source refresh state. |
| `POST` | `/library/scrape` | Queue a batch metadata scrape. |
| `GET` | `/library/scrape/status` | Batch scrape status. |

TMDB requests require `TMDB_API_KEY` from the environment or managed setting.
The API never returns the key. External scores are normalized
`FilmExternalScore` resources rather than JSON stored on a library row.
Candidate lookup requires an available edition with a present video locator and
returns an empty array when TMDB has no matches. It never marks the Film as
reviewed or writes metadata; confirmation remains an explicit `POST`.
Confirmation can attach a pre-scanned edition to an existing Film with the same
TMDB/IMDb identity. The result's `film_id` and `film.id` identify the canonical
Film; an emptied source Film remains an alias for detail reads. Edition IDs and
their scrape bookkeeping are preserved. Unchanged file scans do not clear
attempt time/confidence or reset `failed`/`needs_review` states. Ordinary review
uses `needs_review` with no `scrape_error`; an empty scrape returns HTTP 409 with
`detail.message = "No TMDB matches found"` and persists `failed`.

## File organization

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/library/organization/candidates` | List direct-root and legacy-inbox videos using relative source paths. |
| `POST` | `/library/organization/preview` | Resolve one TMDB identity and preview the exact file plan without writes. |
| `POST` | `/library/organization/confirm` | Revalidate a preview token and queue one confirmed file plan. |
| `GET` | `/library/root-videos` | Deprecated compatibility view for direct-root videos. |
| `POST` | `/library/organize-root` | Queue explicitly enabled automatic root-only organization. |
| `GET` | `/library/organize/status` | Latest organizer status. |

`POST /library/organization/preview` accepts:

```json
{"source_path":"inbox/Messy.Name.1999.mkv","tmdb_id":603,"rename_style":"preserve_stem"}
```

The response contains the source summary, selected TMDB candidate, target folder
and video name, sidecar plan, post-actions, conflicts, `can_confirm`, and a
64-character `confirmation_token`. It never returns an absolute source path and
does not create directories, move files, or write metadata.

Confirmation repeats the preview body and adds its token. A stale source,
changed identity or rename style, or a new target conflict returns `409` before
enqueue. The Workflow validates the same token again before moving anything.
Unsupported, nested, or escaping paths return `400`; a missing source returns
`404`. Manual confirmation never overwrites target video or sidecar files.

Confirmed files may come directly from the media root or its direct `inbox`
child. Automatic organization remains root-only. Restorable moves reference a
private controlled manifest; the Event and OperationSnapshot store only its
opaque reference. File-location restore covers the video, associated sidecars,
and database locator; generated NFO and artwork files remain.

## Ask MVP

Ask is a read-only planning and query interface over factual Explore projections.
Its contract version is `ask.v1`; no schema migration is required.

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/ask/status` | Provider-key presence and availability of the local form. |
| `POST` | `/ask/interpret` | Interpret one question using the configured model, then resolve local entities. |
| `POST` | `/ask/resolve` | Validate and preview a plan locally, without a model call. |
| `POST` | `/ask/query` | Execute explicitly confirmed conditions; pagination never calls the model. |

Interpretation accepts `{"question":"Find unwatched Japanese films from the 1990s.","locale":"en"}`.
Question length is 1–600 characters, locale is `zh` or `en`. Only the question
and static output schema reach the provider, not Library records, notes, media
paths, selected results or private settings. Obvious pasted credentials and
absolute paths are rejected before calling the provider. Questions and responses
are not persisted, included in audit events or logged by Ask.

Resolve accepts a plan and an optional explicit `person_id`:

```json
{
  "plan": {
    "genre": null,
    "person": null,
    "person_role": "any",
    "country": "JP",
    "decade": 1990,
    "view": "unwatched",
    "sort": "title",
    "direction": "asc"
  },
  "person_id": null
}
```

Each dimension accepts at most one value and combines with AND. Genre/country
values are resolved through the controlled multilingual vocabulary. Person
names use active, eligible local entities: a unique exact match can resolve
automatically; multiple exact matches or partial matches require selecting one
of the returned candidates (at most nine, each with up to two sample Films).
Unknown values block execution. A provided Person ID must still match the name;
it cannot override an unrelated or vanished entity.

`person_role` is `any|director|actor`; decade is an integer divisible by ten in
1880–2190; view is `all|watched|unwatched`; sort is `title|year`; direction is
`asc|desc`. Model output must explicitly include every plan field. Manual form
requests may omit fields to use null/any/all/title/asc defaults. Other fields,
multiple values, arbitrary SQL, exact-year/rating/runtime filters, exclusions,
recommendations and mutation instructions are outside the supported plan.

Responses contain `version`, `status`, `plan`, `person_id`, `constraints` and
`issues`. Status is `ready`, `needs_clarification`, `clarify` or `unsupported`.
Unsupported/vague interpretations have no plan. Resolution issues name the
unresolved field and include candidate identities when available.

Query accepts the same payload plus required `"confirmed": true` and optional
`offset` (0–100000). It resolves conditions again and returns `results: null`
if anything remains unresolved. Otherwise `results` is the existing
`ExploreFilmPage` shape with a fixed page size of 20. Person roles are enforced
before total counts, sorting and pagination. The returned `matched_facts`,
source kinds and viewing state provide deterministic explanations; zero results
never trigger automatic relaxation. `/explore/films` behavior is unchanged.

Interpretation makes one call with a 20-second transport timeout, a 1200-token
output cap, zero retries and at most two concurrent calls per process. It uses
the existing model/base URL settings and `OPENROUTER_API_KEY`; provider-key
presence does not certify provider availability. Errors expose stable codes:
`503 ask_not_configured`, `429 ask_busy`, `504 ask_timeout`,
`502 ask_invalid_response|ask_provider_unavailable`,
`422 ask_private_input|ask_invalid_selection`. Contract validation uses `422`;
stale projections return `503 projection_unavailable`. The local resolve/query APIs
remain usable without a model key; Explore provides the current UI.
Natural-language quality still requires live acceptance, independently of the
offline query tests and Analysis Gate B.

## Analysis V2

### `POST /films/{film_id}/analysis-runs`

Queues `analysis.analyze_film`. The runtime builds Canonical input, validates
`analysis-output.v2`, resolves entities and transactionally persists
AnalysisRun, Assertion, provenance, Evidence and resolution reviews.

### `GET /films/{film_id}/analysis`

Returns `FilmAnalysisView` assembled from the latest AnalysisRun and
active structured records. It contains a bounded summary, relations, Evidence,
reviews and status. Raw prompts/responses, hidden reasoning and compatibility
JSON are never stored or returned.

### Local Analysis review

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/films/{film_id}/analysis-review?offset=0&limit=50` | Review history across runs, including rejected and user-corrected relations. |
| `GET` | `/films/{film_id}/analysis-review/targets?predicate=INFLUENCED_BY&q=...` | Up to 30 existing, active target entities of the required kind. |
| `PUT` | `/films/{film_id}/assertions/{assertion_id}/review` | Accept, reject or correct an Analysis relationship. |
| `PUT` | `/films/{film_id}/analysis-reviews/{review_id}` | Resolve, dismiss or reopen an unresolved reference. |

The review page returns `relations`, `reviews`, `offset`, `limit` and
`next_offset`. The same offset applies independently to both lists; consume
both lists before requesting the next page. Maximum limit is 100. Each row
includes a SHA-256 `revision` for optimistic concurrency. The original Analysis
response remains unchanged and still excludes rejected relations.

An Assertion decision is `{"revision":"<hash>","decision":"accepted"}` or
`rejected`. To correct it, use `decision: "rejected"` plus:

```json
{
  "correction": {
    "predicate": "REMAKE_OF",
    "target_entity_id": "film_0123456789abcdef0123456789abcdef",
    "direction": "subject_to_target"
  }
}
```

This fragment supplements the decision payload. Correction rejects the original
and accepts the replacement atomically. It validates predicate, entity kind,
concept kind, lifecycle, direction and self-reference. It does not create new
entities, make provider calls, or copy rationale/Evidence to another relation.
An existing rejected replacement must be reviewed explicitly before reuse.

Resolution payloads contain `revision` and `action` (`resolve`, `dismiss`,
`reopen`). Only `resolve` requires `correction`. Assertion reviews create a
user-curated relationship; entity-reference reviews only record the selected
entity. For reference lookup, optional `entity_type=film|person|concept` selects
the reference kind instead of the predicate's object kind. Evidence/output
reviews can be dismissed or reopened, but cannot be marked verified here.
Reopening a review does not undo any previously created relationship; review
that relationship separately. Identical closed reference decisions carry
forward when the same candidate appears in another analysis run.

Stale revisions return `409 stale_review`; conflicting prior decisions return
`409`; invalid selections return `422`; resources outside the selected Film
return `404`. Read the current page before retrying. Writes, projections and
bounded audit events commit together. User decisions survive reanalysis;
Graph visibility remains factual while Gate B is blocked.

The search UI uses `GET /library/films?q=...` (maximum 200 characters), matching
normalized title/original title, genres, countries and directors. `%` and `_`
are literal characters rather than wildcard syntax. The personal record editor
uses the existing profile-state API and sends only changed `rating`/`notes`;
explicit `null` clears either field. Notes are excluded from profile-state
Activity payloads and from model input.

## Activity and operation restore

### `GET /activity/events`

Lists bounded `EventRecord` objects newest first. Optional filters are
`aggregate_type`, `aggregate_id`, `type`, `command_id`, `correlation_id`, and
`limit` (1–500). Canonical aggregate types include `film`, `library_item`,
`viewing`, `assertion`, `analysis_run`, and `workflow`.

### `GET /library/events`

Server-Sent Events stream for live invalidation and Workflow status notifications.

### `GET /operations/{snapshot_id}/preview`

Returns the bounded before/after diff, current-state match and a confirmation
token when restoration remains safe.

### `POST /operations/{snapshot_id}/restore`

Body:

```json
{"confirmation_token":"<64 lowercase hex>"}
```

Returns `409` if the current state has drifted, the token is stale, the snapshot
was already restored, or a controlled file restore is no longer safe.

## Durable workflows

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/workflows` | List sanitized workflows; optional `status`, `type`, `limit`, `include_active`. With `include_active=true` and no status filter, retain every queued/running workflow in addition to the bounded recent list; type filtering still applies. |
| `GET` | `/workflows/{workflow_id}` | Get a workflow and its ordered steps. |
| `POST` | `/workflows/{workflow_id}/cancel` | Cancel or request cancellation. |
| `POST` | `/workflows/{workflow_id}/retry` | Resume from the first failed/cancelled step. |

Long-running commands return:

```json
{
  "status": "queued",
  "message": "...",
  "workflow_id": "workflow_0123456789abcdef0123456789abcdef",
  "workflow": {}
}
```

Public Workflow/Step representations never include credentials, absolute paths,
raw model/provider output, titles used as privacy canaries, or full dedupe values.
The `job` table is an internal single-step execution queue and has no public API.

## Compatibility policy

This is a deliberate breaking baseline. The following endpoints do not exist:

- `/library/{movie_id}`
- `/library/user-states`
- `/watch-history`
- `/profile/watch-history`
- `/library/analyze/{movie_id}`
- `/analyze/{movie_name}`
- Movie timeline, projection rebuild and historical backfill endpoints

The generated OpenAPI document at `/docs` is authoritative for request-model
field details. Any route or response-shape change must update this document and
`skills/5x49-backend/SKILL.md` together.
## Cinema DNA V1

Cinema DNA is an all-time, local-profile statistic over active Films with
confirmed undeleted Viewings, including Films no longer in the Library. All
three endpoints are read-only and return `formula_version=cinema-dna.v1`,
`projection_version=cinema-dna-film.v1`, `scope=all-time-confirmed-viewings`,
`thresholds`, `totals` and `needed_global_ratings`.

| Method / path | Parameters | Result |
| --- | --- | --- |
| `GET /profile/cinema-dna` | none | Distinct watched/rated Films, viewing record count, four dimension coverage partitions |
| `GET /profile/cinema-dna/facets/{dimension}` | `genre\|person\|country\|decade`; `metric=exposure\|preference`; `limit=20`, `offset=0` | Category statistics, source kinds, roles and stable pagination |
| `GET /profile/cinema-dna/contributors` | required `dimension`, `key`; `metric=exposure\|preference`; `limit=40`, `offset=0` | Selected `facet` summary or null; actual contributing Films and selected factual source |

Both page endpoints return `items`, `total`, `limit`, `offset`, `next_offset`.
Limits are 1–100; offsets are nonnegative. Fact keys use the same validation as
Explore, including normalization of `concept_` to `con_`. Malformed input is
`422`; valid but absent categories yield empty results. Missing/failed/stale
projection state is `503` with `detail.code=projection_unavailable`.

`totals` contains `watched_films`, `viewing_records` and `rated_films`.
Coverage partitions use `total_films`, `covered_films`, `conflicted_films` and
`missing_films`; conflicting/missing facts do not become category memberships.
Facet items include `film_count`, `denominator`, `share` (fraction, not percent),
`viewing_count`, `rated_count`, `preference`, `needed_category_ratings`, `roles`
and `source_kinds`, in addition to stable `key` and current `label`.

Exposure counts distinct category Films divided by all distinct watched Films;
multi-label percentages can exceed 100% in total. Preference is the arithmetic
mean of current personal 1–5 Film ratings, with no rewatch/favorite/recency
weight. It is null unless at least 10 watched Films are rated globally and 3
within the category. Only eligible categories appear in preference ranking;
exposure remains available to inspect low-sample categories and their ratings.
Preference contributors contain only rated Films, even below the display gate.
Sort exposure by count descending then key; sort preference by exact mean,
rated count descending then key. Display means to one decimal place.

Contributor items contain `film_id`, `title`, `year`, `rating`, `viewing_count`,
`in_library` and `fact` (`dimension`, `key`, `label`, public `source`). Sort by
casefolded title then Film ID. Link to `/diary?film={film_id}` for its original
Viewing facts. Notes, media paths, provider input and credentials are excluded.
Each response reads projection readiness and inputs from one SQLite snapshot.
# Film basic metadata corrections

`GET /films/{film_id}/metadata` returns `film_id`, opaque `revision`, and `fields`
for `title`, `original_title`, `year`, `overview`. Each field contains `value`,
`manual`, `automatic_value`, and `automatic_source` (`source_kind`, `observed_at`,
`policy_version`, `conflicted`). Reads do not write or call providers. Historical
year/synopsis columns lack per-field provenance and are labelled `library`, never
guessed as NFO/TMDB from an edition. Existing title provenance is retained.

`PATCH /films/{film_id}/metadata` accepts only:

```json
{
  "revision": "<64 lowercase hex returned by GET>",
  "idempotency_key": "<16..64 ASCII letters/digits/underscore/hyphen>",
  "changes": {
    "title": {"action": "set", "value": "Corrected title"},
    "year": {"action": "set", "value": null},
    "overview": {"action": "reset"}
  }
}
```

- Submit only changed fields. `set` requires an explicit value; `reset` must
  omit it. Unknown fields (including TMDB/IMDb IDs, rating and notes) are 422.
- Title is required, trimmed, 1–300 Unicode characters. Original title permits
  0–300 and synopsis 0–10000; blank optional text is a protected null. Year is a
  strict integer 1870–2100 or null; booleans, strings and fractional years fail.
- Null year means manually unknown and remains protected. `reset` alone removes
  that field's override and resumes the current automatic value and future scans.
  Resetting an automatic field is harmless. Other fields are unchanged.
- Automatic Film/source rows are never changed by this endpoint. The separate
  override, retained edit receipt (before/after values and automatic snapshot),
  bounded `FilmMetadataEdited` event and read projections commit atomically.
  Edits do not write NFO/media or change identity, profile state or Viewing rows.
- Revision checks include manual revision, automatic values/sources, identities,
  lifecycle and editions. Stale state is 409 `metadata_stale`; an inactive Film
  is 409 `metadata_film_changed`. No rebasing or following a merged ID on write.
- Retry the same normalized body and key after an uncertain response. A repeat
  returns current metadata with `replayed: true`, without reapplying an older
  edit. Different content with a used key is 409 `metadata_retry_conflict`.
  Initial success returns `replayed: false`. Records survive process restarts.
- Invalid IDs/bodies return 422; missing Film 404; database contention 503
  `metadata_temporarily_unavailable`; persistence failure 500
  `metadata_save_failed`. Retryable failures keep the same request and key.
- Late identity matching cannot move an edition away from a Film with any
  manual override, including a null override. Restore every corrected field to
  automatic first, then retry the existing conservative identity workflow.
  The check is repeated in the actual observation transaction. Corrections are
  never automatically migrated or merged into another Film.
- Existing portable exports additionally preserve active corrections under the
  optional `curated_metadata.manual_overrides` array (`film_id`, `values`,
  `revision`, `updated_at`). Old v1 exports without this member remain valid;
  database backups retain the complete edit history and automatic records.

# Maintenance database backups

These endpoints create a restorable SQLite package, **not** `library-export.v1`.
They use the existing trusted/local application access boundary. Packages contain
private library paths and personal records; do not expose the application publicly.

- `GET /maintenance/backups`: `{last_attempt, last_success, retention_hours:24}`.
  Missing records are `null`; read/storage failure is 503, never a fabricated
  "never backed up" result. Only backups created by this service are tracked.
- `POST /maintenance/backups`: `{request_id:"<32 lowercase hex>"}`, no other fields.
  Returns 202 with the attempt. Retain the ID across uncertain responses and retry
  the same ID; persisted receipts never regenerate a prior failed, interrupted,
  expired or superseded request. Use a new ID for a deliberate new attempt.
  Concurrent different requests return 409 `backup_busy`.
- `GET /maintenance/backups/{id}`: that attempt, or 410 `backup_not_found`.
- `GET /maintenance/backups/{id}/download`: verified ZIP attachment; unavailable,
  expired, superseded or corrupt packages return 410 `backup_unavailable`.
- `POST /maintenance/backups/{id}/download-triggered`: idempotently records a
  browser-reported trigger on a successfully generated attempt. This is **not**
  a server transfer receipt or proof of the user saving a file to disk.

Attempt fields: `id,status,created_at,finished_at,expires_at,size_bytes,sha256,
schema_version,error_code,download_triggered_at,artifact_state,available,filename`.
Status is `generating|succeeded|failed|interrupted`; artifact state is nullable or
`available|expired|superseded|missing|corrupt`. Timestamps are UTC ISO strings;
size and SHA-256 describe the ZIP. Generation errors are bounded codes:
`backup_tasks_active`, `backup_sensitive_content`, `backup_interrupted`, or
`backup_failed`. Invalid input is 422. Storage access failure is 503
`backup_storage_unavailable`; errors never return source paths or credentials.

The ZIP contains the SQLite database, its existing v1 checksum/row-count manifest,
and `RESTORE.txt`. It preserves Film identities including merged aliases, manual
metadata/edit history, viewing dates/reviews, Film reviews and other business facts.
It excludes the entire Setting table, external configuration/environment files,
artwork files, videos, NFO and external operation manifests. Diagnostic errors and
credential-bearing automatic fields are cleaned on the copy. Derived read models
are cleared and rebuilt by normal startup. Known credentials and credential-shaped
personal content cause refusal instead of silent personal-data edits; this is not
semantic detection of arbitrary secrets typed into notes. Deleted pages are removed
with VACUUM; the sanitized database gets a new verified manifest. The source is
never changed. Source integrity/counts/backup use one SQLite read transaction,
including committed WAL data.

Active Job/Workflow/Analysis work in the completed snapshot causes refusal: wait
for tasks to finish. File-organization undo snapshots are marked expired and their
external manifest references removed in the copy. History is retained, but file
undo is unavailable. Extract the ZIP and use the existing offline restore CLI;
first verify in a fresh temporary environment, with no credentials/media and
`WATCH_LIBRARY=false`. Stop writers, checkpoint the target and explicitly confirm
its current SHA-256 before replacement. Reconfigure media directories and API keys
after recovery; no web reset/restore endpoint is introduced.

State and durable idempotency receipts live separately in
`<database-directory>/maintenance-backups/state.sqlite3`. OS file locks serialize
generation across processes; process death releases ownership and the next status
read/startup marks unfinished work interrupted. Failure preserves the previous
successful package. Only the latest successful package is downloadable for 24
hours after generation. Expiry is enforced on reads/downloads; an idle sweep runs
every 60 seconds while the backend is running. Offline time is reconciled on
restart. Downloads already opened may finish; Windows files still held by a stream
are removed on a later sweep. Cleanup only touches owned package/staging names,
never CLI backups or the source database. A backup-storage fault does not prevent
the main library application starting.

## Video health inspections (schema v10)

All endpoints are under `/maintenance/video-health`. Inspection is read-only and
independent of technical metadata probing during scans. A container pass never
means a continuous full audio/video decode passed. `passed` on the main status
requires every non-cover-art audio/video stream to decode from the beginning to
EOF, with a final unchanged version/access/ownership check. FFmpeg output goes to
the null muxer; there is no repair, deletion or saved transcode.

- `GET /maintenance/video-health`: `{config,schedule_timezone:"UTC",reason,
  counts,total,unread,load,active_id,budget_day,used_seconds,queue_sweep_pending,
  manual_active,active_progress}`. `counts` distinguishes unchecked, queued, checking, passed,
  abnormal, incomplete and unsupported. `load` contains `observable,cpu,disk`.
- `PUT .../config`: strict nonempty subset of `enabled:bool`, `paused:bool`,
  `start_minute/end_minute` (UTC minutes 0..1439), `daily_budget_minutes` (1..1440).
  Unknown/null/coerced fields are 422. Equal endpoints mean all day; an overnight
  interval is supported. Auto detection defaults enabled; budget defaults 30 min.
- `POST .../queue`: 202 `{status:"queued",batched:true}` requests an idempotent
  persistent sweep of DB-known media assets, including multipart files. It does
  not scan directories or synchronously stat all disks. Unchanged passed versions
  are skipped. Explicitly interrupted/cancelled/unsupported/abnormal versions
  require per-file retry; queue-all does not erase those receipts.
- `POST .../cancel`: cancels existing unchecked/queued/active receipts and pending
  sweep, returning `{cancelled:N}`. Future discoveries still follow the auto
  setting. Pause or disable automatic checks to stop future scheduling.
- `GET .../files?status=abnormal&limit=20&offset=0`: page `{items,total,limit,offset}`;
  status accepts all or any count state; limit 1..50, offset 0..1000000. Summary
  polling reads DB metadata only. Rows carry asset/Film/edition IDs, filename,
  title, overall status, separate `container_status`/`decode_status`, filesystem `version_key/version`,
  current flag, checked time, retained `passed_at`, decoded/duration seconds, safe error code/summary,
  and unread flag. A failed container check leaves `decode_status:"unchecked"`; it does not
  pretend a deep decoder ran. Raw tool errors and absolute paths are never returned.
- `GET .../files/vh_<32 lowercase hex>`: on-demand detail revalidates live access
  and the exact filesystem version; includes attempts and unavailable_reason.
  Historical or unavailable results retain their original status with
  `current:false`; they do not certify the current file.
- `POST .../files/{id}`: `{action:"retry"|"cancel"|"acknowledge"}`. Retry requires
  that exact version to remain available/current, observes stability again, and
  starts from the beginning. Explicit single-file retries retain a bounded manual
  intent even with automatic checks disabled: they schedule only that file/version,
  respect pause/load/hours/budget, and do not drain unrelated automatic rows.
  A changed version ends that intent. Acknowledgement persists without deleting evidence.
  Missing ID is 404, invalid grammar/body/query 422, unavailable/stale retry 409,
  database failure 503 with a safe `detail.code`.

Version identity combines locator hash, device/inode, size, mtime_ns and ctime_ns.
It is a stat observation, not a content hash; an out-of-band change must be
observed to invalidate it. Scan metadata/ownership changes immediately invalidate
the old DB summary. The idle sampler gradually detects additional changes; unchanged passing scan
metadata avoids another automatic file read for 24 hours. A manual sweep and live
detail can perform a bounded explicit check sooner. Results belong to individual assets,
not Film identities; removal/retirement/root revocation prevents inspection or
notification transfer to a new edition.

`error_position_seconds` is always null and `position_kind:"unknown"`: decoded
progress is not falsely presented as the exact error timestamp. Full decoding
does not establish audiovisual synchronization or intended content completeness,
and valid-looking truncations with no declared duration can escape detection.
Offline, denied reads, changing files, missing tools/codecs, timeouts, unknown tool
failures and cancellation are incomplete/unsupported rather than abnormal.
Retryable offline/access failures back off exponentially, capped at one day.
Reconnection to the identical filesystem version preserves its prior full pass
without decoding it again; a changed version requires a new stability/decode pass.

One OS-locked worker per database runs one low-priority, single-thread decoder.
Known-file stat samples are small batches at most once per 30 seconds during
eligible idle windows; summary polling never stats all disks.
Stable observations are at least 60 seconds apart by default. Starts require 60
seconds of continuous quiet with CPU below 30% and disk busy below 20%; high
activity (75% CPU or 65% disk) suspends active work, then quiet recovery is
required. The owned decoder's CPU is excluded from host contention estimates.
Foreground application jobs synchronously suspend decoding before execution.
Only available backend-host counters are observed, never all NAS clients or disk
sleep. When observations are unavailable, an explicitly narrowed allowed window
is required; all-day permission is not a blind automatic-start override.

The daily budget limits new starts. A single long file already started may exceed
it while idle, avoiding a perpetual restart-at-budget loop. Outside allowed hours,
on pause or under activity, suspend the same process rather than seeking to a
checkpoint. Unsupported safe suspension terminates as incomplete. Linux uses a
parent-death kill signal and Windows a kill-on-close Job Object so an abrupt
backend exit cannot leave a decoder running beside a restarted worker. Other
unsupported process lifecycles are honestly reported unsupported/incomplete.
Queued receipts persist; interrupted decoders become incomplete and need explicit
retry. Continuous decoder state cannot be restored across backend restarts.

One durable unread notification per abnormal file version, surfaced by a navigation
badge and the maintenance panel, avoids repeated popups/SSE alerts. Acknowledging
or changing the version removes the current unread attention. No external
notification is sent. Health records/queue are host-specific operational data:
they are excluded from `library-export.v1` and downloadable maintenance backups;
raw offline database backups naturally retain the whole DB. Restored raw queues
still revalidate configured access and current versions before running. Deep reset
cascades health rows with assets and never writes media.

Supported deployment: one backend process/worker per library database (the default
Uvicorn/container entrypoint). The OS lock prevents duplicate health decoders
across processes, but a standby worker does not automatically take over if its
owner exits, and active process/load/reason state is local to the owner. Compound
runtime-setting updates and foreground preemption are not coordinated across
multiple API workers. Multi-worker/multi-instance execution against one database
is therefore unsupported for this feature; stop the prior owner before restart.


### Source-backed language search

Extended `search-plan.v2` optionally accepts `languages`, at most eight objects
`{kind:"original"|"spoken",code:<ISO639-1 or yue>,exclude:<strict bool>}`.
Different clauses combine with AND. Repeated/contradictory clauses fail validation.
Old plans continue to omit the empty field. Local EN/ZH examples: `films in Japanese`,
`original language English`, `原始语言为英语的电影`, `不要日语电影`.
Bare nationality clauses retain country semantics. Unknown or conflicting facts
are excluded from positive and negative filters. Query `results.language_coverage`
reports unknown/conflicted counts per requested kind after other hard filters.
Language chips survive URL restoration and remove only their own clause.

Film detail/library projections add `original_language`, `spoken_languages`,
`language_coverage` and `language_sources`. These are film metadata, independent
of edition audio/dubbing. Schema v12 and library/detail projection v3 build locally;
missing historical language data stays unknown, without automatic provider fetch.

The existing Film metadata endpoint also supports `original_language` (code/null)
and `spoken_languages` (unique code list/null, max30). Set/clear/reset retain
revision, idempotency and source ownership; automatic updates never override manual
values. See `docs/features/language-metadata-enrichment.md` for cast completeness,
source-specific aliases and the explicit ID-bound enrichment helper.


### Bounded semantic clauses and score contracts

Content segmentation preserves soft contrast/preferences while consuming only
complete v2 hard clauses. Supported language clauses around content are strict
original/spoken-language conditions, independently of country; unknown facts
do not satisfy either inclusion or exclusion. Unsupported leftovers clarify.
A parenthesized reference year qualifies the reference identity, not the
recommendations. Explicit uncertain alternatives use exact local identity
choices; no choice or a third ID cannot execute a partial recommendation.

Semantic result metadata optionally includes `result_cap` (default 5),
`rerank_model` and `admission_profile`. SQL and reference exclusions precede the
cap. Absolute thresholds belong to the existing fixed native model only.
`search_rerank_uncalibrated` is an unavailable state, not a correct empty answer;
unknown score scales stop before provider dispatch. No paid provider is enabled.
Snapshot policy v4 binds model/cap; older snapshots require explicit resubmit,
while restore/navigation remain local. See
`docs/features/search-content-boundaries.md` for offline proposal limitations.


### Model-independent strict no-match evidence

For a fully parsed content request, resolved identities and a completed reference
choice, an unavailable model contract does not prevent current strict SQL from
establishing zero confirmed candidates without Decision/embedding/rerank.
Existing calibrated-model snapshot recovery retains its prior behavior. Such discovery.v3 results are ready,
source local, and empty, with semantic.no_match_basis set to
strict_metadata_eligibility. Unknown/conflicted metadata is still not assumed to
match; an empty confirmed set is not an assertion about unknown real facts.
Provider errors and uncalibrated scores remain unavailable, never correct empty.
Saved empty proofs are rechecked on restore/edits; a newly eligible scope requires
a new explicit submission. Ordinary literal/SQL search remains model-free.
