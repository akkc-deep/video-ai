# LVA-02 Implementation Plan

> Execute inline with superpowers:executing-plans; spec: `docs/task-designs/LVA-02-design.md`.

**Goal:** Reuse complete scene validation proofs within synchronous protected guards.

**Architecture:** A bounded context-local helper owns a fresh native read pass; clip/media/composition guards use it without changing transactions or persistent formats.

## Constraints

Preserve all socket, ownership, model/tool, parent, promotion and durable recovery boundaries. Never pin new inputs for memoization. Weak platforms and revision/temporal origins retain strict validation. Keep existing user changes and production paused.

## Tasks

1. [x] RED/GREEN: `test_scene_validation_pass.py` tests same-lease reuse, fresh flush, strict propagation, identity/binding changes, thread/window invalidation, complete dependency replay and capture limits; implement `scene_validation_pass`, `validate_artifact_once`, `verify_inventory_once`.
2. [x] RED/GREEN: `test_scene_validation_boundaries.py` tests clip/media guards and composition synchronous scope. Wire strict validator extraction, inventory helpers and narrow decorators.
3. [x] Add real-media offline benchmark and recovery tests. Run design's targeted suites and four-pair normal/recovery, protected/weak benchmarks; collect unprofiled wall separately from LocalVideoMetrics diagnostics.
4. [x] Review change, address material findings, record results and ledger decisions, complete LVA-02 and prepare LVA-03 design/handoff from established evidence.

## Review Focus

- A caller capture must never be repaired after overflow.
- Every independent guard must flush inventories before returning.
- Mutable auxiliary dependencies must remain freshly verified on hits.
- Store/frozen/implementation rebinding cannot silently establish a new baseline.
- Strict mode must propagate through later protection windows and nested calls.

## Execution ledger

- Start: user requested “完成任务- LVA-02”; board READY and complete design/handoff read.
- Ruling: Work in the supplied checkout because required LVA-01 inputs and existing cold-admission changes are uncommitted there. Limit edits to LVA-02 files; no clean/reset/stash or broad staging. Cost if wrong: shared-checkout interference; inspect focused diffs at completion.
- Ruling: Existing detailed design already fixes the implementation choices; user's completion request authorizes execution without another design approval round. No GPU/network/production resume is required.
- Task 1 RED: 13 new tests failed because scene_validation_pass was absent; GREEN: 13 passed. Task 2 RED: all four guard wiring cases failed; GREEN: 17 total passed. Expanded identity/budget/thread/capture coverage reached 30, then 32 new cases.
- Task 1 follow-up RED/GREEN: a FileNotFoundError on a memo hit did not invalidate the memo; added rejection/invalidation and preserved the original exception. Inventory refusal wording and proof-deadline exception tests also failed first, then passed.
- Verification: design's unit/transaction/native-proof command: 212 passed in 7.56s. Media performance: 22 passed, 1 known process_identity fixture deselected in 4.95s.
- Ruling: Production frame planning explicitly rejects 128x72 (config.py / scene_clip_continuation.py permit fast 768x432 or quality 1280x720). Use genuine 768x432 production fixtures rather than patch that contract for the benchmark. Cost if wrong: larger benchmark cost; measured dimensions/frames are disclosed.
- Ruling: Original integration fixtures referenced real E:/VideoAI tools outside their sandbox; repair only test-tool placement and inject isolated configs in the affected media recovery tests. Six malformed-preparation cases still fail before LVA-02 in unchanged verification.scene_input_protection; three additional continuity tests use paths rejected by unchanged _scene_continuity_io.local. Keep these failures named, do not relax production policy or claim a green whole-repository suite. Cost if wrong: those unrelated baseline defects remain.
- Independent review: no remaining confirmed runtime safety defect; Important evidence gap in PTS/direct producer counts, Minor asymmetric direct-glob scan counter. Read existing probes/receipts to add actual PTS and receipt-derived producer evidence; do not label inferred receipt counts as direct invocation measurements. Direct glob comparison remains explicitly unsupported in the original production benchmark samples.
- Ruling: Four actual production-fixture pairs show normal strict 18.908746s versus candidate 20.756011s (+9.77%), actual SHA/decode unchanged. Follow the design's no-benefit branch: retain strict production guards; candidate_scene_validation() enables only offline experimental wiring. Amplified protected 4-audit reuse still reduces strict128→32; do not substitute it for the production result. Cost if wrong: potentially useful optimization remains experimental until better evidence exists; users avoid a measured regression.
- Final gating RED/GREEN: default and explicit candidate guard tests fail before the experiment gate exists; after adding the call-time gate, 214 targeted tests pass in 7.79s. New real-media/upscale recovery suite: 5 passed in 721.74s; includes completed-prefix reuse, transient frame-copy recovery, generated-receipt interruption and same-size/mtime tamper rejection. No repeat GPU run or broad repository validation.
- Deferred minor: original production benchmark's direct-glob inventory count is incomplete. The report marks it incomparable; separate same-rule inventory samples demonstrate4→2 including exit, weak4→4. New producer spy is available for future runs; existing data's direct invocation count remains null rather than rerunning generation for bookkeeping.
- Final recovery run: 64 passed, 6 failed, 6 deselected in1649.92s. Five legacy model-root fixtures fail before LVA-02; one existing output-reclaim cleanup issue occurs after intentionally changed sources. Named with exact reasons in LVA-02-results.json/.md; do not broaden this task into those production modules or call the suite green.
- Ruling: Close LVA-02 on implemented experiment, targeted proof/transaction tests, real-media/prefix recovery and the measured strict-default decision. Keep unrelated legacy fixture/public-invalid-run/publication cleanup defects disclosed. Cost if wrong: those pre-existing paths remain unresolved; no default candidate is promoted onto them.

- Completion: LVA-02 board COMPLETED with exact results/limitations; LVA-03 completed design and next-task handoff linked, status READY, implementation not started. No commit, merge, push or production resume.
