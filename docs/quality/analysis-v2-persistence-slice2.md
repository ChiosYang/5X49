# Analysis V2 Persistence Slice 2 quality summary

- Evidence date: 2026-08-25
- Current migration target: schema/data v9
- Predicate vocabulary: `assertion-predicate.v1`
- Genre vocabulary: `tmdb-movie-genres:v1`
- Import policy: `structured-genre-import.v1`
- Source fingerprint prefix: `978d1a20ee62b4ac`
- Slice 2 conclusion: **Complete**
- Gate B conclusion: **Pending**

This Git-safe summary stores only check results, equality statements, versioned
contract names, and a truncated source fingerprint. Raw databases, media paths,
movie titles, source Genre values, exact domain counts, and full identifiers
remain in ignored rehearsal directories or ephemeral test fixtures.

| Check group | Result | Stored evidence |
| --- | --- | --- |
| v8 to v9 upgrade and verified backup | Passed | Version and preservation equality only |
| Legacy Genre deterministic backfill | Passed | Resolved/review accounting equality only |
| Shared Assertion identity across sources | Passed | Deduplication and key equality only |
| Legacy/NFO/TMDB provenance mapping | Passed | Origin class and active-state equality only |
| Source-local removal, supersede, and restore | Passed | Lifecycle booleans only |
| Import-policy acceptance | Passed | Policy/version equality only |
| User accepted/rejected preservation | Passed | Review-field equality only |
| Unknown, unsupported, and conflicting input | Passed | One-review/no-Assertion booleans only |
| Event/Legacy/W3/W4 transaction rollback | Passed | Pre/post count and field equality only |
| Ordinary and destructive clear lifecycle | Passed | Preservation/empty/reference-row booleans only |
| HTTP and Legacy compatibility | Passed | Existing contract regression only |
| W3 and Gate A local regression | Passed locally | Source immutability and check status only |

The focused Genre Assertion, Analysis persistence, migration, Canonical,
Structured Metadata, TMDB, and Gate suite passed 82 tests. Complete backend
discovery excluding credential-dependent `test_agent.py` passed 176 tests in
110.096 seconds. Python bytecode compilation and `git diff --check` passed.

W3 rehearsal `w4-s2-v9-20260825-01` reached v9 and passed. Gate A rehearsal
with the same run ID passed every local check at v9 and left the input
fingerprint unchanged. Its strict overall status remains `Blocked` because the
Docker evidence is absent; this Slice does not alter Gate A or pass Gate B.

Analysis V2 runtime persistence, entity resolution, verified Evidence,
compatible legacy analysis transition, the adjudicated evaluation set, and the
strict Gate B matrix remain Slices 3–4.
