# Structured Metadata W3 quality summary

- Evidence date: 2026-08-25
- Report schema: 1
- Migration target: schema/data version 7
- Vocabulary: `structured-metadata-vocab:v1`
- Vocabulary hash prefix: `d3c5e1e0d2e9403a`
- Recorded fixture: `tmdb-movie-response:v1`
- Source fingerprint prefix: `978d1a20ee62b4ac`
- W3 conclusion: **Passed**
- Canonical Migration Gate A: **Blocked**

This is the Git-safe handoff. The raw report, verified backup, working database,
logs, exact counts, media paths, titles, and full identifiers remain in the
Git-ignored `backend/data/structured-metadata/` review area.

| Check group | Result | Stored evidence |
| --- | --- | --- |
| Upgrade to v7 and deterministic Legacy backfill | Passed | Version equality and count equality only |
| Alias/title, Graph type, identity and FK consistency | Passed | Zero-issue equality only |
| Credit semantic keys and provenance | Passed | Recomputed equality only |
| ISO country and unresolved-value review accounting | Passed | Zero missing/invalid equality only |
| Second NFO reconcile and recorded TMDB refresh | Passed | Entity/provenance/review count equality only |
| Curated/NFO/TMDB/Legacy source priority | Passed | Boolean precedence and provenance preservation |
| Ordinary clear and deep clear lifecycle | Passed | Count equality and journal-preserved booleans |
| Report, review, Event, Job and console privacy scan | Passed | Zero canary and full-ID leaks |
| Source database and media boundary | Passed | Hash, size, sidecar and read-only equality only |

The W3 rehearsal is intentionally separate from Gate A. It proves the
structured metadata migration and runtime contracts on an isolated offline
copy, but it does not supply the naturally aged private-library evidence or
Docker upgrade/read-source/restore/browser matrix required to pass Gate A.
It therefore does not authorize Graph UI or replace W4 Assertion design.

The final backend regression discovered every `test_*.py` module except the
credential-dependent `test_agent.py`; the post-v9 regression passed all 176
tests. W3 rehearsal `w4-s2-v9-20260825-01` also passed after confirming migration
v7 remained applied while its isolated work copy reached current schema v9 and
the downstream factual Genre Assertion migration remained idempotent.
The focused W3, migration, metadata, TMDB concurrency, and rehearsal runs
passed, and Python bytecode compilation completed successfully.

The post-v10 regression `w4-s3-v10-20260825-01` again passed every W3 check
after upgrading only its isolated work copy. Legacy backfill, NFO reconcile,
recorded TMDB refresh, lifecycle, provenance, privacy, and source immutability
remained green. W3 remains complete; v10 Analysis transition data does not
change its v7 contract boundary.
