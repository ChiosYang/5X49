# Factual Explore engineering quality summary

- Contract: `factual-explore-evaluation.v1`
- Run ID: `w7-engineering-20260901-01`
- Commit: `d6d594208210`
- Fixture seed: `549`
- Behavior fixture size: `200`
- Scale fixture size: `1000`
- Fixture contract hash: `160eab92dc5bbe91`
- Result: **Passed**
- Evidence class: deterministic engineering fixture; not real-library or Alpha-user evidence

| Dimension | Total | Covered | Conflicted | Missing |
| --- | ---: | ---: | ---: | ---: |
| Genre | 200 | 190 | 0 | 10 |
| Person | 200 | 190 | 0 | 10 |
| Country | 200 | 180 | 10 | 10 |
| Decade | 200 | 190 | 0 | 10 |

| Engineering check | Result |
| --- | --- |
| `behavior-four-dimensions` | Passed |
| `behavior-genre-coverage-partition` | Passed |
| `behavior-genre-expected-coverage` | Passed |
| `behavior-person-coverage-partition` | Passed |
| `behavior-person-expected-coverage` | Passed |
| `behavior-country-coverage-partition` | Passed |
| `behavior-country-expected-coverage` | Passed |
| `behavior-decade-coverage-partition` | Passed |
| `behavior-decade-expected-coverage` | Passed |
| `behavior-strict-four-dimension-and` | Passed |
| `behavior-strict-context-matches-films` | Passed |
| `behavior-same-dimension-or` | Passed |
| `behavior-unresolved-filter-fails-closed` | Passed |
| `behavior-conflicted-filter-fails-closed` | Passed |
| `behavior-viewing-and` | Passed |
| `behavior-result-reasons-cover-four-dimensions` | Passed |
| `behavior-context-statement-bound` | Passed |
| `behavior-first-page-bounded` | Passed |
| `behavior-context-total` | Passed |
| `behavior-projection-rebuild-stable` | Passed |
| `behavior-public-payload-private-free` | Passed |
| `behavior-projection-row-count` | Passed |
| `scale-four-dimensions` | Passed |
| `scale-genre-coverage-partition` | Passed |
| `scale-genre-expected-coverage` | Passed |
| `scale-person-coverage-partition` | Passed |
| `scale-person-expected-coverage` | Passed |
| `scale-country-coverage-partition` | Passed |
| `scale-country-expected-coverage` | Passed |
| `scale-decade-coverage-partition` | Passed |
| `scale-decade-expected-coverage` | Passed |
| `scale-strict-four-dimension-and` | Passed |
| `scale-strict-context-matches-films` | Passed |
| `scale-same-dimension-or` | Passed |
| `scale-unresolved-filter-fails-closed` | Passed |
| `scale-conflicted-filter-fails-closed` | Passed |
| `scale-viewing-and` | Passed |
| `scale-result-reasons-cover-four-dimensions` | Passed |
| `scale-context-statement-bound` | Passed |
| `scale-first-page-bounded` | Passed |
| `scale-context-total` | Passed |
| `scale-projection-state-verified` | Passed |
| `scale-public-payload-private-free` | Passed |
| `scale-projection-row-count` | Passed |

## Scale observations

- Context SQL statements: `9` (hard maximum: `10`).
- Overview duration: `65.323` ms.
- Context duration: `96.027` ms.
- Film query duration: `13.746` ms.
- Durations are informational and are not cross-machine release gates.

## Product evidence still required

- Representative real-library coverage and correctness sampling.
- External Alpha comprehension and task-completion evidence.
- Repeat-use and retention evidence in the W10/W13-W14 product gates.
