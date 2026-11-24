# Trust Completed Materials Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan inline.

**Goal:** Resume existing videos without hashing, decoding or recursively re-admitting completed materials.

**Architecture:** The public resume call owns an invocation-local material reader. It reads committed revision views and completed clip sidecars directly, preserving failed/pending reviews and original request identities. New outputs continue through the existing generation and technical checks.

**Tech Stack:** Python 3.12, pytest, existing JSON production records.

**Spec:** User instructions in this conversation: existing materials will not be changed; do not validate generated materials; keep background generation stopped.

## Global Constraints

- No video generation, model downloads, production media edits or background restart.
- Keep RunLock ownership, missing-file errors, failed observations and unknown original submissions.
- Public ordinary resume and review submission use the new reader by default; explicit revision creation and publication keep their existing contracts.
- Direct validation APIs and new runs remain strict outside the resume scope.

## Review Focus

- Inherited completed clips must load saved source metadata without rebuilding source scene contexts.
- Missing completed media must stop recovery instead of silently creating a replacement request.
- New clips created during this invocation must still receive their original technical checks.
- Failed and unreviewed clips must not become accepted.
- Invocation caches must not retain mutable review receipts or leak into later invocations.

## Task 1: Read completed materials directly

**Files:** New `runtime/resume_materials.py`, new `tests/unit/test_resume_materials.py`; hooks in revision, reference and clip record readers.

- [x] Write focused failing tests covering scope isolation, committed revision views, local/inherited clip reuse, missing media, live review status and new-clip checks.
- [x] Run the new tests and observe failures before implementation.
- [x] Implement the invocation-local reader and replace recursive source reconstruction only inside this scope.
- [x] Run the new tests and the affected existing unit tests.

## Task 2: Connect public resume and verify paused task

**Files:** `production.py`, `production_scene_pipeline.py`, `scene_clip_records.py`, `README.md`.

- [x] Activate the scope for existing ordinary resumes/review inputs, skip already-finished reference-image preparation, retain original requests and backend selection.
- [x] Test public entry activation and replay against a local fixture; run relevant transaction/observation tests.
- [x] Perform one bounded, read-only reconstruction of Voyager revision10 progress without inference, regeneration or production writes.
- [x] Document the default behavior and report measured results and limitations; leave generation stopped.

## Execution ledger

- Ruling: Work in the current clean `v2` checkout to apply the requested local behavior directly; no worktree, commit or service start is required.
- Initial evidence: live stacks repeatedly entered `RevisionGuard._verify_dependencies` and source scene-context/reference reconstruction. Resume was stopped at user request before this change.
- Ruling: Scope automatic trust to ordinary Wan (`scene_rendering.mode` absent). Specialized whole/temporal protocols, explicit revisions, upscale products and final publication retain their separate recovery contracts.
- Read-only Voyager10 result: frozen inputs 1.281s, prepared inputs 1.375s, scene context 4.453s, complete progress scan 5.687s; 137 scenes, 41 completed clips, 11 accepted, 1 rejected. No inference or production writes. No claim about full-video generation speed.
- Independent review found missing-template recovery, write-side receipt replay, incomplete raw-failure artifact bindings, specialized renderer compatibility and one missing guard method. Regression tests were observed failing, then all five fixes passed; follow-up review found no remaining Critical/Important issue in this scope.
- Original-HEAD baseline under `E:/VideoAI/scratch/trust-materials-baseline-20261122` reproduces all 11 `test_scene_pipeline.py` fixture failures (7 passed); the shared ffmpeg path is rejected by isolated runtime policy before changed recovery code runs. Production path policy was not changed.
- Final focused suite: **192 passed in 23.54s**, including the public offline pipeline integration, completed-material regressions, original-submission recovery, clip observations, prompt inheritance and strict validation APIs outside the trusted scope. JUnit report: `E:/VideoAI/scratch/trust-materials-final-20261122.xml`.
- Background `make-video`/Wan/Comfy generation processes remain absent. No commit, production restart or publication was performed.

### Existing fixture failures reproduced at original HEAD

All are in `tests/unit/test_scene_pipeline.py` and fail in `freeze_inputs` before recovery, because the configured ffmpeg is outside the isolated test runtime:

- `test_empty_scene_progress_is_read_only_and_does_not_invent_common_prefix`
- `test_half_prepared_prefix_is_blocked_and_never_overwritten`
- `test_invalid_email_secret_is_rejected_before_submission_copy`
- `test_automatic_units_failure_reports_the_actual_early_stage`
- `test_validated_candidate_prefix_does_not_reenter_earlier_stage_writers`
- `test_automatic_common_cannot_claim_prepared_reports_without_original_speech_records`
- `test_baseline_http_send_rechecks_real_lock_after_credentials_are_read`
- `test_pipeline_inputs_boundary_precedes_common_ready_marker`
- `test_common_records_reject_noncanonical_schema_and_time[inputs-schema_version-2.0]`
- `test_common_records_reject_noncanonical_schema_and_time[common-inputs-ready-schema_version-2.0]`
- `test_common_records_reject_noncanonical_schema_and_time[common-inputs-ready-created_at-invalid timestamp]`
