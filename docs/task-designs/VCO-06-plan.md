# VCO-06 Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans for integration and a scoped implementer for Task 1; perform fresh code review before closeout. Steps use checkbox syntax.

**Goal:** Implement the approved, opt-in research color repair candidate workflow without changing production media.

**Architecture:** Pure constant RGB arithmetic consumes the independently verified sealed repair profile. Immutable local transactions bind ordinary pair measurements, the current continuity epoch and actual playback precheck; candidates, reviews and revision ancestry have separate records. Production import remains refused.

**Tech Stack:** Python 3.12, existing NumPy/OpenCV, CPU FFmpeg, existing RunLock and continuity/colorimetry APIs.

**Spec:** `docs/task-designs/VCO-06-design.md` (fully read at start).

## Global Constraints

- `research_candidate_v1`; `production_eligible=false`; no GPU, model POST, publishing, new dependencies, or calibration refitting.
- Native `16/1`, all retained frames, exact rational PTS and mapping; source/observation/accepted bytes unchanged.
- Sealed qualified directions only; single constant parameter; p99≤2, max≤4, no new clipping, no per-frame regression, strict aggregate improvement.
- JSON≤16MiB, metadata≤64MiB, frames≤4096, pixel work≤128MiB, RGB frame≤32MiB, operation≤300s, output preflight≤16GiB.
- `.git` is read-only; keep existing workspace and historical uncommitted work. Do not commit, create worktrees, reset, clean or push.
- All Python commands bootstrap first; tests and GPU work are serial. Full-suite regression remains deferred to VCO-08 per recorded user instruction.

## Review Focus

- Forged or stale evidence, including same size/mtime byte changes, cannot authorize a candidate or review.
- Recovery after any durable boundary retains partial outputs and never silently encodes twice.
- Failed playback submissions remain blocking even after a later passed submission or epoch change.
- Pair fitting consumes all reference frames, including frame zero, and never adjacent/prefix pairs.
- Candidate paths/records/receipts cannot become production sources through low-level APIs.

## Task 1: Pure numerical repair

**Files:** Create `src/video_ai/media/color_repair.py`, `tests/unit/test_color_repair.py`.

**Interfaces:** `estimate_constant_repair(reference,current,*,operation,context,profile)`, `apply_constant_repair(rgb,*,operation,amplitude)`, `score_repair_pairs(reference,current,repaired)` exactly as spec. No experiment imports.

- [x] RED: known arithmetic independent fixtures; sealed direction rejection, noop, insufficient/context support, per-frame regression and clipping.
- [x] GREEN: frozen sRGB arithmetic, deterministic fit, finite/bounded validation and single-thread restoration.
- [x] Verify targeted tests; record RED/GREEN commands and logs in `VCO-06-numeric-report.md`.

## Task 2: Records, profile closure and status

**Files:** Create `runtime/scene_color_repair_records.py`, focused private helpers if needed, unit tests.

**Interfaces:** Spec's request/profile/progress/production-origin functions; reuse strict Artifact/Reader and continuity schemas.

- [x] RED: precise request/context/precheck, genuine sealed closure, revision validation, read-only status, stale and sticky rejection.
- [x] GREEN: complete byte closure checks, current epoch binding and strict review semantics.
- [x] Verify records tests and Task 1 tests serially.

## Task 3: Local transactions and command interface

**Files:** Create `runtime/production_scene_color_repair.py`, `scripts/scene_color_repair.py`, helpers and integration tests; add origin guards in the four spec-listed runtime files.

**Interfaces:** Spec's propose/review result and CLI; ordinary colorimetry→pair audit→fit→stream encoding→readback/after audit→terminal→review.

- [x] RED: real CPU media flow, untouched source bytes, ordinary pair reference selection, interrupted recovery, command failures, zero POST and rejected production origin.
- [x] GREEN: locked immutable transactions and resource bounds, master/playback recipes, exact frame mapping, all closure and review checks.
- [x] Verify core and required compatibility commands; no full-suite run.

## Task 4: Outcome evidence and closeout

- [x] Inspect available real media/prechecks and actual playback capability; never fabricate viewing or matching evidence.
- [x] Fresh review of all changes; repair material findings with regression tests.
- [x] Write `VCO-06-verification.md` with commands, results and remaining acceptance by item.
- [x] Apply the completion gate: software evidence is delivered; natural acceptance is missing,so record BLOCKED and a concrete resume action without successor preparation.
- [ ] Complete actual natural candidate and full playback acceptance (design Acceptance3); this remains blocked by the audited input/precheck gap.

## Execution ledger

