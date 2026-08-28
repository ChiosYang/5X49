# Fresh Canonical Stabilization Quality Summary

- Gate: local strict stabilization
- Status: **Passed**
- Report contract: `fresh-canonical-stabilization-report.v1`
- Evidence run: `local-gate-20260828-05`
- Source commit prefix: `24fa1892`
- Fixture digest prefix: `cadf648a28df`

## Evidence

| Area | Result |
| --- | --- |
| Isolated database and active-database immutability | Passed |
| Fresh startup, reference data and repeat startup | Passed |
| Generated media, scan and repeat reconcile equality | Passed |
| Multi-edition, directory/file relink and missing/restore identity | Passed |
| Projection verify, rebuild digest and stale rejection | Passed |
| Profile state, Viewing and Watch History semantics | Passed |
| Recorded metadata/analysis transports and safe failure states | Passed |
| Workflow retry/cancel, snapshots and dangerous clear | Passed |
| Privacy and path-boundary scans | Passed |
| English/Chinese desktop and 375px browser matrix | Passed |
| Frontend unit/lint/typecheck/build | Passed |
| Backend regression and compile checks | Passed |

All expected/actual lifecycle and projection counts matched. The backend
regression suite completed in 90.5 seconds; the final isolated rehearsal
completed in approximately six minutes before browser inspection and
conclusion.

Docker was not available and live external smoke was not run. Both are reported
separately and do not weaken the deterministic local Gate. Gate B remains
blocked, so inferred Graph publication remains disabled.
