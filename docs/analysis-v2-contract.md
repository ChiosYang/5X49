# Analysis V2 and Evaluation Contract

Status: Adopted contract in the `fresh-canonical-v1` baseline. Persistence,
factual Genre Assertions and the Analysis V2 runtime are active; Gate B tooling
is implemented while its strict live and human evidence remain blocked.

The executable schemas live in `backend/app/contracts/analysis_v2.py`. Runtime
producers and evaluation tooling must validate against those Pydantic models;
this document explains the product and privacy decisions behind them.

## Analysis input and output

- `AnalysisV2Input` contains only canonical Film metadata. Local paths, media
  filenames, API keys, user reviews, Viewing history, and raw NFO content are
  outside the contract. It may also include a bounded, stable-sorted catalog of
  up to 80 active non-Genre Concepts with IDs and aliases so generation can
  reuse existing nodes instead of inventing near-duplicates.
- `AnalysisV2Output` is strict: unknown fields are rejected, including hidden
  reasoning fields. It retains a concise user-facing summary and rationale,
  allows at most eight Assertion candidates, and allows at most two Evidence
  candidates per Assertion.
- Every target is traceable by an internal entity ID, a provider-qualified
  external identity, or an unresolved display reference. Unresolved Film
  references require title and year and must enter resolution review; they
  cannot become formal Graph nodes directly.
- Model-produced relationships always enter as `source_scope=inferred`.
  Provider facts and user review decisions are applied outside this schema.
- Assertion candidates use `direction=subject_to_target` by default. Film
  relations may use `target_to_subject` for descendants; Concept relations are
  always subject-to-target. Direction changes the persisted subject/object and
  participates in duplicate detection.
- Evidence supplied by a model is an untrusted candidate with a bounded claim
  and HTTP(S) URI. It becomes Evidence only after retrieval and policy checks.
- Exact duplicate relationship candidates are rejected before persistence.
- Model-generated qualifiers are not materialized by the current policy. They
  enter bounded review instead; explanatory labels and periods belong in the
  rationale until a qualifier vocabulary is explicitly governed.

Contract versions are `analysis-input.v2` and `analysis-output.v2`. Prompt,
resolver, persistence policy, and app versions remain separate AnalysisRun
dimensions so changing any one can generate a new idempotency key.

## Evaluation dataset

`AnalysisEvaluationDataset` uses `analysis-eval.v1` and requires 30–50 cases.
Case IDs are synthetic and stable. The set must contain Chinese and English
cases and cover same-title identity, cold titles, non-Latin titles, and
cross-decade comparisons. Each expected assertion is labelled `required`,
`acceptable`, or `forbidden`, with annotator count and adjudication status.

Evaluation data must be curated independently of a user's library. It may use
public catalog identifiers and synthetic case IDs, but never local paths,
private notes, API credentials, or hidden model reasoning. Baseline reports
should publish relationship precision, entity-resolution accuracy, duplicate
rate, and human helpfulness separately rather than collapsing them into one
opaque score.

The fixed `analysis-eval.v1` Gate B corpus contains 36 public cases: 12 Chinese,
12 English, and 12 mixed/other. `draft` cases may have `annotator_count=0`;
`adjudicated` cases require at least one annotator, and a live Gate B run refuses
the entire corpus unless all 36 cases are adjudicated. Expected relationship
matching includes predicate, direction, provider-qualified Film identity or
Concept kind/name, and canonical qualifiers. An expected Concept may also carry
up to 20 unique, human-adjudicated `target_aliases`; those aliases exist only in
the evaluation contract, resolve to the same seeded Concept, and count as one
gold target for recall and duplicate detection. They are not added to the model
output schema. Every same-title case includes a forbidden identity trap, and
any prediction outside the frozen expected set requires a human disposition.

`analysis-eval-human-review.v1` references the run ID, dataset ID/hash, and each
novel prediction hash. It stores only a 1–5 helpfulness score and a bounded
`acceptable/incorrect/harmful` decision; reviewer names are not retained. The
review must cover every successful case and every novel prediction exactly.

