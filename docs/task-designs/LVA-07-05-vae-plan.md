# LVA-07-05 VAE Repair Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans inline with focused RED/GREEN and one final scoped reviewer.

**Goal:** Remove unused CUDApool/CPUoffload overlap and fail image preparation before expensive pair.
**Architecture:** Local VAE memory scope and same-worker text+image cache; unchanged node schema/math.
**Tech Stack:** Existing Python/Comfy/PyTorch, no install.
**Spec:** docs/task-designs/LVA-07-05-vae-design.md

## Global Constraints
Originalmodels/fp32/768x432/93frames/16fps/prompts/seeds;12GiB private24RSS20allocator; originalUUID and human gate; no newpair before combinedprep.

## Review Focus
Exact perinstance restoration and CPUdevice handling; no global/perframe patch; failed preparation cannot publish readiness; VAE and condition cache sameepoch; nativeDecode schema/lock and preserved numerical outputs.

### Task1: Scoped lifecycle and prepared image
- [x] RED tests in tests/unit/test_wan_wrapper_vae.py and integration worker for pool-overlap behavior, exception restore, sameepoch image gating and no late encoding.
- [x] Implement wan_wrapper_vae.py; update context prepare/cache/claim, native decode registry subclass and client receipt validation.
- [x] Run focused+affected Wrapper suite GREEN; one scoped review/fix pass; archive and deliver only task files.

### Task2: Operational continuation
- [x] New -03 comparison/source/auth; owned worker and combined prepare-text once, originalGET only.
- [ ] Combined prepare passes before fresh pair; control then actual humanacceptance beforefast.
- [ ] Record all terminal outcomes/resource/exit; do not equate preparations or pair with quality.
