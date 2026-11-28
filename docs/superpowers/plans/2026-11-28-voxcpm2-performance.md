# VoxCPM2 Performance Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans for this isolated experiment. Steps use checkbox syntax for tracking.

**Goal:** Complete TTS-VOX-09 with real, comparable GPU evidence and a conservative activation decision.

**Architecture:** An experiment invokes the existing locked official model and its public prompt-cache API; production behavior remains on the approved implementation. A pure summary function rejects incomplete or unequal comparisons.

**Tech Stack:** Python 3.12, locked VoxCPM2 / PyTorch CUDA, FFmpeg, pytest.

**Spec:** docs/task-designs/TTS-VOX-09-design.md

## Global Constraints

Use provided-reference-narration-v1; seed=42/cfg=2/steps=20, atempo=.95 once, 500ms silence top-up and whole-program -23dBFS RMS. Remove fixed spoken guide acoustically after tempo. No ASR, voice changes, package installation or production monitoring. Preserve unrelated dirty files. This experiment adds new files in the current v4 checkout because it consumes the approved, uncommitted production implementation; a HEAD-only worktree would test the wrong baseline.

## Review Focus

- Missing/duplicate or crossed pairs cannot produce performance approval.
- Cold generation and cache build cannot contaminate hot comparisons.
- Unequal PCM cannot be reported as quality-equivalent.
- Internal context must be removed from listening samples and reported body duration.
- Inference success is not subjective listening acceptance or a long-duration benchmark.

### Task 1: Reproducible experiment

**Files:** create scripts/experiments/voxcpm2_performance.py and tests/unit/test_voxcpm_performance.py.

**Interfaces:** summarize(rows, expected_pairs, cache_build_seconds) -> dict; rows contain round, case, variant, generation_seconds, raw_seconds, body_seconds, pcm_sha256, pipeline_seconds.

- [x] Write and run failing summary tests for weighted RTF, cold exclusion, incomplete/duplicate pairs, unequal PCM and round regression. Six expected failures observed.
- [x] Implement summary and experiment; run tests and CLI help. Six tests pass; CLI help exits 0.
- [x] Run dedicated CUDA experiment with two AB/BA rounds. Exit 0; 6 pairs plus cold persisted under `E:/VideoAI/scratch/benchmarks/TTS-VOX-09/20261128-222209-485528`.

### Task 2: Result and decision

**Files:** create docs/voxcpm2-performance.md and docs/research/TTS-VOX-09-result.json; update only 09 row/status in docs/voxcpm2-integration-design.md.

**Interfaces:** consume actual result.json, report real timings and decision.

- [x] Review experimental code and raw results, run relevant narration/summary tests. Independent read-only review found no important defect; 63 passed / 3 Windows symlink skipped using a fresh managed basetemp.
- [x] Record speed/quality gates, rejected/deferred paths and long-duration limitations; keep default unless both gates pass. Gain 2.31%, paired PCM equal, no comparative listening; retain production path.
- [x] Verify new files, task links and preserved production default; report outcome. Original default remains approved voice / 20 steps / .95 tempo / 500ms / -23dBFS; no implementation or production configuration mutation by 09.
