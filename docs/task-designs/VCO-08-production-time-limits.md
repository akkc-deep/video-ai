# Formal production without execution time limits

User requirement: “我的意思是在正式生产视频的时候也不要设置预算”.

Formal production must wait for completion regardless of elapsed job, startup, phase,
clip, frame, or local media-processing time. Single HTTP/connect timeouts,
ownership checks, cancellation, unknown-submission recovery without re-POST,
resource ceilings, and media/frame specifications remain enforced.

Implementation uses a call-local production execution scope. It is entered by
the public automatic production API and independent formal scene production
operations, and reset on success, exception, or interruption. Generic media
and research APIs retain their existing bounded defaults outside that scope.
Each Comfy request still uses its finite configured request timeout. Startup
waits for health without a total deadline and fails if its owned process exits. Tracking
has no overall deadline in production. Local subprocesses use timeout=None.
New frozen options explicitly record unlimited_v1 and a null media-command
limit; old frozen options remain readable and are never rewritten. Resuming
an old formal run uses the new execution policy without changing its identity.

Plan:

- [x] Add focused failing tests for production entry propagation, elapsed Wan
  and frame work, finite HTTP requests, immutable resume identity, and media.
- [x] Implement execution scope, frozen-policy validation, tracking and local
  media propagation while retaining provenance and ownership checks.
- [x] Run focused RED/GREEN and affected production/transaction/media tests in
  the root agent's allocated serial testing slot; defer full-suite regression
  until VCO-08 closeout as instructed.
- [x] Report verification evidence and remaining request/service controls.

Main automatic/scene implementation and verification:

- Public `make_video`, formal scene operations, and automatic image, speech,
  Wan, upscale and composition producers enter the unlimited scope. The scope
  resets on ordinary failure and KeyboardInterrupt. Original frame send guards
  stay cancelled after return; identity and ownership checks remain active.
- Local FFmpeg/FFprobe, full native frame proofs, color analysis, continuity,
  capability probes and YAML processing have no execution timeout in that scope.
- A new command receipt records `timeout_seconds=null` with
  `time_limits=unlimited_v1`. Receipt consumers validate that explicit pair
  independently of the current scope. Historical 300-second receipts retain
  their original policy and timestamp checks. Durable direct composition events
  accept an explicit null timeout or the historical numeric 300/300.0, while still
  matching arguments, working directory, original raw logs and successful finish.
- RED/GREEN includes elapsed clip/frame/legacy tracking, Jimeng tasks, service
  startup/exit, real three-frame native extraction, resource ceilings, scope
  cancellation, and independent scene review entry. Real compose/candidate
  validation receipts with simulated 600-second execution pass later load calls
  outside the production scope.
- 206 production, service, transaction, media and delivery recovery tests passed
  in 289.62 seconds: `test-1230b4252d7e4e32bdb562566ea8f40a.log` under
  `D:/VideoSi/cache/video-ai/logs`. A subsequent 46-test batch passed in 20.63
  seconds: `test-1eeafe23186c4dff94e23db7082e8686.log`. The earlier
  `test-c9ccf77ba6f5436591437d77fd746d0a.log` batch was interrupted and has no
  final result; it is not counted as passing.
- Independent review identified a remaining ByteGuard interval and two
  historical numeric-type compatibility defects. Five targeted tests first
  failed (`test-8db3763de2464ead99b30aa5f558a4a1.log`), then passed after
  correction (`test-a7c49945dbd6464aa2065daccd6fadc4.log`, 11.92 seconds).
  ByteGuard still rejects same-stat changed bytes after an unlimited verification.
  Generic finite command receipts preserve integer 300; actual `run_logged`
  historical float 300.0 events remain recoverable in both composition paths.
- A 435-test affected batch reached 215 passing tests before finding an old
  injected scene-client compatibility problem (`test-7a494ac2efab4f89a8d1cf038d117e01.log`).
  That batch is not claimed to pass. Scene producers now pass the frozen
  `comfy_request` timeout explicitly to their transaction, so injected clients
  need not expose a new attribute. Two focused tests reproduced the missing
  explicit-timeout API before that fix (`test-47611a0fea8f46c79d731b3940934302.log`).
  Final focused verification passed all 84 tests in 253.25 seconds, including
  all 26 no-limit cases, both transaction unit files and the actual scene-media
  flow that exposed the problem (`test-b7a97859ba09406a8e06349e15516dc1.log`).
  The final directly affected integration/shared-media results are below.
  Interrupted batches (`test-caa51f55993b4c58a3e4d8bcb49afe36.log`,
  `test-ead89ec1341348369f98e6285b9f446b.log` and
  `test-3b0cd50c21da498cb6c246c554a6d77f.log`) have no final passing result.

The separate public staged pipeline also reaches its own DeadlineHttp,
upscale evidence and resume protocols. Its implementation and principal
476-test compatibility result belong to the legacy agent. The final three
legacy whole files were verified in this agent's 230-test batch below.

Retained controls are finite individual HTTP/connect/SMTP operations, signed
URL validity at submission, resource-sampling queries, and termination/cleanup
escalation waits. These describe communications, credentials, monitoring and
cancellation; none is an overall production execution limit. Offline research,
component experiments and generic media calls outside the production scope
retain their existing default limits.

Final affected verification after the root-owned LongCat first window:

