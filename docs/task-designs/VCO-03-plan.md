# VCO-03 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox syntax for tracking.

**Goal:** Implement the approved read-only CPU continuity analyzer and calibration tooling without changing production behavior.

**Architecture:** A read-only evidence context verifies VCO-02 files once per unique path and checks them again on exit. A bounded measurement core separates registration, color and trajectory measurements from audit persistence and calibrated decisions. Calibration alone constructs recorded experimental controls and isolates holdout data from threshold fitting.

**Tech Stack:** Python 3.12, optional NumPy 2.2.6 and OpenCV headless 4.12.0.88, existing FFmpeg evidence.

**Spec:** docs/task-designs/VCO-03-design.md

## Global Constraints

- Source media, source audits, production CLI and old VCO-02 schemas remain unchanged.
- No default quality thresholds, invented labels, playback claims, GPU inference or network media acquisition.
- Only explicitly supplied local paths; exact JSON schemas and SHA identities; exclusive outputs in a new audit.
- Resource limits and parameters are the exact v1 dictionary in the design; optional dependencies import only on diagnostic use.
- Run only the five targeted test files in the design. Full regression remains deferred to VCO-08.
- Real completion requires 24 independent sources, 240 cases, actual dual human annotations and all six ready detector profiles.

## Review Focus

- Forged successful-looking raw/command evidence must be rejected by read-only loading.
- Context must suppress only its explicitly selected frame, region and detector.
- Geometric loss and missing history must abstain without fabricated colors or semantic claims.
- Source PTS and experimental display time must stay separate; truth cannot enter measurement.
- Holdout must never enter threshold fitting; abstentions must remain visible in evaluation.

### Task 1: Read-only color evidence

**Files:** colorimetry.py; tests/unit/test_colorimetry.py.
**Interfaces:** load_color_analysis_set(record_paths, *, config, timeout=300) -> ColorAnalysisReader with frames, sidecars, identities, read_rgb and context-exit verification.

- [x] Write and run failing tests for missing reader, read-only behavior, forged records and same-stat drift.
- [x] Extract reusable validation from the existing sidecar loader; implement bounded deduplicated identity handling without a source RunLogger.
- [x] Run colorimetry unit and integration checks, preserving old behavior.

### Task 2: Measurement and report

**Files:** continuity_analysis.py and focused internal helpers as needed; tests/continuity_helpers.py; tests/unit/test_continuity_analysis.py.
**Interfaces:** validate_continuity_manifest(manifest), measure_continuity(plan, frame_provider, *, deadline=None), analyze_continuity(manifest, *, config, paths, logger, timeout=300).

- [x] Add failing tests for strict schemas, independent color formulas, normalized affine geometry, conservative matching, time/ROI/context and six scores.
- [x] Install the pinned optional extra using bootstrap; retain base dependencies=[].
- [x] Implement bounded frame access, deterministic IRLS/LK, exact color sampling and trajectories with explicit abstentions.
- [x] Add dependency/input freezing, profile validation, evidence PNG/pairs/metrics and exclusive report persistence.
- [x] Run measurement tests and verify thread restoration and resource rejection; no parent-environment mutation is introduced.

### Task 3: Calibration and controls

**Files:** continuity_calibration.py; tests/unit/test_continuity_calibration.py.
**Interfaces:** build_annotation_template(catalog), validate_calibration_catalog(catalog, labels=None), build_control_case(source, variant, *, reader, truth), calibrate_continuity(catalog, labels, *, config, paths, logger, timeout=600).

- [x] Write failing tests for catalog/labels/split leakage, control time and truth isolation, strict midpoint fitting, ties, abstention/Wilson metrics and disabled profiles.
- [x] Implement ten deterministic controls, unverified annotation templates and strict catalog/labels validation.
- [x] Implement calibration-only fitting, exclusive threshold freeze, one holdout evaluation and domain-bound profiles.
- [x] Run calibration tests; keep fixture_only results distinct from real acceptance.

### Task 4: CLI, integration and closeout

**Files:** scripts/continuity_audit.py; tests/integration/test_continuity_analysis_flow.py; VCO-03-verification.md; task board.

- [x] Implement four explicit offline commands with exit codes 0/2/3/124; relative-path refusal is exercised through the actual CLI entry point.
- [x] Run real small CPU FFmpeg -> colorimetry -> read-only reader -> independent audit integration and compare original identities.
- [x] Run the design's five-file targeted command, obtain one independent code/spec review and address material findings with regression tests.
- [x] Record exact commands/results and real calibration gaps; do not mark COMPLETED because real outcome-level acceptance remains unestablished.

## Execution ledger

- 2026-10-24: Explicit user request “VCO-03 完成任务”; full design and handoff consumed. READY -> IN_PROGRESS authorized.
- Ruling: execute in the existing workspace because .git is read-only and VCO-02 is uncommitted; no git metadata writes or commits. Risk: changes share the user's working tree; preserve all prior edits.
- Ruling: use native implementation with one final independent reviewer; the approved design fixes interfaces and algorithm. No repeated design or execution approval is needed for the explicit completion request.
- Pre-flight: reader -> analyzer uses ordered frame metadata and lazy bytes; analyzer -> calibration uses ResolvedPlan/FrameProvider and raw detector scores; CLI -> both uses exact public signatures. No interface conflict identified.
- Real catalog/labels requested asynchronously; no material has yet been supplied. Software implementation can proceed independently; real calibration cannot be fabricated.
- Implementation is present for all four plan components. Read-only reader RED7 -> GREEN39; initial analyzer/calibration RED -> GREEN15; original CPU flow3 passed; all ten controls passed; 20 fixture-only cases sealed before holdout and remained unverified. See VCO-03-verification.md for exact logs.
- Final independent review: eight Important findings; three Minor findings regraded Important by their effects on explicit evidence/reproducibility requirements. One remaining minor deferred: distinct-record same-source uniform-frame shortcut can conservatively abstain.
- Fix pass: future-anchor/fps/join/profile regressions RED4; original JSON bound RED1; mask truth boundary RED1; lineage RED1; numeric digest/RECORD RED2. Final unit GREEN66 after correcting `.log` JSON accounting. Full design-targeted check is running; no full-suite invocation.
- Final: five-file targeted command 101 passed in 252.66s, exit 0; 16/16 source/test/script/pyproject size/mtime/SHA unchanged; git diff --check passed. Exact final log is recorded in VCO-03-verification.md. No full-suite run, true human benchmark, GPU inference, production integration or successor preparation occurred.
- Task 1: software complete (reader and legacy VCO-02 regressions green).
- Task 2: software complete (formulas, geometry, context, timeline, resource and profile rejection regressions green).
- Task 3: tooling complete (ten controls, sealed fitting, fixture-only holdout and evidence-consumer smoke green); actual 24-source human benchmark remains unverified.
- Task 4: software verification and blocker handoff complete; VCO-03 overall is BLOCKED pending actual corpus/labels, not COMPLETED.
