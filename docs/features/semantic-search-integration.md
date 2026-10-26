# Explore semantic search integration

Status: In Progress
Last updated: 2026-10-23
Related: semantic-search-phase-two.md, offline-retrieval-optimization.md

## Goal

Use the existing Explore input and Film cards for local exact search, complete
hard filters, content search and reference-Film similarity. Add a native Decision
classifier and a native reranker, with an isolated, resumable library content
index. A mock pipeline is not real-model or real-library acceptance.

## Existing behavior

Main at the start of this task is `10da4f31e63855550d0fd10dffed9de3c485623c`.
Production currently uses literal title/Person aliases, complete EN/ZH local v1/v2
rules and the guarded v1 interpreter. Semantic caches, providers and retrieval
policy are offline modules. No production route currently uses them.

The known persistent default project database has 15 visible Films and 16
editions; titles, original titles, year, runtime, automatic overview and credited
actors/directors cover all 15. Overview text totals 3,172 characters. This was an
aggregate, query-only SQLite read; no media, private reviews, paths, credentials
or viewing records were read. A running service's environment override was not
inspected. Coarse TMDB edition provenance does not prove each historical scalar
field's origin. No source database was modified or indexed.

## Scope and boundaries

- Preserve ordinary search, collections, legacy exact URLs and global search.
- Do not restore Ask/manual filter forms or change the visual system.
- No local models/downloads, automatic scraping or unbounded background indexing.
- Prior trials retain their own receipts. The current explicit logging consent
  is limited to this internal evaluation; Qwen's old unknown charge and USD 0.01
  reservation remain separate and untouched.
- PR28's live-quality hold remains separate.
- The latest authorization covers internal evaluation only: selected free models,
  public evaluation data and a public-metadata whitelist from the 15-Film
  persistent test database. Maximum 320 inference POSTs, zero price, no recharge
  or paid fallback. Production enablement is not authorized by this trial.
  Default configuration makes no network call or key lookup.

## Architecture and decisions

1. Local exact identities and complete local hard plans bypass Decision. A
   finite choice classifier may route remaining content requests; it cannot
   invent identities, extract arbitrary filters, run SQL or call tools.
2. The selected native APIs are OpenRouter `/api/v1/systemone`,
   `/api/v1/embeddings` and `/api/v1/rerank`, not chat substitutes. Models are
   `baseten/mammoth-1:free` / `baseten`,
   `nvidia/nemotron-3.5-embed-8b:free` / `nvidia/bf16` and
   `nvidia/nemotron-3.5-rerank-8b:free` / `nvidia/bf16`. Check zero prices and
   active endpoint status before dispatch. Mammoth currently appears on the
   public ZDR list. NVIDIA requires this trial's explicit public-input logging
   consent, only inside an evaluation scope. Do not apply that exception to
   private libraries or normal production. No paid or alternate-provider fallback.
3. A shared durable ledger reserves before dispatch, records safe response IDs,
   model/provider and usage before validating billing, and stops on uncertainty.
   No SDK retries. An interrupted call is not automatically replayed. Estimates
   and conservative unreported-cost holds remain distinct.
4. Local SQL resolves identities and intersects every hard condition before
   candidate ranking, reranking, counts and display. Unknown facts fail strict
   positive/negative requirements. Semantic preferences are labeled relevance,
   not asserted facts; unsupported hard clauses need clarification.
5. Only approved public title/alias/overview/credit/tag fields enter a separate
   model/provider/version-scoped content cache. Paths, personal edits, reviews,
   ratings and viewing state are excluded. Jobs are explicit, cancellable and
   resumable; changed document digests are incremental. Source DB stays intact.
6. Query snapshots retain validated local plans, query vectors and ranking
   evidence. Restore, Back, Return, pagination, chip edits and viewing mutations
   never trigger another model call. Reapply current SQL eligibility and clamp a
   shrinking last page. Expired/stale snapshots explain the problem and preserve
   ordinary search; they do not silently rerun inference.
7. Rerank at most 20 candidates with bounded excerpts. Validate finite scores,
   unique in-range indices and the selected model/provider. It cannot introduce
   a Film outside the candidate set or bypass SQL. Service failures retain local
   search and explicitly disclose the fallback instead of reporting false zeroes.

## Acceptance criteria

- [x] Strict provider/privacy/billing contracts and adversarial mock tests.
- [ ] Local fast paths, complete hard-plan/content separation and finite routing:
  deterministic checks pass, but real acceptance exposed coverage/identity bugs.
- [x] User-visible Explore results with cancellation, restoration and honest errors
  verified using synthetic native transports.
