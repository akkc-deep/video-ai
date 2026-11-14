# Cold Admission Performance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans inline. Steps use checkbox syntax.

**Goal:** Remove hours of repeated source preparation and resume the original Voyager2 task.

**Architecture:** Separate trusted dependency replay from physical verification. Deduplicate native files/ancestor directories within bounded read passes, retain fresh boundary checks, and bind semantic reuse to exact effective source scopes. Measure the complete cold path rather than only warm review receipt handling.

**Tech Stack:** Python 3.12, existing Windows native leases, pytest; no dependencies.

**Spec:** `docs/superpowers/specs/2026-11-15-cold-admission-performance-design.md`

## Global Constraints

- Preserve current dirty checkout and saved baseline; no reset, unrelated commits, media mutation or fabricated acceptance.
- Preserve failed-observation immutability, exact raw receipts, parent admission and unknown-task GET-only recovery.
- Production exited130 at a read boundary; retain old owner/intent evidence. Resume only after the measured optimization.
- User delegated implementation choices and inline execution previously; continue without an additional approval round.
- Do not run a full unrelated suite or add generation-time audit loops.

## Review Focus

- Captured dependencies must propagate completely through nested/shared ancestors.
- Same-stat edits/replacement, new/missing files and source-scope tightening remain refusals.
- Directory reparse changes, including lazy scanners, retain strict checks at the correct boundary.
- Copied contexts, foreign threads, writer promotion and closed windows cannot reuse checks.
- Cold guards can grow; new dependencies must never inherit a stale verified marker.

### Task 1: Remove duplicate observation and physical replay

**Files:** `_continuity_byte_guard.py`, `scene_revision_records.py`, `_protected_continuity_inputs.py`, `verification.py`; new `tests/unit/test_cold_admission_performance.py`.

**Interfaces:** `replay_guard(guard: ByteGuard) -> None` merges existing immutable rows into active captures with existing limits/conflict rules. `_NativeInput.verify(path)` may return its checked stat for internal reuse. `_Protection.verify()` validates unique parent directories before/after unique entries and returns the exact native entries it checked.

- [ ] Write RED tests: one observe per stable_bytes read; replay does not call `_safe`/stat; replay preserves complete rows/conflicts/capacity; overlapping window/native entries checked once; shared parent checks scale by unique directories.
- [ ] Run the focused new cases and confirm expected failures.
- [ ] Remove duplicate stable_bytes observation, implement pure replay and bulk native exit verification, retaining strict public observe/scanner paths.
- [ ] Run new tests plus affected byte/protected-input cases.

### Task 2: Bound and deduplicate full read preparation

**Files:** existing read transaction/protection code, source scope helpers, reference memo keys and progress read entrypoints.

**Interfaces:** `protected_read_pass(*, fresh=False)` is a synchronous, same-thread/live-window physical proof period. Effective source-scope fingerprint includes exact image required IDs and clip required/known IDs. No pass spans a persistence/network boundary.

- [ ] Add RED cases for nested captures sharing physical dependencies, growing guard dependencies, exact image/clip scope changes, pass closure/thread/writer invalidation, and fresh mutation detection.
- [ ] Integrate the pass with read transactions and fresh boundaries; separate capture propagation from physical work so a new capture does not trigger a complete ancestor traversal.
- [ ] Correct semantic scope keys. Share pure immutable source values only where the exact input/scope proof permits it; do not cache mutable stores/progress across writes.
- [ ] Cover complete progress/preflight scans with bounded read windows. Measure again before adding further caches; record any residual-hotspot decision here.
- [ ] Run the relevant guard, source-revision, review and recovery regressions, including real Windows reparse cases.

### Task 3: Prove complete cold-path improvement and resume

**Files:** `scripts/benchmark_cold_admission.py`, focused cold fixture, report under `docs/handoffs`, task-local resume entry if needed.

- [ ] Build a fresh-process benchmark from load_frozen_inputs through load_prepared_inputs, context/progress and exit cleanup; include shared ancestry and multiple clips/scopes, with actual native protection and no inference.
- [ ] Compare saved baseline/current sources with the same protection mode, elapsed stages and unique proof/rebuild counts. Include incomplete/cancelled status explicitly.
- [ ] Run one bounded read-only preparation probe against the existing Voyager run. If incomplete or still dominated by repeated work, profile that phase and finish the remaining fix rather than declaring success from the small fixture.
- [ ] Obtain one fresh-context review of the complete optimization, correct important findings, run the focused affected checks and diff check.
- [ ] Resume the original revision10 task with preserved intents and observe actual stage progression; keep the full video objective active until delivery.

## Execution ledger

- Baseline saved: `.tools/cold-admission-optimization-baseline-20261115-011834`, 644 source/test/script files, exact SHA manifest.
- Producer11572/session31241 cooperatively exited130. No service/inference was active and native owner is absent. Original media, lock history and task IDs retained.
- Read-only parallel investigations confirm ordinary Wan reference admission dominates; temporal/native-video secondary issues are not the measured root and will not become an unrelated project.
- Ruling: work inline in the existing checkout, honoring the prior delegated workflow and snapshot pattern; do not create a divergent worktree lacking the current user changes.
