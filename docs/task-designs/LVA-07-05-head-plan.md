# LVA-07-05 Head Adapter Implementation Plan

> **For agentic workers:** Execute inline with superpowers:executing-plans and one scoped final review.

**Goal:** Resolve dynamic-head installation without touching fixed upstream code.
**Architecture:** Exact full-delta validation and direct CustomLinear buffer installation, then scoped sampler-reload interception. No per-forward work.
**Tech Stack:** Python, fixed CustomLinear, existing CPU-only fixture runner and pytest.
**Spec:** docs/task-designs/LVA-07-05-head-design.md

## Global Constraints

Original six models, policy counts1500/1459/290, private-static protection, existing control and video budget retained; no downloads/install/production changes.

## Review Focus

Head scale exactly once with runtime rounding; installed head survives upstream removal/reload; invalid entries fail before any static write; scoped function always restores; control has no head adapter effects.

### Task1: Implement and prove adapter

- [x] Add failing tiny real-CustomLinear head forward and sampler reload/exception tests.
- [x] Implement exact head preflight/direct installation and sampling scope.
- [x] Run focused CPU/Wrapper tests GREEN, record results; scoped final review.
- [x] Deliver only task files to source root; document source/authorization amendment.

### Task2: Resume actual experiment

- [x] Once CPU implementation blocker resolved, record BLOCKED->READY->IN_PROGRESS and actual capacity.
- [x] Seal new20261120-01 root; authorize by actual continued user messages; one owned unlimited GPU worker and original-ID pair admission.
- [ ] If pair passes, generate original control, collect, present for actual human review; fast only after acceptance.
- [ ] Record all actual results/unverified work and owned shutdown, no new matrix or unknown repost.

Actual fullpair passed; control preparation failed under8GiB commit cap, separate tokenizer-only proof664tokens. Task2 blocked; no diffusion/video/fast. Service exit0/portclosed and observer stopped. Next joint T5 memory/context design before another pair run.