- [x] Isolated incremental index with provenance, versioning and restart tests.
- [x] Existing navigation, mutation, page-boundary and privacy regressions pass.
- [ ] Independent unseen protocol/config/thresholds frozen before revealing cases.
- [ ] Approved real adapters, frozen holdout and bounded real-library validation.
- [ ] Same-head full CI and independent review; normal merge and safe local main FF.

## Authorized internal evaluation scope

The user approved a single shared cap of **320 free inference POSTs**, no recharge:
64 public Films (40 new, 24 prior distractors), 60 independent EN/ZH holdout
intents, the 15-Film actual index and at most 10 library-validation queries,
including development checks. Recipients are OpenRouter, BaseTen and NVIDIA.
NVIDIA records inputs for security/product improvement and its API Trial Terms
limit this use to internal evaluation, without confidential/personal data.
Query text and bounded approved public metadata are the only payloads. The
user clarified that the persistent project database is itself a test library;
this does not establish public provenance for arbitrary fields. Exclude any
field of doubtful origin and report the resulting coverage loss.

The prior 24 questions are development/diagnostic data, never unseen acceptance.
Old NVIDIA vectors may only be reused when exact wire text, provider/model,
query/passage mode and dimensions match; otherwise encode separately under the
same 320-request cap. Freeze actual configuration before opening the isolated new
questions/qrels. Theme relevance is provisional graded judgment with provenance,
not human gold. Report answerable ranking separately from no-answer decisions,
CN/EN and intent groups, candidate recall at small K, hard violations, erroneous
abstentions/false positives, routing errors, end-to-end latency and actual costs.
Do not tune on holdout then label the rerun independent.

## Slices

### 1. Native transports and authorization boundary

Status: Implemented and locally verified; independent code review pending

Strict schemas, endpoint/price/privacy preflight, bounded payloads, shared ledger
and synthetic transports. No new credentials or default egress.

### 2. Index, orchestration and Explore

Status: Implemented and locally verified; live test-library acceptance incomplete

Public-content extraction, resumable cache, SQL eligibility, route decisions,
bounded reranking, snapshots and the existing UI. Mock and local fixture checks.

### 3. Real acceptance and delivery

Status: In Progress; public execution complete, independent quality gate failed;
persistent test-library execution interrupted

Freeze protocol, run only approved calls, keep safe receipts and vectors, report
quality honestly, then commit/push/draft after implementation/local checks.
Independent review and same-head CI precede merge. After merge safely fast-forward
`D:\Projects\5X49` main only when tracked state and ancestry allow it; preserve
untracked files and stop instead of resetting dirty/diverged work.

## Verification evidence

- Branch `ai/semantic-search-integration` starts at current main; clean on entry.
- Read-only aggregate inventory completed; database size and mtime unchanged.
- Official Decision/rerank request and response documentation inspected.
- Provider, runtime, orchestration and existing search targeted checks: 83 passed;
  freeze/input-separation checks: 3 passed. The additional shared-language guard
  and freeze regressions passed 25 checks before revealing holdout questions.
- Frontend lint/typecheck and 140 unit checks passed. Eight browser checks passed
  EN/ZH, 1440px/320px, actual rendering, sort, refresh, Back/Return, chip removal,
  explicit cancellation, fallback and stale snapshots. They use synthetic native
  transports and do not establish real-model quality.
- All three selected native APIs returned valid real responses. Explicit fixed
  dated/native response aliases were checked against official endpoint metadata;
  the two initial stops, receipts and zero charges remain recorded.
- Live development totals: 48 POSTs, 47,678 tokens, reported USD 0, no uncertain
  receipts. Original 38 model/text/mode-bound vectors were verified and reused;
  the second development run reparsed 12 exact settled Decision responses.
- Old dev v1 reports/configuration are immutable. Separately archived dev v2
  has 12/14 answerable semantic Top-1 hits, Recall@3 .65476, nDCG@10 .72645,
  4/4 hard-condition exact sets and 2/2 correct no-answer outcomes. Two broad
  themes are wrongly rejected. These are tuned development results, not unseen
  quality acceptance or a claim of general improvement.
- Real receipt latency: Decision n=14 median .75s (.57-1.09s); native rerank n=12
  median .73s (.54-1.94s); two uncached query embeddings took 5.91/13.36s; one
  cold document encoding took 16.90s. Cached query-vector reads are about 1ms;
  local index/retrieval about 80-95ms on this small corpus. This does not include
  a measured real browser end-to-end distribution or prove the cause of remote
  delay. Redundant per-row public preflight GETs in the first development runner
  were removed, keeping the enforced 300-second quote expiry.
- The independent corpus-only transfer passed exact SHA256
  `6a3ed86909e95c058db3be1bbb64d6e60f47403a04e3509e6f3acb70fd3028ec`
  (225,932 bytes, 64 films); original 24 document texts remain unchanged.
