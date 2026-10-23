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

## Verification

- [ ] Pure-rule tests: BM25/IDF, CJK, short exact names, generic-only evidence,
  strict clause coverage, reference exclusion, bounded recall, hard IDs and guards.
- [ ] Frozen inputs/history/receipts unchanged; saved-vector-only full ablation.
- [ ] Targeted and full backend checks; final exact-head CI and independent review.
- [ ] Publish comparison and limitations separately from historical results.

## Remaining risks

Provisional theme judgments, tiny known corpus, lexical synonym gaps and
unvalidated admission constants. No production semantic activation or quality
acceptance. A future unseen public-fact test requires frozen new questions and
separate permission before new query embeddings; rules alone cannot prove its
semantic quality. Old Qwen unknown charge / USD .01 hold remains untouched.
