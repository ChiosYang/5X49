# Analysis V2 and Evaluation Contract

Status: Adopted contract; persistence schema is implemented in version 8,
factual Genre Assertions in version 9, and Analysis V2 runtime plus compatible
Legacy transition in version 10. Evaluation and Gate B remain W4 work.

The executable schemas live in `backend/app/contracts/analysis_v2.py`. Runtime
producers and evaluation tooling must validate against those Pydantic models;
this document explains the product and privacy decisions behind them.

## Analysis input and output

- `AnalysisV2Input` contains only canonical Film metadata. Local paths, media
  filenames, API keys, user reviews, Viewing history, and raw NFO content are
  outside the contract.
- `AnalysisV2Output` is strict: unknown fields are rejected, including hidden
  reasoning fields. It retains a concise user-facing summary and rationale.
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

## Persistence boundary

Schema version 8 implements the durable boundary without connecting model
generation. The persisted `assertion-predicate.v1` registry contains the eight
model predicates plus factual `HAS_GENRE`; the model schema remains unchanged
and cannot output `HAS_GENRE`. Assertion identity is the canonical hash of
subject, predicate, object, and qualifier hash. Run, scope, provenance, and
review state are intentionally excluded.

An automated model result may only create an inferred, proposed Assertion.
Accepted and rejected decisions survive refresh and re-analysis. A Genre that
the fixed W3 vocabulary resolves uniquely from NFO, TMDB, or Legacy metadata
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
items. The synchronous title-only `/analyze/{movie_name}` compatibility route
is not a persistence producer and remains on its existing response contract.