- Full backend suite: 625 tests passed, three skipped; frontend full E2E: 280
  passed. These full runs precede the final unsupported-metadata guard; its
  final focused suite passed 26 checks. Two new shared-ledger concurrency
  checks also passed. The extra delayed-navigation browser check separately
  passed against a newly built application: a new submission remains current
  while the older native Decision completes; no cancelled follow-on inference.
- Final backend source snapshot: 635 tests passed, three skipped, exit 0, including
  the final guard, concurrency and seven explicit-recovery/partial-body tests.
  This run blanks API keys and uses an owned temporary source/database snapshot.

### Frozen execution, explicit continuation and results

The 60 execution-only questions were received after the effective v3 freeze.
Their saved array SHA256 is
`91a0dba729b2f6aedcfb2658bb1517c5dc60f2fa13593b95c5267590284ec74d`.
The native/local route mapping was documented at 04:36:12 UTC after the parent
handoff had revealed question text around 04:35 UTC. It precedes input-file
creation at 04:36:50, which does **not** establish a pre-reveal mapping freeze.
Earlier commentary overstated that ordering. Route classification therefore has
a protocol deviation and uses a provisional mapping, while the underlying
enum, prompt, parser and behavior source hashes were already frozen before
reveal. Original evidence and timestamps are retained. No qrels or expected
identities were supplied to the implementation or models.

An initial unauthenticated metadata GET failed before any inference; the shared
ledger remained at 48 and all four public GETs subsequently returned HTTP 200.
The unchanged run then acknowledged request 49: four public document vectors,
392 tokens, USD 0, 18.218 seconds. Request 50 dispatched the next embedding batch
but returned no response within 20.015 seconds. No request ID or usage was
captured for that attempt. The ledger halted with `search_provider_unavailable`;
its uncertain receipt, request count and partial acknowledged cache are retained.

At this first interruption attempts were 50/320, acknowledged tokens 48,070,
reported cost USD 0. The
unreported bound is USD 0 only because the prechecked fixed endpoint's permitted
price is zero; it does **not** mean request 50 returned a zero-cost receipt.
At that point zero acceptance questions had executed. No automatic retry,
ledger reset, provider change or frozen-source change followed the interruption.

Read-only reconstruction matched request 50's original four-text batch to its
ledger input hash. Its exact UTC dispatch timestamp and HTTP headers were not
recorded. Filesystem evidence bounds the attempt between 04:38:20.479 and
04:38:40.626 UTC on 2026-10-23, rather than proving an exact send time. The
generic stored exception cannot distinguish connection, response-header or
response-body failure. No previous HTTP 403 Activity lookup was retried and no
alternative credential/account path was used. Twenty-eight acknowledged passage
vectors (24 historical plus four new) remain durable; the complete generation
was not activated. Model execution and usage for request 50 remain unknown.

The persistent test-library public-field review subsequently prepared fourteen
of fifteen Films, using original titles and automatic overview values bound by
SHA256 and official public-source URLs. One award/promotional-heavy overview
was excluded pending complete source verification; ordinary local lookup still
covers it. The existing runtime accepted this manifest against a read-only
source connection and created an isolated pending fourteen-chunk job. Ten test
queries were prepared without a provider call. Source size/mtime were unchanged. A
69-test native/index/runtime/evaluation/concurrency unit run passed after the
freeze; no acceptance parameters or source hashes changed.

The user subsequently authorized exactly one repeated four-document attempt,
retaining uncertain receipt 50 and allowing only indexing transport timeout to
change from 20 to 60 seconds. Receipt 51 succeeded in 7,862.112ms, 423 tokens,
reported cost USD 0; its request ID and identical input hash link it to receipt
50. The four vectors were saved before the continuation lock was released.
The original uncertain receipt, NULL cost and historical halt remain intact;
an explicit recovery view permits only the authorized continuation. Standard
budget instances still fail closed, and any new uncertainty blocks that view.
The infrastructure appendix SHA256 is
`d5b60831044fe927325745c64c7befef2f0e9e7c3566cb3db2b497ca6c43529d`;
the separate execution envelope is
`f66a6c35cd1cf0039bb9520d413276acf487c71dbe51f9b530f1f322395020cc`.
Query embedding (20s), Decision (5s), rerank (10s), models, prompts, local
filters and ranking thresholds did not change. Questions were already revealed,
but none had executed when this infrastructure-only continuation was authorized;
this is not a pristine run of the original frozen infrastructure.

All 60 public questions then executed once. Their immutable outputs retain
plans, candidates, native index-to-Film mappings, final displayed IDs, raw
scores, A/B/C/D availability, stage validity/application/fallback flags, safe
usage and timing. No qrels were loaded and no parameter was adjusted from these
outputs. Public completion used 136 total POSTs (including 48 development
attempts), 100,981 reported tokens and reported cost USD 0, with receipt 50 still
unknown. Public query stages used 29 Decision, 24 query embedding and 24 rerank
POSTs; the remainder were local paths or explicit clarifications.

