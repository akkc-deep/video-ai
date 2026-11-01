# VCO-03 Calibration Compatibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox syntax for tracking.

**Goal:** Replay the user's accepted local targets and preserve reliable nonuniform native timing through existing calibration.

**Architecture:** Optional source control_targets bind region subsets and authorization identities into the existing corpus digest. A shared source timing validator uses verified probe boundaries; calibration and profile consumers retain observed rational time steps.

**Tech Stack:** Existing Python 3.12 / NumPy / OpenCV CPU, unchanged dependencies.

**Spec:** docs/task-designs/VCO-03-design.md, compatibility amendment dated 2026-10-25.

## Global Constraints

- Continue VCO-03 in the existing authorized dirty workspace; .git is read-only, no worktree, commit, branch or overwrite of prior work.
- Keep source files, old audits, accepted review videos, parameters, production CLI and VCO-02 schemas unchanged.
- Real fitting/holdout remains gated by 24 sources, frozen lineage/split and two genuine independent human labels.
- Run only the five targeted files from the design, through bootstrap; each command <=300 seconds. No full suite before VCO-08.
- Do not infer labels or viewing evidence from acceptance of effect placement.

## Review Focus

- Catalog changes must invalidate old label bindings.
- Unknown/background/empty/duplicate target IDs must be rejected before generating pixels.
- No inferred last-frame time or missing original frame may satisfy interval coverage.
- Profile reconstruction must apply the same selectors and observed rational time steps.
- Accepted material must be compared by reconstructed native RGB, without rewriting it.

### Task 1: Bind and replay targets

**Files:** continuity_calibration.py, _continuity_controls.py, test_continuity_calibration.py, test_continuity_analysis_flow.py.

- [x] RED: pure schema/corpus-binding tests and real two-subject local-control pixel tests; retain actual calibration/profile-evidence integration.
- [x] GREEN: optional exact control_targets validation, shared recipe selection, authorization checking and scoped context; replay in profile verifier.
- [x] Verify default controls remain unchanged and altered selectors require new corpus binding.

### Task 2: Native time coverage

**Files:** continuity_calibration.py, continuity_analysis.py, test_continuity_calibration.py, test_continuity_analysis_flow.py.

- [x] RED: unequal PTS steps, contiguous indices, exact next-frame/end-of-file boundary and observed step coverage; real VFR CPU fixture in calibration integration.
- [x] GREEN: verify native frame coverage against sidecar instead of enforcing constant deltas; use observed step reciprocals in calibration/profile/application.
- [x] Run all five targeted test files; inspect every failure and record command/exit/log.

### Task 3: Existing-data verification and remaining preparation

- [x] Reconstruct all frames of the two accepted people03 cases through the production constructor; compare existing hashes, selectors and scoped context.
- [x] Validate all 20 selected sources' exact native intervals, including frog, without fitting or holdout measurement.
- [x] Finish finite licensed source attempts; prepare any successful complete downloads and consolidate genuinely human-dependent material.
- [x] Record changed software identities, preparation counts, failures and remaining gates; leave task state truthful.

## Execution ledger

Pre-flight: source selectors feed construction and profile recipe checks; timing feeds calibration applicability and ordinary profile matching. Both interfaces must change together. Existing parameters and source evidence remain authoritative.

Ruling: preserve and edit the current workspace in place — the user requested continuation/reuse and .git is explicitly read-only; creating another checkout would omit the uncommitted delivered implementation.

Ruling: use the design's five-file verification command — the explicit task contract defers full regression to VCO-08 and overrides generic skill advice to run the whole repository.

Ruling: no further design choice is requested — the user already selected the targets and requested autonomous continuation; this amendment makes that accepted behavior reproducible without new detector behavior.

RED: 5 intended failures, log vco03-compatibility-red-05b40d398b8f4220ba3c5aaf9ce480ec.log. GREEN: 6 passed including VFR fixture calibration and profile reconstruction, log vco03-compatibility-green-bb65fda220cf45a396d9a561bd784727.log. First five-file regression: 106 passed, 273.61s, log vco03-compatibility-targeted-94d5cc15bba24bc297a64dea37b6d489.log. Source-boundary hardening still pending below; this is not the final verification.

Final review: independent read-only reviewer found one Important source-boundary issue. Entered one TDD fix pass: an edited/refrozen display map or region role must be checked against original source records and regions. No second review is needed; the regression and final five-file run will verify the fix.

Final: minor (deferred): ordinary profile applicability considers all native time steps in the media sidecar, so timing outside the selected interval may conservatively prevent application. Retained the conservative policy; no unobserved time step gains profile coverage.

Final: Ruling: reviewer left real-data verification and test execution to the primary agent — run explicit source/RGB verification and the five-file command, and retain absent human labels/fitting as blockers. Cost if wrong: accepted material could be mismatched despite software tests, so no formal calibration is allowed before these checks.

Final: fixed source-evidence reconstruction — refrozen timing/region role regression RED (1 failed) → GREEN (1 passed), final five-file suite 106/106. Log: D:/VideoSi/cache/video-ai/logs/vco03-compatibility-final-targeted-458c8400d9774061a402c853099cf89c.log.

Task work verified: all20 native intervals, all1000 people03 control frames, sealed artifacts unchanged. Missing4 sources and genuine human/split inputs remain; no task-completion transition. Git mutations unavailable, so the existing workspace and ledger remain in place.
