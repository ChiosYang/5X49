# Offline retrieval optimization

Status: In Progress
Last updated: 2026-10-23
Related: semantic-search-phase-two.md; public-movie-semantic-evaluation.md; PR48

## Goal and boundary

Separate bounded candidate recall, ordering and display admission. Reuse the 38
previously recorded NVIDIA vectors, without network, credentials, private library
reads, new accounting or production wiring. Existing search/navigation and the
historical semantic implementation remain unchanged.

The 24 public questions have already been inspected. They are now a diagnostic /
regression set, NOT an independent test set. Original documents, qrels, freeze,
evaluator, vectors and historical results must remain byte-for-byte unchanged.
Themes remain provisional. Four injected hard plans prove SQL execution, not NLP.

## Implementation decisions, before the new comparison

- New opt-in pure retrieval module; no provider/Decision/reranker or network API.
- At most 20 candidates per modality (maximum configurable bound 100). Hard IDs
  supplied by the existing SQL executor are intersected before Top-K. Reference
  content excludes itself and uses a separate score policy from natural language.
- BM25 k1=1.2, b=.75, positive smoothed IDF; English case/NFKC/limited suffix
  normalization, CJK bigrams plus low-weight character evidence. Generic search
  terms have negligible weight and cannot independently admit a result. Exact
  complete title/alias matches bypass token reduction; stable IDs stay distinct.
- RRF k=60 orders candidates; its score is neither probability nor admission.
- Admission uses original cosine, weighted substantive lexical coverage and
  clause coverage, with explicit reason codes. Broad themes and strict factual
  requests have separate policies; reference comparisons use document vectors.
  These heuristics are experimental and cannot verify arbitrary paraphrased
  conjunctions. No Top-1/Top-2 margin rule or per-film/per-question exceptions.
- Diagnostic intent modes use the fixture's existing category annotations:
  plot/no-answer => factual, theme => exploratory, reference => reference.
  This is NOT automatic intent recognition or end-to-end NLP acceptance. Identity
  and supplied hard-plan cases remain separate shared local paths.
- Predeclare policy v1: theme cosine >=.42 alone, or >=.28 with lexical
  coverage >=.12; factual cosine >=.32 with substantive coverage >=.30 and
  every substantive clause covered >=.25, or strong literal coverage >=.70;
  reference cosine >=.45. Exact identities use a separate literal path.
  Weak lexical-only matches never qualify merely through RRF rank. These fixed
  starting values are diagnostic hypotheses, not independently calibrated limits.