Observed statuses were 24 ready, seven keyword, 27 clarify and two
needs_clarification. Only 16/60 displayed a Film; the first eight identity cases
all displayed none. The predeclared all-eight identity gate therefore cannot be
claimed passed. These observations are not an independent ranking score or an
excuse to tune and rerun the revealed holdout. Independent scoring on
the parent side confirmed failure; a second reviewer reproduced it. The compact scoring
export is 152,321 UTF-8 bytes, SHA256
`5f258fe8130cecaf964afb856def4316cc29f8cff4cb3e7387961af50558f1cb`;
ranking integers reference its zero-based Film ID dictionary.

The independent scorer's confirmed result is a failed acceptance gate:
identity Top-1 0/8, plot Top-3 9/12 and combined-condition Top-3 0/8. Three
executed similarity requests included their reference Film. These are
end-to-end engineering/coverage failures, not isolated embedding-quality scores.
The original outputs, sources and thresholds remain unchanged. Read-only triage
confirmed all seven keyword outcomes executed the real SQL lookup; sentence
wrappers/punctuation remained in the literal term, while direct known-title
lookups could succeed. The bounded content splitter also routes unseparated
year/person/plot text through legacy unsupported guards or captures plot text
as a Person. One compound case has duplicate fixture Person identities from
separate Wikidata/public-source namespaces. Broad similarity phrasing can fall
through to semantic search without a bound reference/exclusion. Subsequent
fixes need a separate implementation/evaluation version, not a rewritten pass.

The independent calculation reports 16/54 answerable queries with
nonempty displayed results and overall nDCG@5 .2562. Among the 24 actually
executed semantic cases, candidate Recall@20 is .9722 and raw pre-/post-rerank
nDCG@5 is .8728/.9272, dropping to .5763 after final admission. Eight of those
24 are emptied by the frozen factual .09 threshold: their highest native scores
are .0566-.0875. These subgroup diagnostics cannot replace the failed whole-task
acceptance, and no threshold adjustment or model rerun follows them.

All 27 clarify outcomes are distinct from established no-match results: six
negation, seven unsupported_filter, two multiple_values, eight
incomplete_request and four unsupported_content_negation. Two additional
needs_clarification outcomes contain unresolved Persons. The latter content
negation reason was missing from the original frontend reason whitelist, so those four
cases display the generic "Search could not complete" reason under the clarify
heading. This is a user-visible mapping gap, not a model timeout.

The executed input file is a 7,623-byte JSON array. Its raw-byte SHA256 is the
reported `91a0dba7...`; this is not the hash of the parent's differently wrapped
transport document. Serializing the 60 rows with UTF-8, ensure_ascii=false,
sort_keys=true and separators comma/colon gives SHA256
`747d24538e1606a552642e0325356ff4ea849f07b1129a16d915f76b347a711d`.
The same canonical hash and exact string/order equality hold when extracting
id/locale/question from all immutable outputs. No text/case/Unicode normalization
is applied by this equivalence proof. Per-row hashes are separately preserved;
the original execution file is not rewritten to match a transport hash.

Across all 60 cases, including fast local clarifications, measured submission
pipeline median was 156.64ms, p95 19.014s and maximum 21.274s. The end-to-end
boundary covers required preflight and actual ID extraction; it excludes corpus
indexing, offline ablations, serialization and browser rendering. This mixture
does not represent a median uncached semantic request or a real-browser latency
distribution. Saved per-stage receipts permit that narrower analysis without
new inference.

Public-query receipt timings are Decision n=29 median 615.364ms / p95
1,487.558ms, query embedding n=24 median 6,924.215ms / p95 17,483.623ms and rerank
n=24 median 869.754ms / p95 1,376.237ms. These measure individual client transport
stages, not server-side queue time; a slow provider stage does not establish its
cause. No extra timing-only inference was made.

The independent report's nearest-rank p50 is 8.801s for the 24 semantic cases
and 41.911ms for all 60. For even-sized samples the statistics.median convention
averages two middle values instead: 9.146s and 156.644ms. These are the same
observations under different percentile conventions. Use the protocol's
nearest-rank values when comparing its results; neither all-case summary
represents uncached semantic-search latency.

### Persistent test-library interruption

