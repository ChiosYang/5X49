# Settings controls, directory picking and test feedback

Status: Ready for independent review
Last updated: 2026-10-21
Base: main f5471324bdee0974c1c2465e02ab31225a3a697a (PR #37)

## Scope and behavior contract

- Use the exact shared Auto Scan / Auto Organize Root toggle for language,
  following the user's 2026-10-21 clarification. Show Chinese/English labels and
  an accessible current-language name; this selects a language, not enablement.
  Reserve a left-side loading slot and remove the language success Saved message.
- The directory header plus opens the existing backend FileBrowser immediately.
  Confirming a loaded valid folder appends it in order and autosaves; cancellation
  creates no row and sends no write. Remove Use as first and Discard changes.
- Existing editable directory inputs still save completed edits. Empty blur
  abandons that field edit and restores its confirmed path; it must never delete
  a configured root implicitly. The explicit remove icon remains the deletion
  action. Retain root validation, retries, ordering, shared single-flight sessions
  and all scan guards introduced in PR #37.
- API and TMDB connection tests show right-side success/failure icons with
  accessible names/tooltips. Remove their below-row success/error prose. Results
  become invalid as soon as a relevant URL/model/key edit starts; stale responses
  cannot certify a newer configuration. Testing remains an explicit action.
- TMDB testing becomes an icon button and the key saves on blur/Enter, never per
  keystroke. Remove its Save button and success prose. Preserve source ownership,
  failed-input retry and cross-unmount serial/version protection; tests cannot run
  against an unsaved draft. Persist only metadata to SWR, never key text.

## Reference and evidence

The original PNG reference was Library ID
`libfile_32a730f9e60c8191aebc793691491441`. Native preparation succeeded, but the
supported Windows transfer helper failed at `os.setxattr`, including one bounded
retry; no installed file or pixels were available. The user subsequently replaced
that dependency with the explicit shared-toggle reference above. No storage or
metadata bypass was used. Screenshots are internal visual verification only;
the parent explicitly requested no Library upload for this task.

## Verification plan

- Unit regressions for blank root-edit abandonment, serial TMDB writes and
  retaining failed drafts on detach. Browser tests cover stale test responses.
  Preserve the existing remount and scan-guard tests.
- Synthetic/mocked browser cases for picker confirm/cancel/error/history, input
  blur versus plus/remove ordering, autosave failure/retry/remount, test loading
  and stale completion, keyboard/tooltips and no implicit provider requests.
- en/zh at desktop, 390px and 320px; screenshot inspection, lint, typecheck,
  production build, relevant backend tests and final exact-head CI/review.
- Use only disposable configuration/media and simulated provider APIs. Do not
  enter any real credential, alter user media, deploy or bypass branch protection.

## Implementation decisions

- Reuse `ToggleSwitch` directly (48 x 28px). Chinese/English labels and the
  accessible current-language name identify it as a language selector.
- Keep completed root snapshots as the restoration baseline, including failed
  removals; an old saved row index must not restore a different root. Explicit
  remove remains the only way to delete a configured path. Picker append order
  preserves the first-root convention without the removed Use as first action.
- Close the picker when Settings history leaves Library. Visited categories stay
  mounted, so merely hiding Library would otherwise retain Dialog isolation.
  Refresh directory listings on open; selection is disabled until a successful
  current listing. Narrow/short screens stack actions and scroll directory data.
- Share the existing Base URL session between its editor and the AI test guard.
  Test generations invalidate on edits and suppress stale responses. A fixed
  result slot sits to the right of each test button. Localized tooltips report
  outcomes without exposing provider response messages or credentials.
- TMDB uses the same bounded serial session registry with failed-draft retention
  across unmounts. Unsubmitted idle input is abandoned on full page departure.
  Only configuration metadata enters SWR; no key is persisted in browser storage.
  Source ownership, loading failures and save retry remain visible/accessible.

## Verification evidence

- Frontend unit: 121 passed. Lint and typecheck passed.
- Backend: `python -m unittest test_settings_autosave test_api_routes -q`, 26 passed;
  mocked calls verify field-level preferences remain independent of model loading.
- Production build: `next build --webpack` via the isolated E2E runner. Webpack is
  the existing local Windows workaround; no build configuration is changed.
- Related E2E: final 65 passed, including en/zh picker actions inside a 320 x 568px
  viewport after the responsive refinement. All tests use disposable data and
  mock provider endpoints. Existing roots/Base URL remount races and global scan
  guards remain covered, together with all eight Settings categories.
- Manually inspected Chrome plus 18 general/library/connections screenshots:
  en/zh at 1440, 390 and 320px. Additional screenshots cover loading, save/test
  failures and picker errors. Local originals and a SHA-256 manifest are under
  `frontend/e2e-artifacts/` and `.mcp-artifacts/settings-feedback-visual/`.
  No Library uploads were requested for these internal screenshots.

## Remaining work

Commit/push/draft PR, exact-head CI and the parent's independent review precede
normal merge. There is no reference-image
blocker after the user's explicit clarification. No deployment is authorized.
