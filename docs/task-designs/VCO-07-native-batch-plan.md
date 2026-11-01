# VCO-07 native PNG batch evidence repair Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans inline. Keep this ledger; no git writes, worktree, installs or full suite.

**Goal:** Finish native whole-scene extraction within its unchanged1200s shared budget while preserving every PNG's complete validation and every persistent-write guard.

**Architecture:** A whole-only producer uses the existing strict PNG decoder and complete source RGB24 pixel comparison, retains per-frame evidence in memory, then writes a bounded aggregate inspection record. It preserves source/video/sequence/hash/alias checks. The original segmented helper and frame180s transaction are unchanged. Explicit recovery validates the exact saved orphan extraction directory; it never treats its first21 inspected files as a completed extraction.

**Tech Stack:** Existing Python3.12, FFmpeg/FFprobe, RunLock, SceneMediaStore; no dependencies.

## Binding facts and decisions

Scope/spec: VCO-07-design.md; existing native-pixel algorithm scene_retained_rgb24_v1. User repeatedly authorized continuing until complete and resuming the failure point; this supplies the established implementation choice and opts out of additional design questions. No new viewing, epoch or source generation.

Actual resume77536/worker14976 exited1 at12:56:59+08; result media-resume-phase-d0dde8ef7c5a4e56a358b8c5ad0988e5/result.json says TimeoutError/media budget expired. Original source bytes unchanged/source POST3,upscale POST0,forbidden_calls[]. Extraction-e2ddf036773b4af884d0cf3becba3c41 already contains all219 PNGs. The21st per-image inspection exhausted frames.extract_video_frames's1200s deadline; executed commands returned0. Every PNG inspection emits multiple guarded process/log files; full guard costs roughly6.3s in this actual store versus4.375s for the isolated continuity proof. This is a new observed batch failure; prior native protection itself passed and is retained.

Alternatives: increasing deadlines violates frozen budgets; suppressing guards on actual writes violates closure guarantees. Retain strict checks but aggregate the newly captured inspection evidence. Original source bytes, old partial logs and orphan directory remain. Do not execute backup source.

## Task1: tests and producer

- [ ] Archive old runtime producer and snapshot failed state under original RunLock, without deleting files. Record old321 inventory and source readiness.
- [ ] Add tests/unit/test_scene_native_batch.py. RED missing batch API. Real tiny videos prove exact all-frame pixel equality and numeric sequence, wrong/reordered/last-frame-corrupt/extra/missing/alias/mid-validation mutation rejection, shared timeout exhaustion, unchanged segmented dispatch and no second extraction on explicit recovery.
- [ ] Add media/scene_native_batch.py with extract_native_scene_batch(..., reuse_existing=False, timeout=1200). Inspect full native video with existing inspect_video; fresh extraction uses exclusive numeric RGB24 FFmpeg command. Reuse requires owned exact directory, never invokes extraction. Capture all file identities, decode source, verify every PNG using existing verify_png under the SAME remaining deadline, compare every pixel, recheck source/images/numeric inventory, then save one aggregate record. Bounded<=320 frames, positive dimensions/count, no stale timeouts. Aggregate evidence records each file and decoded pixel SHA, actual checks and recovered/fresh provenance; it is not an invented per-image command log. Every actual logger write remains guarded.
- [ ] Modify runtime/production_scene_upscale.py _extract only: explicit whole_scene_v1 selects batch helper; default/segmented retain original helper. Optional exact recovery_directory allowed only for whole and expected owned extraction-<UUID> child, with source/target identity and full validation before the existing extraction-ready/promotion writers. Production pipeline's ordinary calls remain unchanged.
- [ ] Virtual budget test uses actual batch helper and219 rows,6.3s/write guards plus real loop accounting; prove all219 validated within unchanged1200s and mutation at final evidence guard still refuses. Keep old shared-budget control demonstrating current per-PNG logged inspection fails.
- [ ] Run focused batch/frames/whole-media/upscale recovery and native guard/transaction checks via bootstrap -B; read outputs. No full suite.

## Task2: review and exact-state recovery

- [ ] Fresh independent review of new batch producer and recovery only. Keep native lease implementation frozen. Fix Important/Critical once with RED/GREEN; retain minor ledger.
- [ ] Capture unchanged Engine05a; generate accurate new software inventory from df51, allowing only reviewed changes/new files. No source assessment rerun.
- [ ] Measure actual installed media store guard and check original180s frame transaction against measured cost before GPU. Isolated4.375s alone did not establish actual global guard cost. If budget control fails, diagnose actual duplicate work; do not relax180s.
- [ ] Explicit original writer recovers existing219 directory after full validation, then same run advances through remaining native batches/463 RealESRGAN frames/composition. Do not rerun original first-start or saved-input-only resume helper, whose zero-extra-file assertion is now stale.
- [ ] New final-film human playback/audio/subtitle response, independent publish and zero-new-work replay before VCO-07 completion.

## Preflight interfaces / ledger

Task1->Task2: returned Artifacts/evidence and existing extraction-ready schema unchanged. Full RGB24 correspondence is mandatory for recovered and new directories. Existing validate_extraction verifies the original native pixel algorithm again. No protection or ready cache is installed by batch evidence.

Ruling: project constraints override worktree/commit scripts; ledger stays here. User's repeated continue-until-complete instruction covers routine repair choices, so no additional permission gate. This repair changes logging granularity for new explicit whole batches, not source video generation, continuity algorithms, recipes or deadlines.