- 2026-10-27: User explicitly requested “完成任务VCO06”. Approved detailed design and entry handoff read in full. READY→IN_PROGRESS authorized; no new design decision requires approval. Existing `.git` read-only and local-workspace constraint overrides skill worktree/commit steps. Recorded user VCO-08 full-regression deferral overrides skill full-suite default. Plan and spec interfaces agree; numerical task feeds runtime, strict records feed writer/status; no conflicting interfaces found.
- Task 1: numerical implementation passed initial 56 tests plus calibration23. Fresh review found preflight allocation ordering, corrected by regression RED→GREEN; final numerical57/profile31/calibration23 =111 passed. Commands and logs: `VCO-06-numeric-report.md`, `VCO-06-profile-report.md`.
- Task 2: request/origin/status tests RED14→GREEN14; playback validator RED7→GREEN7. Profile fresh review found closeout byte rehash, calibration coverage and saved-bound consistency gaps; five regressions observed RED, then corrected without refit or new holdout measurement. Formal r2 reverified12,004 Artifacts with12,723,957 parsed metadata bytes and original four qualified directions,105.11s. No production eligibility granted.
- Task 3 in progress: real CPU tests exposed a path/Artifact bridge mismatch and then correct abstention for a still with no ordinary mapping coordinate. Fixed caller bridge and added source-bound selected-still reference mapping in the fixture, following existing ordinary reference protocol; geometry/fit thresholds unchanged. Runtime fresh review has four material saved-output/observation findings recorded in `VCO-06-runtime-review.md`, with regressions being added before fixes. Test outputs remain under D:/VideoSi; no real full playback is claimed.
- Final review: 15 expected RED failures reproduced missing measured/history/memory checks and the premature successful recovery terminal. Fixed retained original/history risk consumption, strict saved measurement bodies, bounded full-frame and PNG work, and prospective terminal validation. Additional resource RED2 reproduced unbudgeted larger references/output metadata; fixed preflight/metadata charging. Final unit157 and real positive+bad-recovery2 passed; remaining transaction/compatibility checks are running.
- Ruling: the new `intended-rgb` interruption occurs before master encoding, so its test must require retained intended RGB and absent master, unlike later colored checkpoints. Actual retained terminal is interrupted with exactly that boundary reason and source bytes preserved. The prior assertion inherited from master/later checkpoints was a test error, not a reason to create premature media. Only that assertion changed; rerun its exact case after the ongoing batch. Cost if wrong: the intended-RGB recovery behavior would lack a valid boundary test; the isolated rerun resolves it.
- Final boundary batch:23 passed/1 assertion failure in1910.55s. The isolated corrected intended-RGB case subsequently passed. Historical risk cases then correctly rejected a fixture's overwritten ROI; reuse the original frozen manifest/ROI for a new epoch, rather than changing evidence bytes. Cost if wrong: history semantics would not be exercised; rerun both real ordinary-report/history branches.
- Additional path review: a controlled real Windows junction test observed an archive write through a forbidden target alias before the late Artifact check (RED1). Move canonical target/temporary checks before mkdir/open; run the junction regression and a fresh positive media flow. This changes only the repair archive preflight,not frozen calibration files,ordinary algorithms or legacy source guards.
- Closeout ledger: archive alias RED log `vco06-archive-alias-red-0e675398ce6a4eb39eb8f61f46d81438.log`; target/temporary preflight fixed. Current unit collection **159 passed,22.97s**,log `vco06-closeout-unit-01dc75ce6ffb43c1b4f5281cd777e4ff.log`. Current-source real candidate,invalid recovered fit and both color/non-color historical cases **4 passed,459.51s**,exit0; log `vco06-closeout-current-flows-b009e405ffc24289b2af8c8d46ffa167.log`. The exact six legacy files remain in the active serial command,178 collected; log `vco06-final-compat-7ffbc141c43842f99f13f5020f2e8822.log`.
- Latest authoritative source snapshot: `D:/VideoSi/cache/video-ai/logs/vco06-final-scope-2d065b5de93840d7b91f71254e78d2cb.json`,captured after archive/history fixes. Earlier snapshots are historical. Verify it after checks with `D:/VideoSi/cache/video-ai/temp/vco06_scope_identity.py verify PATH`; original run closeout checker is `D:/VideoSi/cache/video-ai/temp/vco06_original_inventory_closeout.py`.
- Actual natural-input work: user delegated sample selection; selected accepted native egret `scene_0003_clip_0001` and audited all3 actual user-accepted first clips. Exact native/source color checks passed and original3011 files matched,but all selected PNG originals lack sRGB/gamma/ICC declarations. Real VCO-02 gate on a byte-identical canonical PNG copy returned unknown/unverified/pixels=null. Source record:`docs/task-handoffs/VCO-06-real-input-audit.md`. No natural candidate/precheck/new actual playback can be registered from this input. Final task disposition must preserve that unverified acceptance,not declare completion from fixtures.
- Entry handoff preserved before replacement: `D:/VideoSi/cache/video-ai/logs/vco06-entry-handoff-62b39579eff143e0840650ada64dc3fb.md`,6737 bytes,SHA256 `357d35941e49b7d5cb4fc36ca20d1a908d3af78045538bc0e21a1c7b371a7f3e`; original/archive byte hashes matched.
- User progress preference updated during closeout: “每隔半小时汇报一次进度，不要汇报中间过程，只汇报进度即可”. Subsequent interim reports follow that interval and contain progress only.
- 2026-10-28 final closeout: required exact six compatibility files **178 passed,5755.44s**,exit0,no skips; log `vco06-final-compat-7ffbc141c43842f99f13f5020f2e8822.log`. All186 distinct focused cases and178 legacy cases now have passing evidence across the documented serial commands/corrected reruns. Expanded transaction results predate the final two-line archive target/temporary preflight; final159 unit+4 CPU/history+178 compatibility checks use the frozen final source. After tests,433/433 Python files matched the authoritative snapshot; original3011/3011 file set,bytes,SHA and mtime_ns matched with no extras/missing files. Preservation result `D:/VideoSi/cache/video-ai/logs/vco06-original-closeout-61627cd9e494438fa9ff309d890f5232.json`; `git diff --check` exit0. No full suite,model/GPU request,actual production publication or Git mutation. Re-read the board's current IN_PROGRESS row and complete VCO-06 design; write the pause handoff before recording IN_PROGRESS→BLOCKED for missing natural input/precheck/playback acceptance. No successor preparation.
- Transition committed: wrote the required pause handoff at the retained exact path,then changed only the VCO-06 row and matching detail to BLOCKED. Verified handoff title/heading order and board status; final documentation diff check exit0. No test command or orchestration cell remains running.
