# Video health

Status: In Progress
Last updated: 2026-10-14
Related: user-authorized video integrity checks

## Goal and contract

Automatically check stable new/changed local videos and gradually backfill the
existing library. A successful ffprobe container read is never a full decode pass.
Each video and multipart asset has its own stat-based version and result. A deep
pass requires continuous software decoding of every audio/video stream to EOF.
It cannot guarantee audiovisual synchronization, intentional content completeness,
or detect every possible valid-looking truncation. No media writes occur.

## Decisions

- One durable queue and one OS-locked worker per database; one decoder, one codec
  thread, low process priority. Tools are restricted to local container protocols.
- Compare device/inode, size, mtime_ns, ctime_ns and locator identity before/during/
  after inspection. This is a filesystem observation, not a cryptographic hash.
  Scan metadata changes invalidate old results even before the next idle sample.
- Observe a small batch only inside an idle/allowed/budget window. Never walk
  disks to discover health work; use existing MediaAsset records. Newly observed
  records precede a persistent cursor through older assets.
- Sustained idle and high/low thresholds avoid start/stop flapping. Application
  jobs yield foreground priority. CPU/disk observations describe only the backend
  host's available counters; they reveal neither all NAS clients nor disk sleep.
  Missing observations require a narrow user-configured allowed window.
- Schedule times are explicitly UTC. Daily decoder budget limits new starts;
  one file already started may exceed it so long videos can finish. Outside an
  allowed window, under load, or on user pause, suspend the owned decoder process
  and retain continuous progress. If suspension is unsupported, terminate and
  mark incomplete. Cancel terminates and never reports corruption.
- Decoder state cannot be serialized across restarts. Interrupted work becomes
  incomplete with explicit retry; queued work survives. Never resume by seeking
  and claim a continuous full pass. No automatic endless restart retry loop.
- Offline/access errors use bounded exponential backoff. Unsupported tools and
  codecs, cancellations, changing files and unknown failures are distinct from
  abnormal media. Error locations are unknown; decoded progress is not presented
  as an exact corruption timestamp. One durable notification per abnormal version.
- Health results/queue are host-specific operational data, excluded from portable
  export and downloadable backups. Foreign-key cascade clears them on deep reset.

## Slices and acceptance

1. Durable schema, versions and safe decoder: complete.
2. Conservative scheduler and lifecycle integration: complete.
3. Settings, maintenance details and in-app notifications: complete.
4. Synthetic real decode, persistence/safety tests and UI E2E: complete locally.
5. Draft PR checks and parent-coordinated independent review: awaiting review.

## Verification evidence

- Base main verified: 73f280670018c6d6c75f7aee933650e357c74f00.
- Existing checkout clean before task branch feat/video-health.
- `uv run python -X utf8 -m unittest discover -s . -p "test_*.py" -q`:
  412 tests passed, 3 existing platform/environment skips (Windows).
  Final settings-race/health/API/root regression: 71 passed, 1 existing skip.
- `uv run python -X utf8 -m unittest test_video_health -q`: all 29 passed,
  including real 6-second MPEG-4/AAC multi-audio-track media, middle-packet
  corruption with container pass/decode failure, truncation, native pause/resume,
  active cancellation, budget overrun fairness and abrupt owner-exit reaping.
- Final targeted migration/root/backup/reset/health regression: 77 passed,
  1 existing platform skip.
- `npm run test:e2e` with canonical Windows TEMP/TMP: all 74 passed, including
  the 4 new health UI scenarios and all existing real backend acceptance.
- Production build (in E2E runner), `npm run lint`, `npm run typecheck`,
  `npm audit --audit-level=high`, `uv run python -m compileall -q app`: passed.
- Full frontend unit run: 88 passed / 3 failed on Windows in the unchanged
  `tests/eslint-root-dirs.test.mjs` / Next plugin Windows absolute glob behavior.
  Tests and frontend dependency manifests match base main byte-for-byte;
  Ubuntu PR CI will verify the complete suite. New schedule unit tests passed.
- Script suite: 15 run, 2 Compose errors because this host lacks Docker CLI,
  1 existing skip. Ubuntu CI covers Compose; no Docker configuration was changed.
- Browser pixels inspected: Chinese narrow settings and English desktop
  maintenance detail show separate container/decode states, version and unknown
  error time. Existing big page titles and background-free navigation retained.
- Every application test used a disposable SQLite DB and generated media. No
  real library reset, media repair/write or deployment was performed.
- FFmpeg flags follow [official FFmpeg documentation](https://ffmpeg.org/ffmpeg.html).

## Default scheduling parameters

- Automatic enabled; user pause off; allowed start/end 00:00/00:00 UTC (all day).
- 30-minute daily new-start budget; one active long file may exceed it while idle.
- 60-second stable observation and sustained idle; launch CPU <30%, disk busy <20%.
- Active CPU >=75% or disk busy >=65% suspends, then requires quiet recovery.
- At most one sampling tick per 30 seconds; each candidate lane is 4 files.
- Unchanged passes with unchanged scan metadata avoid another automatic stat for
  24 hours. Manual sweep/live detail can check sooner; out-of-band change evidence
  is observational, never falsely represented as a cryptographic guarantee.
- Missing host counters plus all-day permission means no blind automatic launch:
  user must narrow allowed UTC hours. This is especially relevant to Windows
  disk counters lacking busy-time data and some container environments.
- Pause retains the same process/continuous decoder; backend restart cannot:
  queued work persists and interrupted active work is incomplete, explicit retry.
- Linux parent-death signal / Windows kill-on-close Job Object prevents orphan
  decoder overlap after abrupt backend exit. Native Windows behavior was tested;
  Linux behavior is additionally exercised by Ubuntu CI with real FFmpeg.

## Remaining risks

Native Windows suspension and owner-exit reaping passed; Ubuntu CI exercises
the Linux implementation with real FFmpeg (see PR check results).
Abrupt backend death cannot preserve an in-memory decoder. Idle scheduling is conservative and
does not claim remote NAS observability. No external notifications or deployment.

Supported deployment: one backend process/worker per library database (the default
Uvicorn/container entrypoint). The OS lock prevents duplicate health decoders
across processes, but a standby worker does not automatically take over if its
owner exits, and active process/load/reason state is local to the owner. Compound
runtime-setting updates and foreground preemption are not coordinated across
multiple API workers. Multi-worker/multi-instance execution against one database
is therefore unsupported for this feature; stop the prior owner before restart.
