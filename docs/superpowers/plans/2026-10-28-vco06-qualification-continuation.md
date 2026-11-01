# VCO-06 qualification continuation implementation plan

> **For agentic workers:** Use superpowers:executing-plans inline, task by task, with test-driven-development. Preserve this checkout and its historical dirty work; .git is read-only. User explicitly requested continued execution, so do not insert a plan approval stop.

**Goal:** Reuse the delivered real research input, implement the specified qualification statistics, and produce byte-bound scientific readiness evidence before any natural candidate is authorized.

**Architecture:** Leave imported media, completed ordinary reports, the exploratory baseline and old r2 untouched. A separate pure statistics module consumes the existing feature schema. A read-only study audit validates the delivered context/baseline closure and records diagnostics and missing empirical prerequisites without producing thresholds, a profile or a candidate.

**Tech Stack:** Existing Python, NumPy and existing research readers; no installation, model request or publication for these CPU steps.

**Spec:** docs/task-designs/VCO-06-natural-input-design.md, sections4–7; input docs/task-handoffs/VCO-06-research-input-delivery.md.

## Global Constraints

- Source run 20261028-145342-f5100beeb167, all49 frames and independent reference; reuse saved complete evidence, no re-import/re-encode/rewrite.
- The paper sample is viewed development material; user feedback does not confirm an axis, a natural positive or full playback. Neither it nor the old24 sources can be new holdout.
- Development and fresh holdout each require at least12 videos/4 groups; a qualified direction requires4 natural positives in4 groups per split and valid actual observations.
- All five thresholds remain null until preregistered data, strict separation, seal and independent evaluation exist. No hand-authored profile, synthetic natural success or candidate rendering.
- Native16fps, complete PTS, current context, old four qualified directions/amplitude bounds, production_eligible=false.
- Per JSON16MiB, bounded live processing, 300s operation; all tests serial. Full suite deferred to VCO-08.
- No changes to frozen legacy source files or completed baseline implementation identities.

## Review Focus

- Frame/role/sample removal or reordering must not make a statistic look better.
- Frame/role means are equal-weighted rather than weighted by sample counts; off-axis is p90 per row then maximum, not a pooled mean.
- Negative frame-regression/temporal-increase values stay negative; no clamp.
- A descriptive user statement or a small diagnostic bias cannot create normal/anomaly/known-axis labels.
- Same-size/mtime data changes and copied/foreign baseline/report/assessment are rejected before any readiness result.

### Task1: Fixed statistics

Files: create src/video_ai/media/natural_repair_statistics.py and tests/unit/test_natural_repair_statistics.py.

Interfaces: natural_bias_statistics(frames, *, operation) -> dict; compare_natural_bias(before, after, *, operation) -> dict. Consume complete baseline frame rows and exact existing roles/coordinates/log2_ratios. Return b/o per frame-role, mean absolute bias, max absolute bias and the spec's signed comparison statistics; never fit a or grant qualification.

- [x] RED: independent numeric examples, p90, unequal sample counts, role order/support, nonfinite/bool/coverage and coordinate mismatch.
- [x] GREEN: deterministic bounded schema validation and statistics exactly as specified.
- [x] Verify focused unit file through bootstrap; preserve RED/GREEN logs.

### Task2: Qualification audit and protocol

Files: create src/video_ai/runtime/natural_qualification_audit.py, scripts/experiments/vco06_natural_qualification.py, tests/unit/test_natural_qualification_audit.py and docs/task-designs/VCO-06-natural-qualification-protocol.md.

Interface: audit_natural_qualification(delivery_path, *, timeout=300) -> dict. Validate research context and exact baseline/report/assessment/implementation identity; report all49 frames and four explicitly diagnostic operation projections. Report existing sample count and empirical gaps. Caller cannot pass labels/thresholds/qualification. CLI audit --delivery ABS --output ABS writes only a new independent output, never into the delivered input run/bundle, refuses overwrite and returns3 for awaiting_qualification.

- [x] RED: genuine fixture closure, drift/foreign baseline/current context/implementation mismatch, failed support and overwrite/source containment.
- [x] GREEN: reuse ResearchReader and formal context, exact identity checks, immutable external audit output and null qualification values.
- [x] Document all approved formulas, split/group/label requirements, seal-before-holdout and the exact missing empirical inputs. Distinguish a protocol definition from frozen full inputs; no fabricated frozen dataset.

### Task3: Actual continuation and review

- [x] Run new audit on exact delivered package; capture immutable output with full49-frame statistics and actual missing gates.
- [x] Run new tests plus relevant existing natural/material/report/production-boundary checks serially. No unnecessary heavy legacy rerun when existing production code is untouched.
- [x] Fresh read-only review; fix material findings with RED/GREEN, then record current results and source preservation.
- [x] Apply empirical gates: retain BLOCKED with actual evidence, no successor preparation.
- [ ] Actual independent dataset/labels, threshold calibration/seal/holdout/profile, natural candidate and actual improvement acceptance remain unavailable.

