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
- [ ] Record the final freeze and execute the single authorized free public run.
- [ ] Publish measured counts/cost/latency/ranking and failure analysis separately
  from the earlier fictional smoke. Run final relevant suite/CI and independent
  code review before merging the new evaluation code.

## Remaining risks

Small chosen corpus, provisional themes, short rewritten plots and no real
private-library sampling limit conclusions. Ten conflicting durations reduce
hard-filter coverage. Source facts can contain errors; retained revisions and
observations make them reviewable. Real provider behavior/rate limits may stop
the run. None of this enables production semantic search or clears PR28 gates.