After explicit source-to-recipient consent, the isolated read-only test-library
command was approved and executed once. Its first four-document embedding
attempt is receipt 137, dispatched at 2026-10-23 06:31:49.113310 UTC to the fixed
NVIDIA free embedding endpoint. HTTP 200 headers arrived at 06:32:01.300930 UTC,
but response-body reading raised ChunkedEncodingError at 06:32:01.390149 UTC.
Elapsed time was 12,281.815ms, not the configured 60-second index timeout.
There was no complete JSON, request ID, usage or vector response. Safe transport
trace and the original input digest remain local; remote execution and cost are
unknown. The new uncertainty halts all further dispatch. No repeat is authorized
or attempted, and no historical receipt is cleared.

Current totals are 137/320 POSTs, reported USD 0 and two unknown receipts (50,
137). Reported zero is not a returned zero-cost receipt for either unknown call.
The pending 14-Film generation has zero saved vectors and 0/10 validation
queries executed. A read-only post-interruption revision check still matches
the reviewed source hashes. Its whitelist, membership, trace and source details
are local evaluation artifacts rather than committed public test data. Public
60-case results and their original freeze remain unchanged. Seven deterministic
recovery/partial-body regressions pass; they do not establish a live retry or
test-library acceptance.

## Independent execution freeze

Effective configuration SHA256:
`f3286a9dc2a0c432347e4b35e673762c65129dac1452ba4ca28b56e693d39f79`.
It binds 24 normalized source hashes, fixed models/providers, prompt/schema,
candidate K=20, native score thresholds factual .09 / exploratory .04 /
reference .06, Decision confidence .6 and conservative factual mode on uncertain
intent, 5/20/10-second inference timeouts and zero-price/no-retry fallback rules.
Native scores are relevance evidence, not probabilities. This policy was chosen
using old dev observations and has not passed independent validation.

The earlier configurations `c8bce407...` and `68f891e3...` are retained but
superseded **before any execution questions were received** to preserve all
existing unsupported metadata guards, including producer/writer, rating,
favorite/note requests and all 14 language-condition forms. Protected explicit
plot spans may describe a writer or a linguist as a story subject. No model
call was made for these completeness corrections; 26 focused checks passed.

`app.evaluation.search_holdout --freeze-only` has no network/key access. Execution
accepts only 60 unique id/locale/question rows, CN30/EN30; extra qrels, expected
IDs or hard plans are rejected. Labels and scoring remain on the independent
side. Immutable outputs retain ordered candidates/final IDs, native/lexical/raw
scores, three local baselines, source status, plans, safe receipts and timings.
The precommitted annotated package SHA256 is
`b26dce46353c86f3b43e84db005301cf257fd734dc5498c408318d220e191703`.
The first freeze uses base main `10da4f31...`; no early/incomplete PR is published.

The evaluation server is a single-process opt-in instance. Explicit random
request-owner IDs plus a bounded cancellation registry cross HTTP proxies;
in-flight responses are settled, but no later model stage starts after observed
cancellation. This is not a multi-worker distributed cancellation service.

## Remaining risks

Free availability and independent multilingual quality still require acceptance.
The frozen native thresholds are development-calibrated; the held-out assessment
failed and remains failed after the separately versioned engineering fixes below.
A prior paid proposal was superseded without any inference: its
Fireworks reranker returned inactive status -2 during public preflight.
Historical scalar provenance reduces exportable coverage: the reviewed pending
test-library job covers fourteen of fifteen Films; coarse TMDB flags alone are
deliberately insufficient. Encoding and the maximum ten validation queries
remain blocked by new uncertain receipt 137. Public holdout execution and scoring
are complete, with identity, compound-condition and exclusion gate failures;
no real quality acceptance is claimed. The complete real browser latency
distribution also remains unverified. A separate
compliant provider/authorization will be needed for formal production use;
successful free evaluation does not complete that part of the original goal.

## Post-failure engineering regression v4 (zero network)

The original 24 source files were archived before repairs in
`holdout-failed-v3-source.zip`, SHA256
`e2be502e84c3441f9c5ad7fb860a60544f4a9c560c327c47aa840200df83d198`.
The original freeze, corpus, execution questions, outputs and independent FAIL
were not rewritten. No qrels were supplied to the implementation.

General repairs bind complete title wrappers to local identities, preserve
title punctuation, execute positive/negative Film IDs with the existing SQL
conditions, segment v2 metadata before the legacy guard, retain distinct Person
identities and bind/exclude reference Films on submission and restoration.
Unsupported content negation now has a specific EN/ZH explanation. Unknown
constraints still stop execution. Native admission thresholds remain unchanged.

`python -m app.evaluation.search_seen_replay` is an offline-only diagnostic.
It blocks sockets/HTTP, has no credential supplier, opens the original ledger
and public database read-only and copies the vector index into memory. It checks
the original configuration hash and input binding, settled receipt identity and
usage, exact model/provider/request body (including candidate order), and native
response validation. It can only reuse exact text/mode/model-bound vectors and
matching responses from the original assessment. Missing evidence is unverified;
it does not synthesize model output or substitute a development response.