## Execution ledger

- 2026-10-28: User explicitly requested reuse of the delivered input and continuation of qualification/calibration/candidate/improvement. Re-read delivery and updated natural-route design; actual readonly CLI status exit0 in log vco06-resume-research-status-6bc56a6af41d4b0fa7bd76381e59ffbb.log. Existing49 frames/commit/epoch/assessment valid; current profile/operation/playback remain absent. Available tools do not provide actual full-video viewing. No new generation is useful before the independent observation/data gap can be resolved.
- Ruling: deliver all independently executable CPU/statistics/protocol work first, leaving empirical natural qualification and rendering gated. The single reused paper source is development only, with zero confirmed natural positive and zero fresh holdout; treating it as24 independent cases would invalidate the study. Cost if wrong: extra diagnostics without a usable profile; the audit makes that limit explicit and keeps existing admission disabled.
- Pre-flight: Task2 consumes Task1 statistics with the unchanged baseline frame schema; Task3 consumes Task2 byte-bound audit. No conflicting interface or legacy source edit required. Skills: writing-plans, executing-plans, test-driven-development; readonly .git and explicit full-suite deferral override worktree/commit/full-suite defaults.
- Statistics RED24 module-missing failures: vco06-natural-statistics-red-57aa0594528c415b95b8aeea36004173.log. GREEN24 new+4 existing=28: vco06-natural-statistics-green-136498de7670499297e5dc31a93f252c.log.
- Audit initial fixture import errors retained in vco06-qualification-audit-red-1f4eb76f86bd4068a6c56eca2f5c91ee.log; moved imports into test bodies, then17 expected missing-module failures in vco06-qualification-audit-red-tests-8c0fdcd71ce84147bba5667937483551.log. First GREEN attempt had3 fixture failures/42 passes because Windows text writing used CRLF while the real producer writes binary LF; fixed only the fixture serialization. GREEN45 in vco06-qualification-audit-green-lf-9e503801d51e40b7a048044003a00895.log.
- Additional read-window RED1: root report could change after pixel replay because nested report validation did not enroll all report/shard refs in the audit's own final rehash. Log vco06-qualification-window-red-0e23d24ddd5e4a8fae2edd34924af59c.log. Fixed full closure enrollment and deduplicated JSON charge; added shard guard. GREEN47 (43 new+4 existing), vco06-qualification-window-green-542fd0f3d4e5484186f19ec83bf25eab.log.
- Actual first replay: vco06-natural-qualification-real-audit-fd2e24f440d44a979b3d5e09b87b922b.log, exit3 as expected; all49 saved frames rederived from original pixels and exact baseline bytes matched. Artifact retained as qualification-audit.json under D:/VideoSi/projects/video-ai/vco06-natural-qualification/20261028-resume-245dea6b135b4cc19a7b8cb9077a206f. This precedes the final read-window fix; final rerun pending under a new name. No original evidence rewritten.
- Fresh scoped review: no Critical/Important/Minor findings; report docs/task-designs/VCO-06-qualification-continuation-review.md. Current131-case suite is running serially; actual final replay follows it. User interim progress remains every30minutes only.
- Final continuation: the131-case suite passed123.14s. Subsequent self-check found an output could land inside a delivered bundle if that bundle itself was under AUDIT_ROOT; RED1 log vco06-qualification-bundle-red-b5d7508f86544447ac4429ab12ebf069.log. Added explicit bundle exclusion before audit/write. Final132-case suite passed123.94s/exit0, log vco06-qualification-final-suite-3655b2fcfb6b463b82a47c5752f61e33.log. No other code changed after this final source.
- Final actual49-frame replay exit3/awaiting_qualification, log vco06-qualification-final-real-replay-b877874f2acb4572bff4b694c775148f.log. Result qualification-audit.final.json SHA cc02371430e35e6313b06acd8b874becdb37ebee232c22eb3cfb0b57f30adca6. All original baseline bytes matched; threshold/labels/qualification remain absent. Protected568 files and final451 Python files unchanged; r2 profile unchanged. An initialPowerShell checker accidentally nested the source array and falsely reported drift; retained that failed checker report, fixed enumeration, and verified against the unchanged original baseline.
- Refreshed the default blocker handoff and VCO-06 detail only; retained BLOCKED without a new state transition. Exact current outcome, commands and remaining empirical requirements: docs/task-handoffs/VCO-06-qualification-continuation-results.md. No new model/GPU request, actual publication, Git mutation, full-suite claim or successor preparation.