The first 275-selected invocation was interrupted before completed-test output
for the GPU trial (`test-3b0cd50c21da498cb6c246c554a6d77f.log`). Its resumed
invocation (`test-06952bf3eeb047bd8c00a32427e1541a.log`) passed five real small
media/upscale cases, then entered the unchanged 200-frame 93/92/15 mapping
fixture. The root explicitly authorized stopping that owned fixture and
deferring the unrelated long-N/full-chain regression to final VCO-08/project
regression. That invocation has **5 PASS plus an interrupted case**, not a
complete 275-test passing result. The already-passing full scene-media case
was deliberately excluded from both invocations; it passed in the 84-test batch.

The change-specific scope was then verified with all eight whole files:
**230 passed in 270.45 seconds**,
`test-b1033d47453b46108f8ffd030e2dbf35.log`.

| Owner | File under tests/unit | Passing cases |
| --- | --- | ---: |
| Main/shared | test_video.py | 68 |
| Main/shared | test_frames.py | 33 |
| Main/shared | test_scene_native_batch.py | 21 |
| Main/shared | test_colorimetry.py | 40 |
| Main/shared | test_continuity_report.py | 12 |
| Legacy | test_start_image_generation.py | 15 |
| Legacy | test_start_image_checks.py | 36 |
| Legacy | test_pipeline_revision_resume.py | 5 |

The root confirmed these seven directly related integration IDs, all of which
passed in **494.91 seconds**, `test-0a81e2f4e676484290c597707e4f56bb.log`:

- `test_scene_continuity_flow.py::test_real_tiny_frames_to_report_and_explicit_fixture_review`
- `test_scene_continuity_flow.py::test_explicit_recovery_keeps_single_analysis_and_same_author_bytes`
- `test_scene_color_repair_flow.py::test_genuine_closed_profile_to_all_frame_noop_and_readonly_status`
- `test_scene_color_repair_flow.py::test_genuine_cpu_candidate_master_playback_reports_and_fixture_review`
- `test_scene_pipeline_recovery.py::test_new_original_text_uses_automatic_prefix_and_exact_baseline_prompts[intent]`
- `test_scene_continuity_recovery.py::test_direct_media_context_cannot_bypass_current_guard`
- `test_scene_continuity_recovery.py::test_media_write_guard_rechecks_current_epoch_before_write`

These exercise genuine 64x36 two-frame continuity/repair media, no-op and
encoding branches, independent status/report consumption, durable recovery,
the public automatic prefix and current epoch/write guards. All integration
paths above are under `tests/integration`. No source changed during the final
230-test and seven-test batches. No model was called.

The five completed cases from the interrupted invocation were the remaining
two `test_scene_media_flow.py` cases and the first three small
`test_scene_upscale_flow.py` cases. Together, those five, the 230 unit cases
and the seven selected integration cases cover 242 of the original remaining
275 cases. The following **33 cases are deferred**, not claimed to pass, and
must run in final VCO-08/project regression:

- `test_scene_upscale_flow.py`: `test_authentic_200_frame_chain_submits_only_93_92_15_and_contributes_every_retained_frame` (interrupted), and `test_later_frame_pending_raw_conflict_and_orphan_body_prevent_all_earlier_new_posts`.
- `test_scene_pipeline_recovery.py`: `test_new_original_text_uses_automatic_prefix_and_exact_baseline_prompts[tts_body]`, the same test with `[large_tts_body]`, and `test_prepared_public_pipeline_waits_for_parent_and_never_posts_child_or_duplicate` (includes full composition/publish).
- `test_scene_continuity_flow.py`: `test_public_local_analysis_and_review_transactions_exist`, `test_manifest_binding_rejects_incomplete_frames_wrong_join_and_reference`, `test_three_clip_prefix_requires_same_author_and_all_risk_responses`, `test_confirmed_raw_defect_survives_ready_receipt_and_same_media_reassessment`, `test_partial_audit_resume_preserves_first_attempt_and_rejects_two_successes`, and `test_partial_local_attempts_are_bounded_and_fourth_does_not_measure`.
- `test_scene_continuity_recovery.py`: `test_continuity_review_is_run_only_and_rejects_conflicting_actions`, `test_cli_forwards_continuity_review_without_advancing`, all six parameter cases of `test_cli_continuity_review_is_mutually_exclusive`, `test_public_source_acceptance_adds_current_overlay_after_base`, `test_completed_prefix_validates_history_before_current_wait`, `test_source_finish_preserves_original_complete_while_current_epoch_waits`, `test_missing_source_aggregate_wait_does_not_call_original_model_writer`, `test_confirmed_issue_is_blocked_instead_of_pending`, both parameter cases of `test_parent_guard_rechecks_new_submit_but_preserves_durable_get_recovery`, `test_parent_scoped_admission_includes_earlier_retained_scene_prefix`, `test_review_cannot_borrow_receipt_for_different_original_video_bytes`, `test_prefix_playback_rejects_fabricated_historical_assessment_stub`, `test_inherited_binding_reads_metadata_from_proved_origin`, and `test_direct_publish_checks_current_diagnostics_even_for_completed_transaction` (20 cases total).
- `test_scene_color_repair_flow.py`: `test_explicit_request_rejects_unverified_profile_before_candidate_media`, and `test_clip_revision_and_media_low_level_boundaries_reject_research_bytes`.

The two current-epoch/write-guard cases in the final seven also belong to the
root's original 21-test research/natural-repair selection. The root will run
the other **19 cases in its original four files** against the same stable
source, avoiding duplication. That final root-owned batch remains pending at
this handoff; its prior result predates these shared source changes.
