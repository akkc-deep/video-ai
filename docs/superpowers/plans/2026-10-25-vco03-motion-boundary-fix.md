# VCO-03 Motion Boundary Correction Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans inline. Preserve the existing workspace and its uncommitted implementation; .git is read-only.

**Goal:** Remove clip anchor relocation from measured motion and explain or resolve the observed camera-jump abstention without weakening matching support.

**Architecture:** Use the measured region affine to derive pair-local center displacement. Keep the declared right anchor for identity, sampling, and subsequent clip tracking. Investigate background correspondence independently with the existing fixed matcher and retain explicit abstention when support is insufficient.

**Tech Stack:** Existing Python / NumPy 2.2.6 / OpenCV headless 4.12.0.88 CPU.

**Spec:** `docs/task-designs/VCO-03-design.md`, sections 4–6: motion uses subject affine and actual dt; missing background cannot imply a stationary camera. Evidence: `D:/VideoSi/projects/video-ai/continuity-benchmark/background-roi-experiment-20261025/boundary-investigation.json`.

## Global Constraints

- Preserve sources, original 200 controls, accepted ROI, existing diagnostic audits and software snapshot.
- No default quality thresholds, fitting, holdout, model inference, dependencies, GPU, git mutations or VCO-04.
- Each command <=300 seconds; run the design's five targeted files, not full regression deferred to VCO-08.
- Different implementation bytes invalidate old dependency fingerprints; save a new software snapshot and isolated diagnostic outputs.
- User's “继续处理吧” authorizes the just-proposed correction and investigation; continue without another approval round.

## Review Focus

- A changed clip anchor must not generate motion on identical pixels.
- Real image translation must survive an imperfect anchor; camera compensation remains separate.
- Failed subject matching must not create a velocity merely because an anchor exists.
- Existing matching gates, padding and original color metrics remain intact.
- New diagnostic results must not overwrite or misrepresent old implementations or formal acceptance.

### Task 1: Correct pair motion

**Files:** `src/video_ai/media/continuity_analysis.py`, `tests/unit/test_continuity_analysis.py`.

- [x] Add real-image regressions: stationary two-clip sequence with a shifted second anchor has near-zero velocities and no boundary spike; translated pixels with an imperfect anchor retain the measured translation and compensation.
- [x] Run regressions and retain intended RED failures.
- [x] Derive current pair's motion center from the subject affine applied to the left box, while keeping right anchor in the sample's box/center for next-clip tracking. Leave failed matching null.
- [x] Run regressions and complete unit file GREEN.

### Task 2: Investigate background support

**Files:** isolated scripts and evidence under `D:/VideoSi`.

- [x] Reproduce stage counts: original background 10 passing points, right sofa 2, below unchanged minimum 12.
- [x] Probe a statically chosen wider window/background region that remains in frame under the jump; propagate from the first frame with existing matcher and clip-start anchors only.
- [x] If support remains insufficient, record the limitation and exact cause; do not weaken gates or substitute recipe motion as a measurement.

### Task 3: Recompute and verify

- [x] Recompute unchanged / motion_reset / camera_jump on the same calibration source and same AI background proposal in a new directory.
- [x] Compare original color metrics and control RGB identities, before/after velocities and scores; retain the real missing-score reason.
- [x] Run five targeted test files; obtain one fresh read-only implementation review and address material findings with RED/GREEN.
- [x] Save report, new implementation identities, command logs and current limitations; formal task remains BLOCKED.

## Execution Ledger

Pre-flight: Task 1 changes only trajectories/detectors; Task 2 must not silently change matcher parameters; Task 3 uses the same source/recipe/region input as the old experiment.

Ruling: correct the existing specified affine-motion computation, without changing v1 matching constants or schema. Any alternate matcher would be a separately versioned algorithm, beyond this bounded fix.

Ruling: retain the established in-place workspace because .git is read-only and recreating a checkout would omit the delivered untracked implementation. No commits or worktree creation.

Ruling: the original native-interval/independent-review/calibration gates remain; AI support experiments cannot satisfy them.

Task 1 complete: 2 intended RED failures; full analysis unit GREEN26; same-input real boundary scores match isolated sensitivity prediction.
Task 2 complete: wider window alone had11 accepted vectors/3 global cells; finite static canopy/lower-sofa probe found canopy adds2 vectors/one new cell; lower sofa failed and was retained. Adopted window+canopy only in independent AI diagnostic plans, not formal ROI.
Task 3 complete: six new full-case runs, all RGB identities preserved, per-region comparison verification, fresh review without material findings, final bounded five-file suite108. First combined325.54s exceeded budget; retained and superseded for budget verification by five hard-bounded runs.
Ruling: camera-support counts use distinct timestamps with any valid background estimate. Per-region scores keep local tracking failure, so the original background remains null while the new regions provide measured jump scores.
