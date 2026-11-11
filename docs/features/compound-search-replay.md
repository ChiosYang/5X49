# Compound search: reference focus and named exclusions

Status: Done (implementation and offline regression)
Baseline: main `8e92ec5`; 2026-11-11

## Behavior

In the evaluation search path, a named comparison aspect directly before the
reference cue can be separated from complete EN/ZH metadata conditions. Rerank
receives that aspect, the reference Film remains excluded, and a runtime such
as “不到两小时” is strictly less than 120 minutes. A bare person name or an
excluded title ending in an aspect word must not be truncated.

For plot searches, a complete negative title clause can follow “but”. A shared
exclusion of a title and anything released before/after Y keeps the inclusive
opposite year bound. An ordinary positive year clause retains its polarity.
Unknown mandatory clauses still cannot be dropped. No model, score threshold,
provider activation, API shape or production semantic setting changes.

## Offline evidence

The 60 previously seen public questions were replayed on separate disposable
baseline and changed-code runs. The archived fixture's old library projection
was rejected by today's reader. Both runs therefore seeded fresh projections
from the same hash-verified 64-Film public corpus using `seed_projection_database`.
The existing `search_seen_replay.replay` used copies of the original execution
report, receipts and index; only exact recorded bodies and cached vectors were
reused. Network access was blocked in the runner. No independent labels were
used. Missing evidence here refers to this original recording set.

| Observation | Baseline | Changed code |
| --- | ---: | ---: |
| Local-only / all attempted model stages recorded / missing a recording | 24 / 20 / 16 | 21 / 20 / 19 |
| Parser clarification / identity clarification | 12 / 4 | 9 / 4 |
| Questions displaying at least one Film | 20 | 20 |
| New provider requests | 0 | 0 |

Three exclusions previously stopped at parsing. They now reach Decision;
the matching request bodies were not in the original recordings, so their
ranking quality is unknown. Eight fully recorded queries each had 20 native
rerank scores below the existing factual threshold. This identifies where
their results disappeared; it does not establish which Films should be shown.
No production quality verdict or new blind result follows from this replay.

## Verification

Generic synthetic failures reproduced the lost focus, a comparison aspect
mistaken for a person, and rejected negative title/year clauses before the fix.
Regression checks exercise the integrated rerank call, original Film
exclusion, adjacent unknown constraints and SQL membership at the cutoff year.
The 11 affected unittest modules passed all 158 tests on Windows. All 60
ordered display-ID lists were identical before/after. The next calibration
step needs reviewed relevance labels, including negative examples, and a
separate unseen validation set; a lower threshold alone is not evidence.
