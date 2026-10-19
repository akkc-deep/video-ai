# JIM-06 Implementation Plan

> **For agentic workers:** Use the task-specific contract in JIM-06-design.md. Execute test first, observe RED, implement, verify GREEN. Independent modules may be delegated with fixed interfaces and exclusive file ownership.

**Goal:** Produce exact scene-frame 1080p candidates with complete narration/subtitles and publish only the exact version accepted by a complete final-film observation.

**Architecture:** New schema=2 modules and directories consume the existing immutable JIM-03/JIM-05 acceptance APIs. Frame upscaling, composition and final observation/delivery have separate durable gates; completed replay only reads evidence. Existing shot consumers remain unchanged.

**Tech Stack:** Python 3.12, pytest, ffmpeg/ffprobe, ComfyUI RealESRGAN, existing RunLock/PathPolicy and media helpers.

**Spec:** `docs/task-designs/JIM-06-design.md` (complete authoritative signatures, exact fields, recipes and failure rules).

## Global Constraints

- paragraph_jimeng_v1, schema_version=2; native16/cut, 1920x1080, RealESRGAN_x4plus.pth, burned original subtitles.
- Never change upstream scene/clip budgets or drop a child head twice: 200 retained frames = 93+92+15, generated third-clip indices 1..15.
- Complete image and dynamic observation acceptance precedes every service/POST/encode/delivery; rehash captured upstream bytes and inventories before side effects.
- All record/media writes on the caller thread under the actual run lock; intent before POST, recover original UUID/graph/output, never automatically resubmit an unknown task.
- Actual final-film observation is a separate gate. Test-authored observations prove protocol behavior only.
- No CLI/coordinator/revisions or real cloud/model/email calls. Preserve existing checkout and read-only Git metadata.
- Every Python invocation follows scripts/bootstrap.ps1, uses -B, and stores runtime/temp/log files under D:/VideoSi. Run tests serially.

## Review Focus

- A later frame's conflicting transaction must stop all new submissions, including earlier missing frames.
- Crash after original command completion must recover exact encode/probe evidence without re-encoding accepted media.
- Failed observation raw bytes without a rejection receipt still block; accepted observations resist later failed submissions.
- Existing same-byte external output without file ownership is a conflict; receipt publishes last.
- Late transport threads cannot submit or persist after deadline/lock loss; service cleanup failure cannot return success.

### Task 1: Exact retained-frame upscale and immutable records

**Files:** Create planning/scene_media.py, media/scene_upscale.py, runtime/scene_media_records.py, runtime/scene_upscale_transactions.py, runtime/production_scene_upscale.py and private helpers; tests/unit/test_scene_media.py, test_scene_upscale_transactions.py, test_scene_media_records.py; tests/scene_media_helpers.py and upscale integration tests.

**Interfaces:** Produce plan_scene_upscale(scene_clips), plan_scene_contributions(scene_clips,upscaled,timeline); SceneMediaResult, load_scene_media_progress, four require_scene_* functions; produce_scene_upscaled_clips and the exact transaction signatures from the spec. Downstream validators may be imported lazily from private composition/delivery modules to avoid cycles.

- [x] Write and run test_200_retained_frames_upscale_once_without_second_head_drop first; expected RED for missing API.
- [x] Implement pure plans; assert exact coverage, real JIM-05 mapping and malformed/bool/extra-field rejection.
- [x] Test first, then implement native retained RGB24 extraction, immutable extraction/media receipts and recovery, full pixel verification.
- [x] Test first, then implement separate PNG transaction with raw HTTP, UUID/graph/prefix/node validation, bounded transport/health and original-task recovery.
- [x] Implement complete batch preflight, guarded service lifecycle, once-only 200-frame output/complete and read-only acceptance/progress. Test future-frame conflicts, unknown run, cleanup and late-thread failures.
- [x] Run Task 1 unit/integration tests; save exact commands/results.

### Task 2: Full narration/subtitles and candidate composition

**Files:** Create runtime/production_scene_composition.py and private helpers; tests/integration/test_scene_media_flow.py and composition recovery tests.

