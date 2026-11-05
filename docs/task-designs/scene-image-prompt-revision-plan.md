# Scene image prompt revision implementation plan

> Execute inline using superpowers:executing-plans. User already opted out of further design approvals. Git metadata is read-only; preserve existing changes and do not commit.

**Goal:** Regenerate scene_0001 using the user's departure-direction feedback while preserving the source run, audio and base plan.

**Architecture:** Extend regenerate_images requests with optional image_prompt_overrides, a scene ID to nonempty prompt mapping. The immutable revision request binds these overrides. A shared effective prompt resolver applies explicit changes and inherits prior changes only while the base plan is imported. Generation and verification use the same resolver for baseline and reference images. Old requests retain their exact field contract.

**Tech stack:** Existing Python CLI, Jimeng, revision receipts and pytest.

**Spec:** User rejected both candidates and said the second looks like a return to Earth. Show Earth behind the probe, departure into deep space, and no rocket exhaust. This plan is the concise implementation specification.

## Constraints and review focus

- Preserve source bytes and all original speech; create a separate frozen revision.
- Reject empty prompts, URLs, unknown/non-target scene IDs and overrides on other revision kinds before effects.
- Preserve existing revision formats and exact request verification.
- Inherit corrections across later revisions; do not carry them into a replanned scene layout.
- Replay must not submit new paid tasks; altered revision requests must fail binding checks.

## Task 1: Bound prompt overrides

- [x] Add failing validation and real revision/pipeline tests for corrected submissions, immutable origin, replay, reference prompt construction and later inheritance.
- [x] Run new tests and confirm expected failures.
- [x] Implement optional request validation and shared effective prompt resolver; wire generation and evidence readers.
- [x] Run focused revision, baseline/reference image and pipeline regressions.
- [x] Review the change with a fresh reviewer and resolve material findings.

## Task 2: Actual retry

- [x] Write a regenerate_images request with the corrected first-scene prompt.
- [x] Prepare the new frozen revision and generate two new candidates, reusing speech and plan.
- [x] Inspect actual output and report image selection and any real credential boundary.

## Ledger

Initial: no source artifacts or Git metadata will be rewritten. Full-suite reruns are excluded: the prior run was stopped after only 2% with no failures; run regressions appropriate to this change as required by the task instructions.

Task 1 RED: unit test failed on strict legacy request fields (test-975fd6261a6c45f9816d4329e01bb73a.log); real revision/pipeline integration failed because the optional override field was rejected (test-b72f5a3f1c6446afa1c856ee72eea867.log). First GREEN: 72 passed in 100.47s (test-0dd4df2a36634794a6e979e0c5265638.log). Broader relevant regression suite is running.

Final review: independent reviewer review_prompt_revision found no Important/Critical issues. Minor coverage additions deferred: combined inherited/new overrides, actual reference generation/replay, source with no accepted choices. Actual retry exercises the last case; direct reference prompt construction has an integration regression.

Actual request: D:/VideoSi/projects/video-ai/inputs/voyager-departure-revision-1a5f92e2-ac83-424f-906b-90f0dcd8fc59.json. Target: D:/VideoSi/projects/video-ai/runs/20261104-053708-1a5f92e2ac83. Source records remain unmodified. SMTP remains available only to the human's Windows account; actual generation is permitted with available Volc credentials but notification needs the user helper if this boundary remains.

Final focused evidence: initial 72 tests passed; added reference-context and tamper-binding tests both passed in 63.95s, log test-aadd4e8e92ed470b81eaf76737418c89.log. Broader suite test-c5c82479f20a49a18d5b1fa02b845177.log was stopped after excessive runtime (126 progress dots, no failure output observed); it did not finish and is not claimed passing. Do not repeat it without a new reason.

Actual preparation succeeded: start-cf095d46240d45f18856b420fb907b10.log, exit 0, revision_ready. All 245 PCM files copied and verified; target revision commit and ready records exist. Actual target execution started with start-beb87b48b616466695b1eae1dd56389b.log. No image acceptance has been authored.

Actual recovery findings: first accepted task returned done but image GET hit the 60s HTTPS deadline. Resume (start-420ccd6f8cac4130814b564f33d61382.log) correctly reused that task but refused changed CDN origin hashes. A fresh read-only official query confirmed one output and a changed origin. Added single-output origin refresh receipts without rewriting outputs.json or signed URLs; changed multi-output ordering remains refused. Regression RED: test-5dae685e22df44fb9abffc7e74fc5cde.log. GREEN: 51 baseline/reference candidate tests in 107.31s (test-634294647b0f4ecbafa07159bfc27e08.log). Independent review found no material issue; reference-specific refresh coverage deferred as minor.

Download timing finding: HTTPS calls the ownership callback before every 64KiB read, and the revision callback scans the whole captured closure. Added a GET-only lock callback; paid API callbacks and download transaction boundaries still verify all captured source bytes. New unit RED reproduced the wrong callback (test-7bae359fbb61439fa5d456267d12c295.log). A real RevisionGuard mutation regression asserts no candidate bytes/receipt commit after a changed captured source. Relevant adapter and candidate suites running before actual resume. No network timeout, request identity, task ID or image byte integrity limit was weakened.

Recovery final GREEN: 82 passed in 107.88s, test-e19ea3b24e3b45608d867a20ea7ba836.log. Independent review found no material issue in the GET-only lease checks; complete source validation still protects the save boundaries and all paid calls. Actual task resume is running with start-094be70ea3df495f9f6c4f875d5d6efe.log.

Actual result: both corrected candidates downloaded and decoded, manifest and contact sheet exist. First accepted task reused after its original timeout; single-output refresh receipt preserves original outputs.json. Both persisted requests exactly match the bound scene_0001 override. Actual resume returned blocked/start_images/EmailPreconditionError: SMTP credential unavailable; no new mail receipt or image acceptance exists. Lock released. New contact sheet: target production/image-selection/image_batch_0001/mail/contact_sheet_0001.jpg. User helper D:/VideoSi/cache/video-ai/resume-with-user-smtp.ps1 now defaults to this corrected run and securely prompts if the user's credential is missing. Original source remains the historical run; this is a new revision, not a delivered video.
