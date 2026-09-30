# W12 Beta validation and W13–W14 follow-up

Updated: 2026-10-01
Status: Prepared; no recruitment, participant results or retention claimed

## Entry decision

Open Public Beta recruitment only after Gate E is reviewed against the exact
candidate build and its installation/recovery evidence. Review Gate C/D product
evidence separately. Gate B remains independent: no accepted inferred Graph
edges are released until its strict live/human conclusion is Passed. Do not
substitute deterministic fixtures or developer-operated sessions for users.

Use a small, consented cohort of people who already maintain local movie/NFO
collections. Record OS, installation route and approximate library-size band,
without collecting film titles, media paths, keys or private notes. Recruitment
messages and actual enrollment require a human owner; none were sent here.

## Private Alpha protocol

Give each participant the installation guide and these tasks, with no developer
operation on their behalf:

1. Install without provider keys and import a chosen local NFO collection.
2. Find a Film, explain its metadata/relationship sources, and locate another
   Film using factual Explore.
3. Record a viewing and rating, then find them again in Diary/Cinema DNA.
4. Use the Ask form; when a provider is configured, review interpreted conditions
   before querying and explain why a result matched.
5. Restart and confirm the same records remain. Observe a safe failure case
   using synthetic data only; never request destructive experiments on their library.

Record task outcome, elapsed time, assistance needed, comprehension in the
participant's own words, and blocking/high-priority defects with a redacted
reproduction. A developer takeover is an assisted result, not independent
activation. Consent to a session does not imply consent to upload databases,
screenshots or logs.

Gate C needs at least three independent successful imports and at least two
users correctly explaining Graph relationships and source semantics, plus the
no-key/safety evidence. These counts are currently **unmeasured**.

## Product signal and retention

Anchor W13/W14 to each participant's activation date, not the roadmap label or
calendar week. This plan uses manual opt-in follow-up; no new telemetry or
scheduled messages are installed.

| Window | Evidence to request | Measure |
| --- | --- | --- |
| Activation / D0 | Independent import and first meaningful task | Activated / eligible enrolled; report assistance separately |
| D1–D7 | Another self-initiated Explore, Diary or Ask use | Distinct returning participants / activated participants eligible for seven-day observation |
| D8–D14 | A further self-initiated core action and why it was useful | Distinct returning participants / activated participants eligible for fourteen-day observation |
| Both follow-ups | How it differs from a media-server poster wall; trust issues; workflow used | Qualitative explanations and repeat behavior per workflow |

Opening the app, responding to a reminder, seeded data, automated checks and
developer-led demonstrations are not repeat core behavior. Deduplicate by a
pseudonymous participant ID. Track withdrawal and missing responses separately;
do not classify participants whose window has not elapsed as churned. Always
show numerator, denominator, eligible window and evidence date; small samples
must not be presented as a general retention rate.

Use this local record template (all values start as unmeasured):

```text
participant_alias:
consent_scope_and_date:
candidate_commit_or_image_id:
platform_and_library_size_band:
activation_date_and_assistance:
import_outcome_and_evidence_reference:
source_semantics_explanation:
repeat_workflow_and_dates:
day_7_eligible / observed / missing:
day_14_eligible / observed / missing:
blocking_defect_ids:
withdrawal_or_deletion_request:
```

Keep identifying contact details separately under the human coordinator's
control. Participants can decline evidence capture or withdraw. Delete raw
session material after the agreed review period; retain only consented,
redacted aggregate findings. No participant data belongs in this repository.

## Decision rules

- Gate E unmet: keep Public Beta closed and prioritize the missing safety or
  installation evidence.
- Data loss, credential exposure, or unresolved blocker/high defect: stop the
  candidate rollout and investigate before inviting more participants.
- Gate C unmet: fix onboarding and source comprehension before expanding scope.
- Gate D has no observed repeat behavior: focus on the workflow with the best
  actual evidence; avoid adding a Global Graph or integrations to compensate.
- Continue/focus/delay decisions require dated evidence and an accountable human
  review. Passing engineering tests alone does not satisfy C, D or retention.
