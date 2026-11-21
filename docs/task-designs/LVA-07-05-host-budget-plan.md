# LVA-07-05 Host Budget Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans inline. Do not regenerate old video or run unrelated suites.

**Goal:** Execute the already-authorized two-sample experiment using local capacity and no total deadline.
**Architecture:** Change the fixed experiment admission minima to14GiB RAM/21GiB VRAM; preserve private8GiB/RSS24GiB/allocator20GiB and one owner. GPU controller accepts --max-seconds0 only with explicit unlimited authorization; CPU retains its180s cap. Seal a successor comparison before first POST because source/contract identity changes; preserve prior unstarted root and link actual user approvals.
**Tech Stack:** Python, pytest, existing isolated Comfy runtime.
**Spec:** docs/task-designs/LVA-07-05-design.md; user “按照本机可以提供的来吧” and “时间可以不限制”.

## Global Constraints

No downloads, new dependencies, model substitution, quality reduction, unknown repost, production resume, or fast before actual control acceptance. Max2 samples768x432/93frames/16fps. Runtime memory hard caps retained. Preserve original comparison and its no-execution evidence. No repeated large payload hashes beyond one actual admission.

## Review Focus

GPU0 deadline requires explicit unlimited authorization; CPU0 forbidden. Smaller capacity than minimum refuses. Allocation/RSS/private hard caps unchanged. Source/contract changes require fresh profile/comparison identity. Original admission/trial IDs never reposted.

### Task1: Host capacity and controller deadline

- [x] Add tests proving minima14/21 and preserved hard limits, GPU0 with explicit unlimited authorization, CPU0 and finite-authorization0 refusal, elapsed deadline semantics.
- [x] Run targeted tests and observe RED.
- [x] Implement minimal deadline helper and contract minima; use dynamic error text.
- [x] Run wrapper tests GREEN; review changes and deliver only touched task files to source workspace.

### Task2: Actual experiment

- [x] Record user resource amendment and fresh comparison provenance/authorization; initialize new -02 root with unchanged original fixture.
- [x] Observe actual capacity; resolve BLOCKED -> READY -> IN_PROGRESS with evidence.
- [x] Start one owned GPU controller with --max-seconds0, then original-only pair admission.
- [ ] If admission passes generate control, collect and present for actual human review. Only after acceptance generate fast.
- [ ] Record actual failure/unknown/technical/human outcome and owned exit, without claiming unperformed work.

Task2 stopped at actual UnsupportedPatch(head.head.weight), original-ID GET confirmed, owned exit0/portclosed. Video acceptance work remains blocked, not complete. Details: LVA-07-results.json and LVA-07-05-handoff.md.