The separately saved 60-case replay configuration is
`942a6c83e5652e638d088011d523086ef6461abbbf0858e6bfc1c1f858c06e42`.
Its report SHA256 is
`d39b466c6fbd978df822505b04c96a52c4bf4dbf4f34d973de070d238938a3ed`.
Observed states: 8 keyword, 28 ready, 16 clarify, 3 needs_clarification and 5
unavailable; 25 nonempty outputs. Twenty-nine cases used only local execution;
21 had complete evidence for every attempted recorded stage; 10 lacked an exact
recording. Stage completeness is not a semantic relevance score.

All eight original entity inputs now return their exact local Film identity,
without model inference. Five reference inputs bind an ID and exclude it from
all displayed results; their changed rerank bodies have no exact saved response,
so these are local retrieval/exclusion checks with disclosed fallback, not a
validated new rerank result. Five newly reachable compound requests likewise
lack their newly required Decision responses. Other compound requests still need
unsupported-language clarification or unresolved Person identity handling. The
fixture has two distinct Akira Kurosawa IDs and lacks a reliable Chinese alias;
the implementation neither merges by name nor alters the frozen corpus.

Known exact-only requests execute identity-bound local SQL and return no substitutes.
Unknown exact-only requests explain the missing identity instead of executing a
contains search; the ordinary-search recovery remains an explicit user action.
Unsupported/contradictory requests that clarify are not automatically counted as
correct no-answer outcomes. Broad-theme erroneous rejection remains unresolved.
These are **seen regression diagnostics**, not a replacement independent pass.
Current dispatch count remains 137/320, with unknown receipts 50 and 137 retained;
known reported cost is zero and total cost is not finalized. Persistent test-library
indexing remains at zero saved vectors and zero validation queries.

### Historical-contract compatibility verification

The full backend suite caught the old public pilot's intentional source-lock
failure when the shared factual contract acquired local Film-ID fields. The
repair keeps `contracts/search_plan.py` identical to the historical source and
layers local bindings in `contracts/bound_search_plan.py`. Empty binding fields
are omitted so ordinary v2 payloads and the offline model contract remain
compatible. The executor upgrades factual plans locally; it does not relax the
historical manifest or ask a model to generate identity IDs.

The compatibility revision was replayed without network as a separate record:
configuration `4eb3053383994fc5d1af6c0b92b23aa770011546f6b18344fbf2de38eb7e1939`,
report `582ecbcca963676cc15fc0ce40317c4be04f147fe1e5ca87fdd3ac7fa466d32b`.
All 60 status/ordered-output pairs match the earlier v4 engineering replay;
the 29 local-only, 21 complete-recording and 10 unverified counts are unchanged.
Both reports remain saved. This compatibility check is not another live or
independent quality assessment.

### Exact-only identity boundary

An explicit request for only one named Film must not include a sequel merely
because its title contains the same text. Complete English/Chinese exact-only
wrappers now bind one trusted local Film ID; an absent or ambiguous identity
clarifies. Ordinary keyword wrappers retain normal search behavior, and a known
complete punctuation-bearing title still takes precedence over wrapper parsing.
Regression fixtures cover a prefix-sharing sequel, ambiguous identities, unknown
titles and actual SQL eligibility without any model call.

The final zero-network replay is saved separately with configuration SHA256
`d7f859bc1a4e34345565d532e1fcc60a10fa05d784af564af5c6bfbc2617cb8b`
and report SHA256
`ce1974a929b6ab25c68621b836158ee718b8deb54597128dc7c870b9a03ac809`.
It has 6 keyword, 28 ready, 18 clarify, 3 needs_clarification and 5 unavailable
states. The two absent exact-only requests changed from keyword/empty SQL results
to explicit `unknown_film` clarification; all other ordered outputs are unchanged.
The 8 entity identities, 5 bound/excluded references, 25 nonempty outputs and
29 local / 21 complete-recording / 10 missing-recording counts are unchanged.
The 55 focused identity, integration, runtime and replay tests passed.

### Final local verification of the repair

The final complete backend suite ran 659 tests with no failures and three Windows
skips (two symlink-permission checks and the POSIX read-only acceptance case).
Frontend unit tests passed 143/143; lint, TypeScript and the production build
passed. The backend snapshot used for the full run had manifest SHA256
`a01ca474d10e2baf1223b2f17c172cb53993e2bca0163d0710ae4ef546a12077`.
The separate RC-tooling suite had 12 passes, one skip and two environment errors:
this Windows host has no Docker executable. CI must verify those Docker checks.

