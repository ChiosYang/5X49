# Public-film semantic evaluation

Status: In Progress
Last updated: 2026-10-22
Related: semantic-search-phase-two.md; PR47; enhanced-search-phase-one.md

## Goal

Run a reproducible, separately authorized public-real-film pilot after the
fictional eight-film smoke. Compare keyword, dense and hybrid retrieval without
reading a user's library or enabling production semantic search.

## Scope

- 24 public films, 24 independent questions (12 English and 12 Chinese).
- Four exact identities, six plot-fact requests, eight provisional theme/reference
  requests, four hard-condition plans, two no-answer requests. Two of the eight
  theme cases use a locally resolved reference Film and its document vector.
- One short independently authored bilingual factual document per Film. Every
  method uses exactly the same text. Titles/aliases use fixed public identities;
  no model invents names, facts, SQL, relevance labels or eligibility.
- Selected Wikidata facts are CC0, captured with entity/statement/revision IDs.
  Primary Criterion, A24, BFI and distributor pages support short factual
  paraphrases. Their prose, images, trailers and films are not redistributed.
- Dedicated fixture, source evidence, frozen configuration, safe receipts, vectors
  and an explicit offline replay. No local model/runtime downloads or dependencies.

## Non-goals

- No production API, UI, user database, media, notes or viewing-history changes.
- No chat, reranker, private-library embedding, paid fallback or automatic retry.
- No claims of real-private-library acceptance, independent human gold labels,
  arbitrary natural-language comprehension or statistical generalization.
- PR28's live-quality/budget hold and the old Qwen receipt remain separate.

## Dataset and sources

The committed data is `backend/fixtures/semantic_search/public-movies-v1.json`.
The independent CC0 fact snapshot is `public-movies-sources-v1.json`; each field
and nonzero judgment links to source IDs, whose URLs/access dates/revisions are
in the fixture. The sampling groups are evaluation tools, not new product tags.

| Group | Films |
| --- | --- |
| Family | Tokyo Story; Still Walking; Yi Yi; The Farewell |
| Romance | In the Mood for Love; Chungking Express; Past Lives; Eternal Sunshine of the Spotless Mind |
| Science fiction | Ex Machina; After Yang; Arrival; Moon |
| Everyday life | Perfect Days; Paterson; Ikiru; Living |
| Livelihood | Parasite; Shoplifters; The Florida Project; Minari |
| Memory | After Life; A Ghost Story; Aftersun; Everything Everywhere All at Once |

Still Walking is verified as Q874074 (2008, Hirokazu Koreeda), not the similarly
named 2010 work Q6787651. Stable internal Film IDs derive from the public QIDs.
Only exact source-backed labels/aliases are admitted; no fuzzy identity merge.

Year means the earliest recorded publication/premiere year in the fixed
statements. Territorial later releases remain separate: Minari is 2020, After
Yang 2021 and Living 2022 for this contract. A24's later US theatrical dates and
BFI Player's inconsistent Living catalog-year label do not replace this basis.

All selected whole-minute runtime observations must agree. Ten Films have
unresolved differences; their runtime is null/conflicted, not silently chosen:
Tokyo Story, The Farewell, Chungking Express, Past Lives, Ikiru, Parasite, The
Florida Project, After Life, Aftersun, Everything Everywhere All at Once. The
original values/units remain in evidence. This leaves 14/24 usable runtimes.
In the 2022–2023 / at-most-110-minute case, Past Lives (105/106) and Aftersun
(101/102) are excluded despite both published alternatives meeting the limit.
That is explicit metadata coverage loss, not evidence those films fail the
underlying real-world duration requirement or a way to claim better recall.

## Interpretation and relevance boundaries

The four hard-only cases use explicitly supplied `search-plan.v2` plans. Offline
tests populate isolated public read-model fixtures and run the actual
`SearchPlanExecutor.eligible_ids`; all four agree with the independent metadata
oracle. Missing/conflicted values fail closed. This proves filtering of these
plans, **not** extraction of these exact sentences by a natural-language parser.
The pilot does not send those requests to a chat model.

Four identities and four hard-only plans share local fast paths across all
methods. Report the 16 semantic cases separately so these eight shared outcomes
cannot inflate the embedding comparison. Report each case type and language,
no-answer false positives and hard violations independently.

The eight theme/reference cases use 0–3 graded relevance with a reason for each
nonzero label and an explicit default-zero rationale. Multiple strong neighbors
are allowed; reference Films themselves are excluded. These are provisional
curated judgments, **not independently human-annotated gold**. Hit/recall use
grade >=2; graded nDCG uses gain `2^grade - 1`. Identity/plot/hard facts have
source-backed objective expected IDs. No-answer cases require abstention.