BM25 background: [Stanford IR book](https://nlp.stanford.edu/IR-book/html/htmledition/okapi-bm25-a-non-binary-model-1.html).
Fusion background: [Elastic RRF documentation](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/reciprocal-rank-fusion).

## Experiment

Four stages, each reporting keyword/dense/hybrid where applicable:

1. Original .35 gate / shared-term-count baseline, reproduced from saved vectors.
2. Bounded candidate recall only; display still requires the old .35 or lexical
   evidence. Exposes how many correct neighbors were hidden before admission.
3. Add BM25 lexical ordering; keep legacy display admission for isolation.
4. Add independent admission; report reason codes and rejected candidates.

Report candidate Recall@5/10/20 and union recall separately from displayed
Recall@3, Top-1 and graded nDCG@10 over the 14 answerable cases. Two no-answer
cases get their own false-positive count; answerable false abstentions are also
separate. Do not mix abstention into ranking metrics. Include category/language
subgroups, raw cosine/lexical evidence, all IDs, local timing and artifact hashes.
No post-observation threshold/label/input tuning in this version. No new semantic
independent-test claim without separately authorized new embeddings.

## Diagnostic v1 finding and structural v2 revision

The untouched first report is `docs/evaluations/public-retrieval-ablation-v1.json`,
with its implementation at commit `602c4f2`. Candidate recall improved, but the
first gate rejected all 14 keyword answers and four hybrid answers. Its fixed
coverage fractions treated paraphrases as if most words must repeat literally.
That policy is rejected, not presented as an improvement or hidden from results.

V2 is a revision informed by this KNOWN diagnostic set, not an independent test.
The original .42/.28/.32/.45 cosine thresholds are unchanged. Broad themes allow
a substantive lexical anchor with >=.28 cosine; this makes no full-conjunction
claim. A lexical anchor bundle requires at least two substantive features and
BM25 >=3. Factual bundles also require >=.25 weighted coverage in the entire
request and every substantive split clause. Theme/reference literal bundles
require >=.12 coverage. The old >=.70 literal path remains. Generic or character
overlap alone cannot form a bundle. Explicit SQL hard filters stay independent.
No parameter sweep, per-title rule, data/qrel change or extra embedding occurs.
V2 is archived separately, including the v1 report hash and both code hashes.

## Verification

- [x] Pure-rule tests: BM25/IDF, CJK, short exact names, generic-only evidence,
  strict clause coverage, reference exclusion, bounded recall, hard IDs and guards.
- [x] Frozen inputs/history/receipts unchanged; saved-vector-only full ablation.
- [ ] Targeted and full backend checks; final exact-head CI and independent review.
- [x] Publish comparison and limitations separately from historical results.

## Measured v2 diagnostic result

Reports (all per-case IDs, raw scores, evidence, reasons and subgroups retained):

- `docs/evaluations/public-retrieval-ablation-v1.json`, rejected first admission
  attempt; SHA256 `0019616b7fada1b394f05fca52bc516a0005dd6f396c0a74cd0c57ed2fb6beb7`.
- `docs/evaluations/public-retrieval-ablation-v2.json`, structural revision;
  SHA256 `87b4c1cf5c9afd39280be558024c0034b39cfcefa1daea07bf5dcf69c9310801`.
- V2 experiment fingerprint
  `13c4a5cc98be1290450acf26fb54b6710394012df0796a60a800877405c7b6a7`.
  Both reports identify exact implementation hashes. V1 source is at `602c4f2`;
  the old public freeze and 72 historical ranked lists reproduce unchanged.

For hybrid retrieval, the four stages in v2 are:

| Stage | Candidate R@5 /10 /20 | Display Top-1 /14 | Display R@3 | nDCG@10 | No-answer FP /2 | Wrong abstention /14 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Historical .35 + overlap | 73.81 /79.76 /82.14% | 11/14 | 69.64% | .77823 | 1 | 1 |
| Wide candidates | 86.31 /94.05 /100% | 12/14 | 73.21% | .80312 | 1 | 1 |
| Add BM25 | 78.57 /92.26 /100% | 14/14 | 72.62% | .90630 | 2 | 0 |
| Add independent admission | 78.57 /92.26 /100% | 13/14 | 61.90% | .75055 | 0 | 1 |

All ranking/candidate columns average only the **14 answerable** cases. Empty
answers receive zero there; the two no-answer cases are never included in those
means. Candidate K is a prefix of the fused candidate order, before admission,
not a new display threshold. Per-modality K=20 bounds the union (plus <=20 exact
identities), rather than admitting an entire library. A 24-film corpus makes
high R@20 easier; this does not establish recall at real-library scale.

The wide stage also changes RRF ordering by exposing previously truncated dense
ranks. Consequently its displayed ordering can change even while the legacy
display predicate remains. The lexical stage still allows weak overlaps for
isolation: its 14/14 first-hit result hides two false positives and is not the
recommended display policy. Final admission is a tradeoff: Top-1/abstention
improve here, but R@3 and nDCG regress. No claim that all quality measures improve.

Final admission, across methods:

| Method | Top-1 /14 | R@3 | nDCG@10 | Candidate R@20 | No-answer FP /2 | Wrong abstention /14 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Keyword | 11/14 | 58.33% | .65089 | 94.64% | 0 | 3 |
| Dense | 13/14 | 61.90% | .74389 | 97.62% | 0 | 1 |
| Hybrid | 13/14 | 61.90% | .75055 | 100% | 0 | 1 |

All six concrete plot cases retain the correct first result. The eight
provisional theme/reference cases have hybrid Top-1 7/8, R@3 33.33%, nDCG .56347.
Hard violations remain zero relative to supplied eligible IDs. The four shared
hard-only cases still use injected plans and the unchanged SQL executor, not
new natural-language extraction. Existing tests execute that SQL on isolated
public projections; no private library is opened.

Examples, with unchanged judgments:

- Technology/companionship/memory: After Yang's .326 cosine is retained and
  admitted using its substantive memory anchor. Aftersun's .247 does not pass.
- Everyday work/routines: Perfect Days is first; the weak `daily` overlap alone
  no longer admits The Florida Project. The keyword-only mode abstains here.
- The Jupiter-courtroom and Arctic-submarine cases both abstain, without deciding
  solely from rank gaps. Generic `电影` cannot supply substantive evidence.
- Romantic longing still returns no admitted result. In the Mood for Love is a
  plausible candidate at .255, but lacks substantive lexical support under this
  policy. The known miss remains visible; no threshold sweep was used to erase it.
- Reference Ikiru -> Living and In the Mood for Love -> Chungking Express retain
  the first relevant neighbor. Other high-cosine reference neighbors include
  weaker/unrelated films (e.g. Shoplifters or A Ghost Story), so separate reference
  thresholds do not establish sufficient similarity precision by themselves.

Timing: in this replay, final hybrid local median/P95 4.385/6.206 ms, index build
15.755 ms. Historical replay median/P95 28.967/29.829 ms includes SQLite snapshot
and cache validation; the new pure function omits those operations. These are
different local scopes and **not a demonstrated end-to-end speedup**. Saved query
vectors remove provider latency entirely; no new remote latency was measured.

## Reproduction and verification evidence

From `backend/` with the existing locked dependencies:

```bash
uv run --offline --no-sync python -X utf8 -m unittest test_retrieval_policy test_retrieval_ablation test_public_movies test_openrouter_embeddings test_semantic_search -q
uv run --offline --no-sync python -X utf8 -m app.evaluation.retrieval_ablation
```

The second command prints a fresh **offline** replay; it never rewrites either
archived report or calls a model. It requires the existing owned
`.mcp-artifacts/openrouter-public-movies-v1/vectors.json` (SHA256
`e389c28c39f965d44ad403515f263488eaa3b18283601c24bab4a1758abd8b0d`).
Missing/mismatched vectors stop, with no automatic inference or credential lookup.
Timing and experiment hashes may differ across byte/line-ending environments;
all ranks/metric values should agree. Original vectors are not recommitted.

- 89 targeted offline tests passed in 58.294s (22 new rule/report tests plus 67
  historical provider/core/public regressions). Handwritten unit vectors test
  contracts only; the recorded ablation uses the 38 real saved vectors.
- Both actual ablations ran with HTTP/socket entry points blocked. New model,
  Decision, reranker and accounting calls: zero. Seven historical input/result/
  receipt hashes matched before/after each replay.
- First complete local backend at `2a3ba44`: 556 tests in 295.667s, 3 Windows
  skips, using a byte-verified isolated tracked-source snapshot with blank keys.
  Same-head CI backend: 556 tests, 1 Linux skip, compile and all 15 tooling tests.
- A subsequent reproducibility fix sorts IDF coverage terms before arithmetic.
  Three process hash seeds produce identical evidence; all 192 diagnostic
  per-stage/method ranked lists and ranking metrics match the archived v2 exactly.
  Archived v2 source remains commit `2a3ba44`; neither report was rewritten.
- Final exact-head CI and parent-coordinated independent review remain pending.

## CI dependency prerequisite

Initial CI `39883010509` on `2a3ba44` stopped its frontend job at `npm audit`:
the existing Next 16.3.8 became covered by newly published advisories
[SVG/image RCE](https://github.com/advisories/GHSA-2464-fhr4-w9xw),
[Server Actions DoS](https://github.com/advisories/GHSA-p3m5-59mp-jv5r) and
[cache/typed-array RCE](https://github.com/advisories/GHSA-673q-mjm6-r5xr).
The published patched 16.x minimum is 16.4.1; the audit-recommended 16.4.2 is
compatible with the existing Node 22 / React 19.2.3 versions.

A separate minimal dependency commit pins Next and eslint-config-next to
16.4.2, updates the same version-scoped existing tinyglobby override, and
regenerates the npm lock. No UI/routing source, React version, audit threshold or
CI bypass changes. Full frontend checks/E2E must pass on the resulting exact
head; the old failed run cannot satisfy the gate. No deployment is included.

## Remaining risks

Provisional theme judgments, tiny known corpus, lexical synonym gaps and
unvalidated admission constants. No production semantic activation or quality
acceptance. A future unseen public-fact test requires frozen new questions and
separate permission before new query embeddings; rules alone cannot prove its
semantic quality. Old Qwen unknown charge / USD .01 hold remains untouched.