**Interfaces:** Consume Task 1 require_scene_upscale_acceptance and pure contributions. Produce produce_scene_composition(frozen,units,timeline,*,paths,logger,lock=None), plus private read-only require implementation usable by scene_media_records. No writes to Task 1-owned modules.

- [x] Write failing tests using authentic admitted fixtures, then implement exact inputs/contributions/materialized-ready/materialized schemas.
- [x] Verify original PCM speech bytes and zero pauses/padding; derive SRT/ASS through CompositionSettings/PrivateFont and existing layout.
- [x] Implement guarded unique encode/probe command intents and success recovery; use exact existing encoding flags and full media validation.
- [x] Implement identity candidate copy, candidate-commit and read-only complete reconstruction. Recover ready/command evidence without changing timestamps or re-encoding.
- [x] Candidate returns awaiting_final_review with actual MP4 and unverified template; final observation module provides template builder. Test no external outputs, tampering, non-integral tail samples and interrupted boundaries.
- [x] Run Task 2 tests and record evidence.

### Task 3: Actual final-film observation, ownership-safe delivery and prefix

**Files:** Create runtime/scene_final_observations.py, runtime/production_scene_delivery.py, runtime/scene_completed.py and private helpers; tests/unit/test_scene_final_observations.py and tests/integration/test_scene_media_recovery.py.

**Interfaces:** Consume Task 1/2 immutable complete/candidate dictionaries. Produce exact template/validation functions, consume_scene_final_observation, produce_scene_delivery, validate_scene_completed_prefix. Expose private read-only final/delivery validators for Task 1 facade via lazy imports; no writes to Task 1/2-owned files.

- [x] Write failing pure tests for exact candidate/scene/join/unit identity, full playback, verdict/check consistency, timezone bounds and malformed data.
- [x] Implement exact template/validator and immutable authored-source scanning with acceptance/rejection receipt recovery and failed-raw blocking.
- [x] Test first, implement dedicated schema=2 output lock, immutable temp attempts, mutable publishing transaction, file-ID ownership, fsync and no-overwrite rename, receipt-last publishing.
- [x] Test unknown temp ownership, rename-before-progress recovery, source/lock changes, existing equal-byte unrelated targets and accepted-version changes.
- [x] Implement read-only completed prefix and duplicate replay without services/POST/extract/copy/encode.
- [x] Run Task 3 tests and record evidence.

### Task 4: Integration, review, regression, documentation and handoff

**Files:** Update docs/jimeng-candidates.md and task board; create JIM-06-verification.md; successor artifacts only after JIM-06 completion.

- [x] Integrate exact module interfaces, execute authentic short flow and 200-frame native mapping; no fake upstream complete records.
- [x] Fresh independent review against full design; fix confirmed important defects with regression tests.
- [x] Run all new tests, the historical command and fresh full pytest from design Tests; capture counts, exit status and final file SHA256.
- [x] Document APIs/status/waiting/failed-final behavior and remaining real-service acceptance boundary.
- [x] Only after acceptance evidence, record COMPLETED. Then select successor by board Order, finish/link its design and write/link handoff before READY.

## Execution record