All 24 questions are independent intents, not translated pairs. They form a
small frozen test pilot, with no tuning on this set. Future translated variants
must stay with their original intent's split. Do not change the data, qrels,
threshold (.35), equal RRF weights or k=60 after seeing model results and then
describe the result as an independent test.

## Frozen transport and resource contract

- Fixed `nvidia/nemotron-3.5-embed-8b:free`, only `nvidia/bf16`, model-created
  revision 1792591666, 4096 dimensions and the previous verified task/routing
  fingerprint. Stop if metadata materially changes before dispatch.
- Fresh endpoint price and free-quota checks; every price component must be zero.
  Request price ceilings are zero, provider fallback/retries/redirects disabled.
  Explicit NVIDIA logging/API Trial Terms consent is required; this is not ZDR.
- Only `films[].document_text` and non-null `cases[].embedding_query` leave the
  computer. Source URLs/revisions, qrels, hard facts, local IDs and additional
  title aliases remain local. Private library data is never read.
- Expected 24 document +14 query encodings =38 POSTs/texts; four exact identities
  and four hard-only plans need none, two reference cases reuse document vectors.
  Absolute user-authorized ceiling: 42 POSTs/texts, USD 0. The frozen conservative
  reservation is 15,436 tokens, below the 20,000 bound.
- The synthetic profile retains its old 32-POST limit. The separately named
  public scope permits 42 only with the zero-price NVIDIA quote; it cannot fund a
  paid model. The original Qwen one-call unknown charge and USD .01 hold are
  linked read-only, with no receipt/reservation reset or Qwen retry.
- Before model execution, pin fixture/source/implementation/config hashes in
  `public-movies-v1.freeze.json`. Any changed input/protocol blocks dispatch.
- Atomically save safe ID/model/provider/usage evidence before validation and
  every validated public vector before ranking. A partial/error run cannot
  automatically retry. Existing run roots refuse execution, even after failure.
- Replay uses the frozen saved vectors and in-memory SQLite, with zero HTTP or
  credential lookup. The original fictional smoke did not retain vectors; its
  ranks cannot be retroactively represented as a cosine-score replay.

## Commands

From `backend/`, with existing dependencies:

```bash
uv run python -X utf8 -m unittest test_public_movies test_openrouter_embeddings test_semantic_search -q
uv run python -X utf8 -m app.evaluation.public_movie_pilot
uv run python -X utf8 -m app.evaluation.public_movie_pilot --execute --accept-nvidia-logging --credential-env <existing-deployment-env>
uv run python -X utf8 -m app.evaluation.public_movie_pilot --replay
```

Default preparation has no network, credential or application-DB access. The
execute command is only for the separately authorized frozen public run; never
run it in CI or substitute a new credential source. CLI output omits full inputs,
vectors, credential values and credential locations. Reports/vectors remain in
the ignored owned `.mcp-artifacts/openrouter-public-movies-v1` run directory.

## Acceptance and verification

- [x] Capture 24 source-identified Films and independent EN/ZH questions.
- [x] Validate source provenance, unknown/conflict handling and provisional qrels.
- [x] Cross-check four hard plans with actual local SQL execution in isolated data.
- [x] Prove complete mock execution, 38-vector persistence, zero-network replay,
  no implicit replay, unknown prior receipt retention and the 42-request cap.
- [x] Focused offline suite: 67 tests passed (21.477s); no real provider calls.
- [x] Full local backend: 535 tests passed (3 Windows skips), 293.841s, using a
  byte-verified isolated tracked-source snapshot with blank provider keys. An
  initial restricted Windows run stalled in an existing TestClient case; the
  owned child was stopped, that case passed normally (1.366s), and the complete
  suite then passed with normal execution permissions. No application code was
  changed to bypass the test.
- [x] Freeze `289c657b808e30bad11c61137d1ec3d59db0d43ec7daf32697d732397ee40df3`
  at code head `a836b576b23a3a7325ba710ce50e6e37ecab03b6`, then execute once.
- [x] Retain all 38 public vectors and safe receipts; actual zero-network replay
  reproduced all 72 ranked lists without changing data, qrels or parameters.
- [x] Publish measured public results and saved-artifact hashes in
  `docs/evaluations/public-movies-v1-results.json`, separate from fictional smoke.
- [ ] Final exact-head CI and independent code review before merge.