Local Windows validation requires the canonical `Administrator` temporary path:
the host's `ADMINI~1` alias differs from Python's resolved path and causes existing
synthetic scan/root assertions to fail. The initial browser run's logs were
retained, and the full suite was rerun with canonical TEMP/TMP and permitted
loopback servers. No production filesystem guard or test assertion was relaxed.
All test providers are synthetic and model credentials are blank.

The canonical-path browser run completed with 281 passes and two Chinese
semantic-navigation failures. Their traces showed Back/Forward started together
without awaiting the intervening detail page: the screenshot check raced a
pending navigation. The regression now awaits the detail URL/Return button and
the restored result URL/cards before inspecting pixels, retaining the original
zero-additional-model-call assertion. Both failure traces are preserved locally.
The final complete rerun includes this wait repair and exact-only identity binding.
It finished successfully: **283/283 E2E tests, exit 0, 15.0 minutes**. The four
EN/ZH 1440px/320px result screenshots were inspected, with no horizontal overflow.
The final test-library keyword-collection alignment was then covered by the
58-test targeted backend suite and compile check, both successful. No runtime
ranking, model configuration or frozen replay output changed in that alignment.

### Original bounded recovery proposal

This section records the pre-authorization proposal, not the latest run status.

The reviewed persistent-library manifest contains 14 documents and 14 chunks.
With the existing four-chunk batch limit, completing its index requires four
requests: one separately authorized repeat of request 137's same four texts,
then three batches for the remaining ten texts. The original unknown receipt
must remain unknown and linked to the new attempt. Ten existing validation
queries need at most 30 further requests (Decision, query embedding, rerank);
local fast paths and exact caches can reduce this maximum.

Only ten seen-regression cases lack recordings. Five newly reachable compound
requests need at most three stages each; five bound-reference requests need at
most one rerank each. Their upper bound is 20 requests, not another complete
60-query assessment. Thus the proposed additional maximum is 1 + 3 + 30 + 20 =
54, bringing the shared attempted count from 137 to at most 191 of 320. This is
a planning bound, not permission to dispatch or a forecast of successful calls.

No recovery was executed. Receipts 50 and 137, the current halt, all previous
artifacts and the old Qwen reservation remain intact. After explicit approval,
recovery needs a separate versioned configuration, fresh zero-price/provider
checks and unchanged-source/allowlist verification before dispatch. Any further
uncertain result stops that sequence. Revised seen results cannot replace the
original independent FAIL. The unexecuted test-library result collector now uses
the API's resolved `keyword_query`, as the page and offline replay already do,
instead of reinterpreting the raw input with the older keyword helper.

### PR50 review corrections: HTTP submission and explicit plan edits

Browser cancellation owners now use secure `getRandomValues` entropy, which is
available on HTTP LAN origins without `randomUUID`. A missing/failing entropy API
leaves the optional owner absent; it does not prevent ordinary search submission
or replace an ownership capability with predictable randomness.

Bound-title edits revalidate the complete original literal binding before
executing the corrected plan. Unsupported qualifiers and unedited substitutions
still fail; corrected unknown IDs still require clarification. Removing a content
chip retains the opaque snapshot plus an explicit `semantic_removed` flag. The
server validates that original binding and executes the remaining plan in local
SQL. The original text is display/history context, not an unhandled condition or
an excuse to drop other hard requirements. Further edits and navigation preserve
this state. The snapshot still expires and invalid proof is rejected.

New regressions assert actual result IDs after sorting/removing title/year/content
conditions, including EN/ZH refresh/Back/Return. HTTP API-absence tests cover
ordinary search with evaluation disabled and explicit cancellation with no UUID
API. This changes restoration behavior only; admission thresholds, model settings,
the original failed assessment, all replay artifacts and request accounting remain
unchanged. No new provider request was made.

Review-fix verification passed: 71 backend identity/runtime/integration/discovery
tests, eight evaluation/replay tests, Python compile, 146 frontend unit tests,
lint, TypeScript, the production build, and all 15 semantic browser tests.
These browser assertions check actual result IDs, retained hard filters and zero
additional provider calls, rather than only the disappearance of a banner.
The original-head CI passed Frontend and 283 E2E tests; Backend timed out during
Ubuntu package download before running any tests. The correction head requires
its own complete CI and independent incremental review.

Correction-head CI `39930937426` passed 661 backend tests (one skip), compile,
15 RC tests and all frontend checks (146 unit tests, audit zero). E2E completed
with 287 passes and one test-precondition failure: the unique-title picker looked
only at the capped 12-film index fixture. Its selected title had a second Film
outside that subset; the saved trace correctly returned both distinct IDs.
The test now checks uniqueness against the complete local library, retaining all
one-film, sort, removal, history and zero-call assertions. No product code changed.
All 15 semantic browser regressions, lint and typecheck passed after this repair;
the runner also rebuilt the production frontend successfully. The failing trace
and archive (SHA256 `2042031f653f04cc455e392554a1e4e27ec1978b28364bbda4a949f31450865e`)
remain preserved locally. A fresh correction-head CI is still required.

