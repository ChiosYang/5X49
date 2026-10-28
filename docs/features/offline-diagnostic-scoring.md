# Offline diagnostic scoring

Status: In Progress
Last updated: 2026-10-28
Related: diagnostic v3 draft scoring contract

## Goal and scope

Score an explicitly supplied diagnostic package and result file with no search,
database, application startup, provider or network dependency. Package validation,
source-byte freezing, pending-review registration and simulated self-tests are
separate from running search. No production quality verdict is issued.

Only generic tooling, documentation and wholly synthetic fixtures belong in this
repository. Keep downloaded question packages, labels, review overlays and actual
result reports outside the checkout. Never feed judging/evidence files into an
index or executor. The examples below use generated toy IDs, not a real corpus.

## Supported contract

`5x49-diagnostic-v3.0-draft`: 24 candidates and 24 questions, with three categories
of eight questions. Each category contains five ranked-answerable, two
constraint-driven empty controls and one clarification question. There are 576
question/candidate judgments. Other versions or metric/gain contracts fail closed.

The loader accepts the supplied ZIP or its exact extracted directory. It checks
safe archive members, duplicate paths/JSON keys/IDs, sizes, manifest lengths and
SHA-256 hashes, document-text hashes, question JSON/JSONL equivalence, exhaustive
judgments, category populations, grade/range consistency, reference identities,
and machine-checkable empty-control filters. Unexpected judging fields in index
records or expected-answer fields in execution questions are rejected. URLs in
evidence remain inert text; sources are not fetched or independently adjudicated.

`freeze` records original member hashes, scorer source hashes, the ZIP hash when supplied, and a versioned
review register without changing package bytes. Intervals remain review guides,
never per-system selectable runtime gains. Non-constraint proposed labels remain
`needs_human_review`; clarification labels stay ungraded until clarified. Machine
constraint checks do not imply a human relevance sign-off. A future amendment needs
a new package version/hash and an explicit change reason, not in-place relabeling.

## Commands

Run from `backend/` using the project's existing Python/uv environment:

```sh
uv run python -m app.evaluation.diagnostic validate-package --package /private/input.zip
uv run python -m app.evaluation.diagnostic freeze --package /private/input.zip --output /private/run-v1/freeze.json
uv run python -m app.evaluation.diagnostic template --package /private/input.zip --output /private/run-v1/results.json
uv run python -m app.evaluation.diagnostic score --package /private/input.zip --results /private/run-v1/results.json --output /private/run-v1/report.json --summary /private/run-v1/summary.txt
```

Use quoted absolute Windows paths when applicable. Outputs must be new paths and
cannot overwrite inputs or live inside the supplied extracted package. Neither
the original package nor its input/index text is rewritten by any command.

The bound result template adds `manifest_sha256`. Preserve it and `version`.
Choose top-level `status` explicitly: `TEMPLATE_NOT_RESULTS` (unexecuted),
`SIMULATED_RESULTS`, or `ACTUAL_RESULTS`. An all-unexecuted template is reported as
unexecuted, not a successful all-empty search. This CLI never fills actual runs.

Each run requires `query_id`, `run_status` (`ok`, `error`, `not_run` or template
null), `observed_behavior` (`ranked`, `empty`, `clarify` or unexecuted null),
`fused_ids`, `displayed_ids`, and `clarification_text`. Supply a manual
`human_clarification_score` (0/1/2) and nonempty `human_review_note` for valid
clarification responses; `human_reviewer` is optional provenance. The tool does
not judge clarification semantics with keyword matching. Structural failures
(guessing a film, returning an empty answer or an empty clarification question)
receive zero; otherwise missing human review is pending, not zero.

Optional telemetry uses the same ordered ID arrays: `lexical_ids`, `semantic_ids`,
`filtered_ids`, `reranked_ids`. `scores` maps a stage-array field to an equally long
finite numeric list; booleans/NaN/infinity are invalid. `stage_status` maps these
field names to `ok`/`error`/`not_run`; required fused/display stages marked unsuccessful
cannot contribute a complete valid aggregate. `latency_ms` contains nonnegative
finite numbers. `parsed_constraints`, `filter_reasons` (`film_id`, `reason`) and
`error` retain explanatory evidence, without executing any expressions.

