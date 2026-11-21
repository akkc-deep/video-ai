# Production Wan fast implementation plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ordinary new/resumed production tasks default to the tested Wrapper fast recipe.

**Architecture:** Add a scoped production mode, per-request template selection and a dedicated owned Wrapper worker. Reuse the validated numerical implementation and ordinary durable Comfy transactions; keep frozen historical options and original submitted graphs intact.

**Tech Stack:** Python 3.12, PowerShell, ComfyUI/WanVideoWrapper, existing pytest.

**Spec:** `docs/superpowers/specs/2026-11-21-production-wan-fast-design.md`

## Global constraints

- No experiment replay, GPU inference, paid image requests, email or publication during implementation.
- Preserve original-ID GET recovery; never resubmit unknown work.
- Do not overvalidate video generation.
- Preserve untracked LVA-07-06 completion evidence.

## Review focus

- Mixed completed native / unsent fast clips in old runs.
- Dynamic prompts longer than the benchmark, arbitrary seeds and short 4n+1 clips.
- Worker restart and admission/conditioning lifetime.
- Native services still used by image/upscale stages.
- Unsupported whole-scene/quality requests fail before POST.

## Task 1: Selection and production dispatch

- [x] Write failing tests in `tests/unit/test_production_wan_fast.py` for mode scope, graph/template/parameter selection, original graph preservation and CLI default/overrides.
- [x] Run the tests; confirm missing feature failures.
- [x] Add `runtime/wan_production.py`; wire `production.py`, `cli.py`, scene records/submission and legacy production visuals. Freeze actual recipes in ordinary request graphs without editing historical options.
- [x] Run focused selection/recovery tests.

## Task 2: Owned Wrapper production worker

- [x] Add failing worker/launch tests, including per-clip conditioning and admission reuse.
- [x] Implement `runtime/wan_production_worker.py` and `scripts/serve_wan_production.py`; add stage-only service spec selection. Reuse existing sampler/repairs and leases.
- [x] Verify CPU node registration and real object_info; no checkpoint loads or inference.
- [x] Run relevant existing wrapper and production transaction tests.

## Task 3: Entry documentation and review

- [x] Update startup help/docs and PowerShell forwarding for optional `--wan-mode`.
- [x] Obtain fresh whole-change review and fix material findings.
- [x] Run final focused regression checks and report exact behavior/limits.

## Execution ledger

Implemented in the ordinary `v2` working tree, which was clean except the prior untracked LVA-07-06 completion receipt. That receipt was preserved. User authorization covers integrating the production entry; no commit, push, publication, GPU video generation or paid external request was performed.

Ruling: old frozen configuration/options remain byte-identical, while unsent per-clip requests use the current production mode. Existing graphs and proven inherited clips determine their own recipes. This satisfies the user's later requirement that old tasks also use fast without replaying submitted work.

Ruling: default applies to the ordinary production entry; standalone historical component APIs retain their existing default, and recognize persisted fast/control requests. Experimental authorization/profiles/source remain unchanged.

The design reviewer identified inherited-clip and independent-reader compatibility, output node108, strict old parameter validators, and missing original history limitations. These are handled. The whole-change reviewer identified migration packaging/relocation and host commit/RSS checks; fixed and focused rereview found no new Important/Critical issue. An additional red/green test fixed ambiguous legacy adapter template caching when changing Wrapper recipes. New claims also bind the originally frozen image bytes rather than newly hashing potentially changed input as authoritative.

Verification:

- Combined unit/transaction/Wrapper/PowerShell/real CPU boot/synthetic mixed-media run: **140 passed, 1 deselected, 124.34s**.
- After adding legacy-template-switch and early missing-runtime regressions, final focused suite: **140 passed, 1 deselected, 14.02s**. The two integration flows already passed against the unchanged worker/scene implementation, giving **142 distinct passing checks** in total.
- `git diff --check`: passed. Real installed CLI help exposes `--wan-mode {fast,control,native}`, default fast. Probe worker exited; no remaining `serve_wan_production.py` process.
- The deselected pre-existing `test_default_health_classifies_unavailable_service_for_owned_start` fixture fails before service startup because its real E:/VideoAI tools lie outside the test session's isolated runtime. This was observed separately; product path policy was preserved. Two cleanup-test mock rows were updated to include their now-required parameter mapping.

Limits: no new GPU end-to-end claim; earlier accepted fast numerical/video evidence remains the basis for the recipe. Wrapper uses native16 768×432 and 4n+1 frame budgets up to93. Unsupported explicit quality/long-scene requests refuse before POST and can use explicit native. Installations missing the repaired runtime get an early dependency error; new migration exports include the exact runtime, without experimental output groups.