`gate-b-policy.v2` retains the v1 thresholds and additionally requires zero
resolved identity/title/year contradictions, complete review capture for those
contradictions, zero model qualifier-policy violations, and no more than eight
Assertions at p95. The strict thresholds still require 36/36 completion, at least
85% acceptable displayed edges, at least 95% resolution-decision accuracy,
at least 75% required recall, zero forbidden/harmful or invented entities, zero
semantic/replay/rejected/revoked regressions, median helpfulness at least 4 with
80% of cases at least 4, at least 70% fresh qualifying Evidence coverage, and a
USD 5 total / USD 0.25 p95 per-case budget. Missing evidence blocks; evidence
present but below a safety or quality threshold fails.

The internal `app.evaluation.gate_b` CLI validates the corpus, rehearses the
runtime in an isolated Fresh Canonical v1 database, runs one explicitly pinned OpenRouter
model with a versioned pricing manifest and explicit public-network consent,
creates a bounded review template, and concludes the evidence. Exit codes are
0 passed, 2 failed, and 3 blocked. Run databases, backups, reports, and reviews
remain under the ignored `backend/data/analysis-v2/gate-b/` boundary. The tool
never reads or modifies the application database or media. A
bounded `pilot` command is available for prompt tuning; its report always keeps
strict live status blocked and cannot be used by `review-template` or Gate B
conclusion. Strict `run` also performs an Evidence-network preflight before any
model call and blocks when public DNS/pinned retrieval cannot satisfy the SSRF
boundary.

## Persistence boundary

Fresh Canonical v1 implements the durable boundary. The persisted
`assertion-predicate.v1` registry contains the eight
model predicates plus factual `HAS_GENRE`; the model schema remains unchanged
and cannot output `HAS_GENRE`. Assertion identity is the canonical hash of
subject, predicate, object, and qualifier hash. Run, scope, provenance, and
review state are intentionally excluded.

An automated model result may only create an inferred, proposed Assertion.
Accepted and rejected decisions survive refresh and re-analysis. A Genre that
the fixed vocabulary resolves uniquely from NFO or TMDB metadata
may instead be accepted under `structured-genre-import.v1`; the policy version
and factual provenance remain explicit.

Evidence v1 stores only a bounded claim and metadata for `catalog`, `web`, or
`dataset` material that was successfully retrieved over HTTP(S) and passed the
network/content policy. Candidate URLs with credentials, sensitive query
parameters, non-public literal addresses, file schemes, or unsafe redirects
cannot become Evidence. The runtime pins each request to a validated public DNS
address, revalidates every redirect, accepts only standard HTTP(S) ports and a
bounded document allowlist, and never persists response bodies. NFO is
provenance and user explanation is curated rationale, not external Evidence.

AnalysisRun stores version dimensions, canonical input/output hashes, status,
attempt count, token/cost data, trace IDs, redacted errors, and the validated
user-facing summary. No AnalysisArtifact exists: raw prompts, raw responses,
web-page bodies, hidden reasoning, paths, credentials, and whole source
documents are not persisted. Invalid, unresolved, ambiguous, or unsafe
candidates enter a bounded `AnalysisResolutionReview`; they never cause an
entity to be invented.

The Library analysis worker builds `AnalysisV2Input` exclusively from canonical
Film data. Exact existing identities resolve locally; a missing `tmdb.movie`
identity may create a non-owned Film only after the existing TMDB client
verifies it. Name/year-only and unsupported-provider references remain review
items. A supplied provider/ID is atomic: it must resolve to a Film whose known
title and release year agree with the candidate and may never silently fall
back to a same-name Film. Before Evidence retrieval or persistence, the
versioned deterministic Critic rejects identity/title/year contradictions,
entity/predicate mismatches, self-reference, ambiguous Concept aliases,
non-empty model qualifiers, semantic duplicates and candidates beyond the
eight-edge budget. Rejected candidates become bounded idempotent reviews and
cannot be ordinary Graph edges.

The current prompt/resolver/policy snapshots are `genealogy-v2.v3`,
`analysis-resolver.v3`, and `analysis-policy-critic.v1`.
Analysis is exposed only through `POST /films/{film_id}/analysis-runs` and
`GET /films/{film_id}/analysis`; there is no title-only compatibility route or
raw analysis projection.