Task1 pending. Task2 pending. Current production worker exited1; no live GPU or frame intents. First action is immutable failed-state audit, then RED tests.

Task1 progress: failed audit e0ad30b6/23e4f19c exit0 preserves220 files/219 PNGs and original runtime producer backup8f6ee6fa. Initial new helper RED89826d29:10 missing-API failures; GREENdbeb2a6e:10 passed/4.92s. Wiring first REDd8b9e750 contained3 invalid fixture failures (missing store.paths), fixed fixture; valid REDd81e22c6:6 expected wiring/API failures,2 legacy successes. Added actual shared-budget control reproduces21-PNG exhaustion.

Ruling: correct overbroad verification scope. ed71236f/75688 included already-passed legacy200-frame chain and unrelated final-delivery recovery. Own pytest19156/start134378967254996831/exe verified then stopped; native-1, partial dots are NOT a passing suite. Stop evidence diagnostics/native-batch-broad-test-agent-stop.json. Do not rerun unrelated long legacy/delivery tests. Run new batch/deadline tests, frames, whole media, and directly relevant recovery case; preserve prior compatibility evidence.

Added optional verify_png remaining_timeout callback, default unchanged, so probe and RGB decode each receive fresh remaining batch time. Original media/scene_upscale.py bytes archived as8f6ee6fa/scene_upscale.py.bin, SHA9a300a1960a8bf4903bb4cd798ecc7b3ce8102cd7945bdb734130443f510cb82. Deadline RED2aec4eca:2 expected missing-API failures. This adds one reviewed media file; continuity Engine excludes it and must still be checked unchanged against05a before recovery.

Focused final GREEN6c657b5e469e45c49b54e880120b59ac/native92216 exit0:66 passed/16.31s, new batch21 + deadline2 + original frames/whole media cases. No GPU. Fresh read-only /root/native_batch_review dispatched once; pending. New profile-installed-media-guards.py prepared to measure actual installed store's continuity/execution/ownership/write/global costs, retain220 files/Engine05a/no network/no model submissions. Its measurements are separate from source ready proof and from production frame acceptance; do not repeat old isolated benchmark.

Fresh review returned With fixes: one Important, late external hardlink can appear after initial nlink1 check and survive _sequence/_again. Review report VCO-07-native-batch-review.md. Actual hardlink regressions tests/unit/test_scene_native_batch_review.py RED1b0f67d2:2 failures DID NOT RAISE, both last-PNG verification and final evidence guard. Fix pending: repeat nlink1 checks in each recheck before/after aggregate write. No second review of the same finding; verify RED/GREEN and focused suite once fixed.

Profile native37172/worker33484 is currently running with implementation frozen: log c2d7bb1bb29f40cdbeb8d33a8d3a1ab0, phase installed-media-guard-profile-26c2b8924fa3436d94d83fed919dc64e. Common13:21:12 confirms Engine05a unchanged; installed context/timings pending. No GPU/POST/production media writes; normal RunLock is held by this read-only audit. Do not stop for cold admission cost or run a duplicate profile. Apply alias fix only after this invocation exits, then68 focused tests; new software inventory and actual frame control still pending.

Review declined-judgment rulings: (1) synthetic219-row budget establishes call scaling only; actual batch acceptance remains required. (2) Actual180s frame feasibility must use installed guard measurements, not isolated4.375s. (3) Existing synchronous hash/guard APIs are cooperative; final refusal checks preserve deadlines without claiming preemptive realtime interruption. (4) Original writer's real219-orphan recovery remains a separate acceptance, not a test/viewing claim. (5)463frame/GPU/composition/audio/subtitle/human viewing/publish/replay remain required. (6) Complete software reconciliation and unchanged05a capture are executor gates before production. (7) Frozen unrelated diffs/old guard implementations/legacy long chains/full suite are not reapproved by this delta; prior evidence retained, full suite remains VCO-08. (8) Existing PNG checker hardening outside bounded native<=320 envelope is out of this repair; concrete late-alias finding is fixed, never waived.

Profile37172 exited0/c2d7bb1b, result13:40:21: context1089.5s,31224 source proof files,270 media Artifacts/6 directories,198 overlap. Measured source4.406/4.360s; execution1.812/1.781; owned1.797/1.781; actual writer6.094/6.110; captured6.640/6.750; global8.438/8.437. Original220 files/Engine05a unchanged; no GPU/POST/media writes. DO NOT rerun this original profile.

Final review fix applied ONLY after profile exited: owned_sequence() checks nlink1 initially and at both final rechecks. Late alias RED1b0f67d2 -> GREEN0c86b8a600fb451ca5de42e0ae9563e1:69 passed/17.45s, includes pre-existing-hardlink control. One fix pass, no deferred minors/no re-review of this same delta. Task1 software complete; real orphan recovery remains pending.

Task2 cannot proceed to GPU using isolated4.375s: measured installed writer6.110s/global8.438s expose duplicate execution/revision closure validation. Additional runtime-only coverage optimization is required and planned separately in VCO-07-media-proof-coverage-plan.md. Keep every required dependency in each write/send guard, prove exact coverage or retain strict fallback, never extend180s. Current no running profile or production, no active GPU. New inventory remains pending until coverage repair completes.
