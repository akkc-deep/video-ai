# LVA-07-05 T5 Repair Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans inline, focused RED/GREEN tests and one scoped final review.

**Goal:** Fix T5 memory overlap and preserve original664-token context before resuming video.
**Architecture:** Same-worker durable prepare-text phase and exact in-process tensor cache, T5 cleanup before pair/VAE, contract-driven12GiB private cap and per-call padding length.
**Tech Stack:** Existing Python/Comfy/PyTorch/safetensors, no new dependencies.
**Spec:** docs/task-designs/LVA-07-05-text-design.md

## Global Constraints

Original six assets/content/seeds/frame budget and human gate; one owner, RSS24GiB/allocator20GiB; GPU durationunlimited, CPU bound unchanged. Failed oldIDs terminal; no repeat POST on unknown.

## Review Focus

Cache bound to original prompt/profile/epoch; no late T5 with pair; native encoder finally cleanup; correct positive664/negative512 contexts including positional call; post-text4GiB/20GiB workspace phase gate while initial14/21 stays; one protected model hash window and original-ID recovery; contract-driven12GiB not unbounded.

### Task1: Implement tested text phase

- [x] Add focused failing tests for validation/context/encoding lifecycle/protocol and cap.
- [x] Implement helper, context/cache/lease pipeline, transport/route and sealed settings/cap.
- [x] Run focused+affected Wrapper tests GREEN; independent scoped review; fix important findings once with RED/GREEN.
- [x] Deliver only task files and record design/source amendment.

### Task2: Actual text-first repair execution

- [x] Seal new20261120-02 root and bind existing continued user authorization.
- [x] Start owned GPU worker, prepare-text exactly once, GET original ID if needed; validate actual664/512 before any full pair repeat.
- [ ] If successful, admit pair in same lease window, then one control and actual human review; fast only after acceptance.
- [ ] Record actual results, failures, stage/resource boundaries and owned exit; task completion only if accepted outcome.
