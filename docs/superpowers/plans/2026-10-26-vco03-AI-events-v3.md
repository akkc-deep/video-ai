# VCO-03 AI Event Experiment v3 Implementation Plan

> Use superpowers:executing-plans inline. Spec: docs/task-designs/VCO-03-AI-events-v3.md.

Goal: Separate declared join events from unrelated frame peaks and bound tiny-noise inflation in an experimental scorer.

Architecture: A pure read-only scorer in scripts/experiments/vco03_event_scores.py consumes verified trajectories and declared control joins. Runtime orchestration reuses calibration-only inputs and original producer evidence; no production module changes.

Global constraints: D:/VideoSi runtime outputs; .git read-only; preserve prior dirty workspace; no GPU, paid inference, full suite, ordinary profile or VCO-04; per-command265s. No old check per-case access or refitting.

- [x] Inspect calibration-only trajectory and score evidence; identify absent join support and tiny-MAD inflation.
- [x] Write tests in tests/unit/test_vco03_event_scores.py; run expected RED; implement pure event scorer; run GREEN.
- [x] Validate and freeze calibration evidence, labels, parameters and implementation identities; derive event rows and fit once. Preserve nulls and unsupported joins.
- [x] Complete bounded unused-source eligibility search. Only measure a truly new source after labels/queue and threshold seal are frozen; otherwise explicitly report no new independent check.
- [x] Run a fresh read-only whole-change review and address material findings; verify original artifacts and production identities; save results and update current entry.

Review focus: missing support must never become normal/zero; declared events and intervals must filter evidence; no recipe/truth/source-index leakage; dt/work-grid dimensions and finite-value validation; old checks stay sealed; source/probe original receipt and nested identity closure.

Ruling: user has repeatedly requested autonomous progress and AI-only review. Continue without another design-confirmation round. A numeric motion threshold is not a completion requirement; absence of measurable joins is an outcome to preserve.

Execution verified:20 pure scorer tests +6 producer/probe guards=26passed. Initial freeze rejected before fit; r1 binds the real measured plans and original producer proof. One fit only, no old/new check used. All frozen evidence and derived rows verified.

Ruling: no eligible fresh native-color source after bounded search; deliver calibration-only evidence and explicit not-run check instead of reusing the sealed Scott check. This costs new independent accuracy evidence, which remains absent.