### Bounded validation resumption tooling

The explicit evaluation runner can append a supplemental, expiring grant to the
same receipt ledger after separately approved recovery. It binds the unchanged
historical receipts and metadata, the exact interrupted batch and each remaining
document batch. It preserves the original grant and halt; the ordinary runtime
does not inherit this supplemental permission. The repeated batch must have both
a settled zero-price receipt and durable cached vectors before any later phase.

Document, test-library query and missing seen-regression stages have separate
limits under the shared total. A new uncertain response, including an HTTP 429
without billing evidence, stops every later stage. Restarting the runner cannot
retry it, erase its receipt, read a credential or construct a provider after that
stop. Successful batches and saved query outputs are reused without dispatch.

The source library is opened read-only; vectors, snapshots and immutable run
evidence remain in the task's ignored evaluation directory. Missing seen stages
first attempt exact recorded request/response matching, then use only the
explicitly bounded live allowance. A model failure with local fallback and an
unexecuted query remain distinguishable from successful model validation.
This tooling neither revises the original independent assessment nor enables
production search. Actual validation results and reconciliation evidence stay
in the local run artifacts, separate from this implementation description.

Verification: 92 offline backend tests passed, covering the supplemental ledger,
recovery, providers, exact replay, runtime, index, integration and concurrency.
Python compile and diff whitespace checks passed. The initial restricted Windows
run stopped in asyncio's loopback socket-pair initialization; the diagnostic log
is retained. The same suite passed with local loopback permitted and blank model
credentials. No frontend or production-search behavior changed in this increment.

### Explicit reference comparison focus

Reference search still binds and excludes the reference Film before forming a
bounded candidate set from its content vector. When the user supplies a specific
comparison aspect before or after the title, that aspect is the rerank query.
Whole-reference plot text is used only for a plain similarity request. Only
complete recommendation or courtesy scaffolding is treated as empty focus.
A bounded English/Chinese vocabulary classifies the whole segment, including
recommendation questions and punctuation-separated courtesy phrases. It never
removes individual words from substantive content: any unknown word retains the
complete comparison aspect. Theme, style, plot and negation words are excluded
from this scaffolding vocabulary. A recommendation cue after a known reference
also preserves a substantive comparison that follows it. Hard clauses,
unsupported negation and ambiguous identities retain their existing validation.

If focused rerank is unavailable, local fallback requires substantive literal
evidence for the aspect as well as reference-content support. Reference cosine
alone cannot prove that the requested aspect matches. This is conservative and
can abstain on paraphrases. Candidate generation and native score thresholds are
unchanged; a response for a previous whole-plot query is not reusable for the new
focus query. The policy fingerprint invalidates earlier snapshots, while refresh
of a current snapshot remains model-free. Missing exact recorded responses remain
unverified; this correction does not itself establish retrieval quality.

Verification: 141 affected offline backend tests and 15 semantic-search browser
regressions passed, including the build and EN/ZH desktop/narrow viewports. The
full local backend run encountered an unrelated Gate B backup-manifest temporary
path error at 261 characters on Windows; its failure is retained and is not
reported as a passing full suite. Linux CI remains a separate required check.

Follow-up verification reproduced that Gate B failure with a long temporary run
basename, then passed the original test with a shorter unique basename under
the same validated run root. Its assertions and source hash were unchanged;
the longest observed temporary file path was 253 characters. The same local
harness completed all 678 backend tests (three platform skips). After adding
the polite-reference fallback regression, the final 56 focused tests also passed,
including whole-reference rerank input, unchanged fallback results, substantive
EN/ZH comparison aspects, retained unsupported-condition rejection and obsolete
snapshot rejection. All 15 semantic browser regressions and their production
build passed again. No application filesystem limit, assertion or system
security setting was relaxed. The follow-up commit still requires its own CI
and independent review.

The complete-question follow-up passed 59 focused backend tests. Its new cases
cover 14 English/Chinese recommendation templates with two reference identities,
both native-rerank and local-fallback paths, substantive theme/style/plot wording,
hard conditions, private-path rejection and obsolete-snapshot invalidation.
All 682 backend tests passed with the same short-path harness (three platform
skips), as did 146 frontend unit tests, lint, typecheck, Python compilation and
the production build. The first browser run retained a JavaScript resource
`ERR_NO_BUFFER_SPACE` failure before hydration; after the backend run finished,
the unchanged 15-test browser suite passed in isolation. Earlier restricted
temporary-directory/loopback failures remain recorded rather than counted as
passes. No threshold, transport limit or test assertion was relaxed.