- 2026-10-19: User explicitly requested 完成JIM-06. Full design/handoff read. Existing main checkout contains required uncommitted JIM-03..05 artifacts; .git is read-only, so work stays in the supplied checkout without Git mutations.
- Preflight interface scan: Task 1 plans/complete feed Task 2 contributions; Task 2 candidate feeds Task 3 observation; Task 3 read-only validators feed Task 1 facade lazily. File ownership is disjoint. Exact dictionaries/signatures come from the single existing design. No contract conflict identified.
- Implementation clarification: private facade validators take the fully admitted context, avoiding repeated full upstream decoding within one invocation. Observation validator expected is `{template, created_at}` as in existing clip protocol: the exact serialized template has no candidate creation timestamp, so the wrapper supplies its authentic lower time bound. Observation fields and public function signatures stay as designed.
- Required first RED observed by upscale implementer: 1 failed in 0.15s, missing video_ai.planning.scene_media, using real JIM-05 200-frame budgets/mapping and the specified first test.
- Initial pure plan GREEN: 1 passed in 0.12s. Observation initial pure GREEN: 24 passed in 0.18s. Composition/runtime initial missing-module REDs recorded in worker reports.
- First authentic upscale diagnostic: 11 passed in 672.44s, exit 0, 66 retained frames and unchanged once-only replay. Modules/tests changed after that process started, so this is original-import diagnostic evidence, not the final-tree gate. Subsequent short fixtures derive shorter real PCM before any accepted plan is committed; explicit long_scene retains the upstream 200-frame chain.
- Delivery quick protocol/ownership batch: 59 passed, 2 authentic cases deselected in 7.12s, exit 0. Later caller-thread guard changes require fresh final execution.
- Composition primary authentic diagnostic: 1 passed, 1 deselected in 325.86s, exit 0. Real 6-frame 1080p candidate, original nonzero PCM and zero pauses/padding, original SRT/ASS/font, full decode and unverified final template; no formal output. Final current-tree suite remains pending.
- Tool identity clarification: current FrozenInputs contains model stamps and frozen configured tool paths, but no original binary tool stamps. Preserve exact legacy/new schemas; capture invocation-local ffmpeg/ffprobe ArtifactStamp guards, verify before/after effects, and bind original command receipts/media. Do not claim historical binary identity that upstream never recorded.

### Current verification and review checkpoint

- Independent full read-only review of all 22 new implementation/test files is `docs/task-designs/JIM-06-review.md`: no Critical, four Important (I1 partial pending-frame adjudication, I2 full stage guard propagation, I3 final-scan acceptance race, I4 valid promoted-staging capture), plus two maintenance/test-scope observations. Corrections are in progress; this is not final approval.
- Authentic delivery attempt failed before Task 3 in common-context `read_json(str)` (1 failed, 27 deselected, 179.32s). Preserved upstream run `20261019-152318-41fae13c7243`; direct readonly replay confirmed traceback and test-first Path conversion fixed it. A later direct replay found valid promoted staging absent; receipt-aware capture/negative guards added. Fresh Task 1 units progressed through 51/52/53 to **58 passed in 6.53s** after narrow REDs; authentic preserved-context GREEN remains pending.
- I2 candidate staging regressions: **2 failed, 1 deselected in 0.36s** then **2 passed, 1 deselected in 0.35s**; composition copies all guard categories and captures candidate-ready via receipt-aware logic. Composition's full two-file six-case batch remains unrun.
- I3 final-scan/JSON-rebind/failed-repair regressions: four scan cases and one repair case observed RED; corrected Task 3 quick suite **65 passed, 2 authentic deselected in 7.21s**. Further original raw/receipt inventory snapshot race cases are authored and await narrow RED/GREEN.
- Only one Python/test process may run: the root grants a serial test lease. Current lease: `scene_upscale` for extraction-log guard tests and preserved-run context; `scene_delivery` next for six observation snapshot race cases. `scene_composition` is frozen/finished pending scoped review and root final suite. Independent reviewer `jim06_review` is finished and can resume for scoped correction review.
- Final current-tree targeted, exact historical and fresh full suite have **not run**. After scoped fixes/review, run `D:/VideoSi/cache/video-ai/logs/jim-06-serial-validation.ps1 -Suite all` from bootstrapped context (script bootstraps itself). The targeted stage is fail-fast and puts costly 200-frame integration last; all suites are serial. Preserve original review snapshot; build a separate refreshed package with `jim-06-build-review-package.ps1 -Package <new-path>`.
- JIM-05 captured identities: all 20 predecessor implementation/test files still match; only its captured `docs/jimeng-candidates.md` changed due this task's appended API documentation. No Git mutations or real-service calls.

### Final correction checkpoint