Exit codes: 0 = command completed / complete diagnostic records, 1 = valid report
but incomplete/invalid run set, 2 = malformed, unsupported or unbound input / I/O
error. Exit 0 is **not** a search-quality pass. Draft labels and uncalibrated
thresholds keep `official_aggregate_valid=false` and `acceptance=not_assessed`.

## Metrics and invalid output

Only the 15 ranked questions contribute ranking macros. Relevant means grade≥2;
gains are 0, 0, 3, 7 for grades 0–3. Recall@20 uses the first 20 **fused** positions.
Precision@5 always divides by five; ceiling-normalized precision divides by
`min(5, relevant_count)`. nDCG@5 discounts by `log2(position+1)` and uses the ideal
ranking across the entire candidate pool. Same-grade ties are unrestricted.
Missing displayed slots contribute zero. Report hit, false-empty, unnecessary
clarification and named-hard-negative exposure counts with their denominators.

The six conditional-empty controls separately report false positives and correct
empty behavior. An empty clarification is not a correct empty response. Runtime
errors and missing runs contribute neither correct empties nor zero-relevance
judgments. The three clarification cases report each supplied/structural score,
pending support and total/6. Contract-invalid rows retain a per-case preview but
do not enter valid clarification support or partial totals; a complete total
requires a contract-valid run set. No empty-set recall/nDCG=1 substitution is made.

Known ineligible films and excluded references retain their original display
positions with zero gain. Known duplicates likewise occupy their original slots,
receive no second gain and invalidate that case for aggregation. Unknown IDs are
unscored, not imputed zero. Contract errors, missing records or unresolved ranked
null labels leave complete macros null; explicitly partial macros show measured
support and per-case previews remain available. No IDs are silently removed and
no ranking is compacted.

Per-stage recall and support describe only logged successful stages. Set losses
are observations, not automatic claims about a model, metadata or intent parser.
Missing stage logs remain unavailable. No-answer controls test hard conditions,
not general semantic refusal; this small public diagnostic set is not a holdout.

## Fully synthetic self-test

```sh
uv run python -m unittest test_diagnostic_scoring -q
uv run python -m app.evaluation.diagnostic_synthetic --output /private/toy-v1
uv run python -m app.evaluation.diagnostic score --package /private/toy-v1/package --results /private/toy-v1/ideal-results.json --output /private/toy-v1/ideal-report.json --summary /private/toy-v1/ideal-summary.txt
uv run python -m app.evaluation.diagnostic score --package /private/toy-v1/package --results /private/toy-v1/faulty-results.json --output /private/toy-v1/faulty-report.json --summary /private/toy-v1/faulty-summary.txt
```

All generated reports prominently identify simulation. Tests use fixed hand
calculations and check wrong order, missing/wrong/duplicate/reference candidates,
short lists, independent denominators, empty/error/clarification behavior, null
judgments, unsafe/unbound inputs, finite scores, reproducibility and immutability.
A subprocess guard verifies the CLI makes no network/subprocess calls and imports
no database, search or provider client. These checks establish scorer behavior,
not actual retrieval quality.

## Verification and remaining work

- Targeted synthetic unittest suite: 42 tests passed locally (including two
  contract-invalid clarification subcases).
- Additional RC tooling suite: 15 discovered; 12 passed, one platform skip,
  two Compose checks could not execute because this Windows environment has no
  `docker` executable. This is an environment limitation, not a waived CI check.
- The supplied local draft package was independently revalidated by the loader;
  only a bound **unexecuted** template was scored. No actual search ran.
- Public PR contains generic code and toy data only; independent review and CI
  follow the repository delivery workflow.
- Human relevance adjudication, historical query deduplication and real search
  evaluation remain outside this implementation's completed checks.
