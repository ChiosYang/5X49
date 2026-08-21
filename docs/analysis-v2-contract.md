# Analysis V2 and Evaluation Contract

Status: Adopted contract; generation and persistence remain W4 work.

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

This contract does not make model output durable by itself. W4 must resolve
references, deduplicate by Assertion key, preserve accepted/rejected review
state, and write Evidence and provenance separately. Invalid or unresolved
output is a review item, not a reason to invent an entity.