- Source JSON admission now captures immutable raw byte/inventory snapshots before gates and checks them afterward; recursive adoption uses those original bytes. Pre-gate PCM SHA and original command stdout/stderr (including empty files) close the remaining unhashed-input window. Four additional non-JSON race cases observed RED, then Task 1's three unit files **74 passed in 7.21s**.
- Composition now binds original `events.jsonl` after both successful commands, revalidates the exact encode/probe intent/receipt/completion proofs and rechecks the captured hash. Two removal/mutation regressions observed RED, then **2 passed in 0.36s**; all non-authentic composition recovery cases **4 passed in 0.53s**. Legitimate command appends occur before binding.
- Unknown/unprepared final-entry normalization observed six REDs; quick Task 3 batch then **77 passed**. Scoped independent rereview found accepted/rejected early reuse still needed a final guard after validating the repeated authored input. Twelve mutation regressions observed RED, three legal reuse cases already passed; minimal correction and failed-receipt repair snapshot refresh gave **92 passed, 2 authentic deselected in 8.24s**.
- Scoped reviewer confirmed original raw-protocol I1 adjudication, new-decisive-receipt I3 snapshots and receipt-aware I4 staging, while identifying the early-reuse issue above and known successful PNG validation before batch submission. The latter two prefix forms (raw-success/no-submission and submission/no-output-ready) are being corrected before final source freeze.
- Final targeted, historical and full runs remain pending; incremental tests above do not replace authentic complete delivery/recovery or real 200-frame coverage. Verification record is `docs/task-designs/JIM-06-verification.md` and currently explicitly pending.

### Serial outcome checkpoint

- Frozen implementation passed independent follow-up review: original I1–I4 and all scoped guard findings closed statically, no remaining Critical/Important; 22/22 packaged hashes matched. See `JIM-06-review-followup.md`.
- Initial fresh targeted run: **189 passed, 1 failed in 8718.12s**, exit 1. All authentic candidate, final observation/delivery/twice replay, composition recovery and real 200-frame 93/92/15 assertions passed. The last pending-conflict integration failed before its intended terminal-write interruption because its local `timeout=10` expired under full byte guards.
- Minimal test-only correction uses the same frozen `timeouts.upscale_frame` budget as the production entrypoint (default 180 seconds). No production code, deadline guard or business assertion changed. Independent before/after hashes found only that test file changed; reviewer confirmed the final 22-file package and all 13 unchanged implementation files.
- Affected authentic case recheck: **1 passed in 269.18s**, exit 0, log `D:/VideoSi/cache/video-ai/logs/jim-06-pending-conflict-recheck.txt`. The initial failure is preserved separately, not presented as a single all-green targeted command. Fresh whole-suite execution will cover all 190 new cases on final test bytes.
- Exact historical then fresh full suite started through `D:/VideoSi/cache/video-ai/logs/jim-06-resume-validation.ps1`, session `97259`. This preserves each suite's identities separately and keeps serial bootstrap/Python -B/runtime constraints. Both outcomes remain pending at this checkpoint.
- Historical completed: **456 passed in 3866.66s**, exit 0, with **342/342 file identities matching**. Its preserved before/after vectors are `jim-06-historical-verified-files.json` and `jim-06-historical-verified-files-check.json`. Fresh full pytest then started in session `97259`, bootstrap log `jim-06-serial-validation-f47c6e8b3a734809a2ca07ac830a3c99.log`; full outcome remains pending. No source/test/usage edits have occurred since the single test-budget correction.

### Final execution gate — 2026-10-20

- Fresh full pytest: **3396 passed in 15981.10s (4:26:21)**, exit 0, including all 190 new cases. Runner and independent root verification both confirmed **342/342 identities match**, changed=[]. Historical: **456 passed**, exit 0. The original targeted **189 passed + 1 failed** and corrected-case **1 passed** remain recorded separately; the fresh full suite covers the corrected final bytes.
- Final review package SHA256 rechecked as DC293E4FBBF90F2C603FCF1BECE5DEB515A4C9E15E5F6A2E1167C6271847B9E5. No remaining Critical/Important findings. Exact evidence and authentic run paths are in JIM-06-verification.md.
- User clarified that video total frames are unrestricted and frame rate remains unchanged: native 16 fps and the full original timeline are retained. No test was shortened and no fps change was made.
- All implementation/review/execution gates are complete. Current-task completion and successor design/handoff preparation are the remaining documentation steps; JIM-07 implementation is not started.

- Documentation closure: JIM-06 completion was recorded first. JIM-07 design was then completed, fully read and linked; the next-task handoff was written/read with all 33 referenced paths present, linked while NOT_STARTED, and only then transitioned to READY. JIM-07 implementation and tests have not started. All plan checklist items are complete.