## Actual public run

Requested model `nvidia/nemotron-3.5-embed-8b:free`, route `nvidia/bf16`.
All 38 responses reported `nvidia/nemotron-3.5-embed-8b` / `Nvidia`; all validated
as 4096D. First/last response: 2026-10-22 09:04:10.127200–09:08:39.802565 UTC.

**38 POSTs /38 texts: 24 documents +14 queries, 1,653 reported tokens, USD 0.**
Every request supplied `usage.cost=0`; no estimate, unreported charge, retries,
fallbacks, chat or reranker calls. The authorized maximum remains 42; the unused
four requests are not spent on tuning. The old Qwen receipt SHA256 is still
`8b5219ef6a0a61e0f03f8c9e7a8d3dd5fe1879a85dbb63e1d487ee7fe8611637`,
with its separate unknown actual cost and USD .01 reservation unchanged.

Compare the **16 semantic cases**, excluding eight shared local fast paths:

| Method | Top-1 / correct abstention | Recall@3 | Graded nDCG@10 | No-answer false positives |
| --- | ---: | ---: | ---: | ---: |
| Keyword | 68.8% | 69.3% | .739 | 1/2 |
| Dense | 75.0% | 62.0% | .680 | 0/2 |
| Hybrid | 75.0% | 67.2% | .743 | 1/2 |

The Top-1 aggregate includes correct abstention for the two no-answer cases; it
is not purely a ranking hit rate. On six concrete plot-fact questions, all three
methods hit Top-1 (6/6). On the eight **provisional** theme/reference questions:

| Method | Top-1 | Recall@3 | Graded nDCG@10 |
| --- | ---: | ---: | ---: |
| Keyword | 50.0% | 51.0% | .603 |
| Dense | 50.0% | 24.0% | .359 |
| Hybrid | 62.5% | 46.9% | .612 |

All four exact identity requests and all four supplied hard plans have exact
expected ID sets for all strategies, with zero hard violations. Again, the hard
plans were injected and SQL-verified; these are not four NLP-extraction passes.
The two runtime-conflict exclusions and 14/24 usable runtimes remain visible.

The eight semantic cases per language give English Top-1 keyword/dense/hybrid
75.0/75.0/87.5%, Chinese 62.5/75.0/62.5%. This selected tiny sample and provisional
judgments do not establish general multilingual quality.

Wall time 275.815s includes deliberate serial pacing. Remote request median/P95
5.437/15.984s. Document requests alone: 1.991/9.552s; fresh query requests alone:
**12.217/16.220s**. These request observations are not a latency guarantee.
Warm local retrieval median/P95: keyword 55.265/66.381ms, dense 61.066/65.574ms,
hybrid 62.544/102.525ms. Warm cache timings must not be advertised as end-to-end
query latency; the Windows machine was also running verification work.

## Frozen-result diagnosis

Only saved vectors/ranks were used; no additional model call or tuning occurred.

- The Chinese romantic-longing request gets no result from any strategy; the
  broad intent does not share literal words with the concise factual plots, and
  dense candidates are below the fixed .35 threshold.
- The technology/companionship/memory query returns Aftersun first in keyword
  and hybrid, solely helped by the generic memory overlap. That misses the
  technology condition; the dense strategy abstains.
- The daily-work/meaning request gives no dense candidates; keyword/hybrid put
  The Florida Project first through `daily`, ahead of the intended work/routine
  neighbors. Token overlap is not full-intent understanding.
- Hybrid recovers the makeshift-family/livelihood request from dense abstention,
  returning Shoplifters. It also regresses on the Chinese no-answer request:
  `电影` alone admits After Life despite no Jupiter-station/courtroom premise.
- Both reference queries put an intended neighbor first (Ikiru → Living; In the
  Mood for Love → Chungking Express), but later ranks include weaker/unrelated
  films. Reference identity was resolved locally; this is not an AI entity claim.

The practical result is mixed: concrete plot lookup works in this small corpus,
but broad theme recall, complete-intent precision and free-endpoint query latency
remain inadequate evidence for a production default. No source facts, judgments
or parameters are rewritten to improve this reported result. Production semantic
routing remains disabled; this evaluation does not complete phase two acceptance.

## Remaining risks

Small chosen corpus, provisional themes, short rewritten plots and no real
private-library sampling limit conclusions. Ten conflicting durations reduce
hard-filter coverage. Source facts can contain errors; retained revisions and
observations make them reviewable. Real provider behavior/rate limits may stop
the run. None of this enables production semantic search or clears PR28 gates.
