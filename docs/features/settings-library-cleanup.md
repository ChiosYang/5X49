# Library settings cleanup

Status: In Progress
Last updated: 2026-10-20
Related: PR #34 menu cleanup (merged before this branch)

## Goal

Apply the user's 16 Library settings simplifications in English and Chinese,
while keeping explicit directory saves, existing automation behavior and deletion safeguards.

## Decisions and acceptance

| Requests | UI decision | Behavior retained |
| --- | --- | --- |
| 1–3 | Remove Library Source heading, its introduction, directory configuration/help paragraphs and legacy-first-directory suffix. | Media directories heading and numbered input labels. |
| 4–6 | Put each directory's status icon and remove icon inside the input's right edge. Remove Browse and the text Remove button. | Localized status names, hover/focus tooltips, keyboard access, draft removal and Use as first. |
| 7–8 | Use Add / Save (添加 / 保存); remove removal and container-path explanatory paragraphs. | Explicit Save, Discard, maximum/blank-path guards, server validation and scan controls. |
| 9–10 | Remove artwork explanation and Advanced description/state summary. | Artwork autosave, advanced controls, their risk/behavior explanations and system-status link. |
| 11–14 | Remove health introduction, window/budget fields and Save Schedule. Use the existing ToggleSwitch with the control at the right. | Automatic enabled state saves immediately; failed writes show an alert and retain the confirmed state. Existing backend schedule/defaults/APIs are unchanged. |
| 15 | Remove health runtime reason, minutes, counts, progress/load/limits paragraphs from Settings. | Queue, pause/resume, cancel, read/write errors, loading, accepted-request feedback and link to detailed maintenance results. |
| 16 | Remove only the danger-zone introduction. | Clear action description, impact, typed phrase, confirmation, active-workflow and unavailable-workflow blocks. |

Directory edits never autosave. Health switch requests send only `enabled`;
they do not submit hidden start/end/budget values. The old schedule E2E now
configures those values through the existing API and still checks queue,
pause/resume, decoder results and restart persistence.

## Verification evidence

- `npm run test:unit`: 94 passed.
- `npm run lint`: passed.
- `npm run typecheck`: passed.
- `node e2e/run-settings.local.mjs settings-library.spec.ts zy-video-health.spec.ts zz-media-roots.spec.ts`: 21 passed in real Chrome, including 12 new bilingual settings checks and 9 existing directory/video-health checks.
- Production webpack build passed in that isolated runner. The local runner only selects webpack for the existing Windows Turbopack IPC limitation; it is not committed. Full CI retains the normal build command.
- Screenshots reviewed at 1440, 390 and 320px; actual Chrome keyboard inspection confirmed the focused status tooltip is visible. New CSS required clearing stale local generated webpack cache before the final successful run.
- English desktop: `libfile_701ee877b6948191bfbfa2b2ee7878e8`.
- Chinese mobile: `libfile_32d94c064ae08191b1d6572354b9d77a`.
- Failed health write with unchanged switch: `libfile_981767c415d88191a79932b7c2e5c853`.
- English 320px after the narrow-button fix: `libfile_4f33ab801f088191a11634eefd49628e`.
- Independent review and final-head CI: pending.

The first full CI run (`39365727754`) passed Frontend and Backend, with 133 E2E
passes and one English 320px layout failure. Its trace confirms that the scroll-width
assertion ran while the clear-data dialog was still exiting (320×1000 viewport,
overlay `translateY(0.458928px) scale(0.998758)`). The old screenshot also exposed
a long health action extending into the content's right margin. Health buttons
now have a maximum width of their content container. The test waits for fonts
and actual dialog removal, retains the strict document-width assertion and adds
per-button bounds checks. After this fix, lint, typecheck, the production webpack
build and all 16 settings/video-health E2E checks passed locally. A new exact-head
review and full CI run are required.

All local acceptance writes use the existing isolated harness with generated
media and a temporary SQLite database. No real user settings, media or provider
calls are involved.

## Remaining risks

Independent review and final-head CI are required before merge. No remaining local acceptance failures.
