# LVA-04 Implementation Plan

> Execute the established LVA-04 design inline using executing-plans and TDD.

**Goal:** Isolated, strongly bound native Wan fast experiment; real GPU and human quality remain explicit evidence gates.
**Spec:** `docs/task-designs/LVA-04-design.md`

## Constraints and rulings

- Original quality workflow/mapping, old requests, production settings and existing work remain untouched.
- Ruling: work in the current v1 checkout because required predecessor implementations and evidence are uncommitted here; a clean worktree would omit the actual dependencies. Cost: review only new LVA-04 paths plus the named board edit.
- Ruling: the detailed linked design is already implementation-ready and the user explicitly requested completion; no repeat design approval. Download/GPU authorization remains a concrete final gate as specified.
- No installs/downloads/GPU before that gate; no fabricated speed or quality results. No excessive repeated media inspection.

## Tasks

1. [x] Profile/artifact/freeze tests RED, then immutable profile and strict backend selection GREEN; create isolated workflow/mapping/provenance. Preserve original SHA.
   Interfaces: load_profile(mode='quality', *, factor, assets, capabilities), freeze_profile(root, profile), verify_profile(root, expected_digest).
2. [x] Native node tests RED, then atomic rank64/shape/key admission, sigma assertion and finite IMAGE guard GREEN. Import Comfy/torch only in the owned worker.
3. [x] Recovery tests RED, then FastExperimentClient and fixture/parent bindings GREEN. Reuse existing ExperimentClient durable protocol; completed reuse validates files before returning without producer/POST.
4. [x] Bounded launcher and benchmark offline/prepare/run commands, capability refusals and exact downloadable manifest. Run design's targeted tests, offline command and review.
5. [x] Write results and board evidence honestly; request only the prepared download/GPU gate. No COMPLETED status until real experiment outcomes and human observations exist.

## Review focus

Swapped experts; same-size content replacement; forged/changed service binding; lost POST response; child borrowing another profile's parent; incomplete/ignored LoRA patches; sigma mismatch; unsupported acceleration silently falling back.

## Progress

- Start: user `完成任务LVA-04`, 2026-11-16. READY -> IN_PROGRESS. Pre-flight: profile identity is consumed by nodes, launcher, request and recovery; one canonical digest shared throughout. Source graph/request use the predecessor canonical_digest, while intent uses the existing ExperimentClient digest.
- All implementation/offline steps delivered. Final targeted suite 79 passed/4.90s; final offline fake-HTTP report passed. Full evidence in LVA-04-results.json/.md.
- Independent whole-change reviewer found three Important identity gaps; all reproduced RED then fixed GREEN with suite passing. Phase failure shutdown also fixed. No deferred minors. See LVA-04-review.md for declined-to-judge rulings: real GPU/remote download remain unverified, pre-existing production defects outside scope; cost is those outcomes remain pending, never certified by offline tests.
- Environment manifest initially exposed a wrong version-module filename and valid empty Python sources; source inventory now validates before base admission. Duplicate parent_child fixture routing corrected before authorization using a small-source-only manifest revision. No old quality file or existing runtime implementation was edited.
- Historical authorization-gate snapshot: at offline delivery, real GPU and human evidence were pending; no completion was claimed then.

- Closure: fixed downloads admitted after explicit user authorization; quality cold1/warm3 all 93 frames passed. Fast original graph rejected mixed delta formats before sampling; zero fast videos and no quality/speed adoption claim. Stop branch followed without retry or alternate engine. Both services exit0/finalized. Actual completed/failed-ID recovery 0HTTP/0producer; fresh targeted suite79passed/5.00s. Results/completion record negative experiment, board COMPLETED.
- Successor: only after completion, Order5 LVA-05 detailed design linked, next-task handoff written/linked, NOT_STARTED -> READY. No LVA-05 implementation/GPU started.
