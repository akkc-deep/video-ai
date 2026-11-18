# LVA-07-02 Mixed Delta Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Fix the reproduced unmerged static-delta omission in an independent Wrapper source copy, with strict admission and CPU pair atomicity.

**Architecture:** Keep real upstream CustomLinear dynamic LoRA math. Add a CPU-bounded private pair preparation module applying scalar-strength additive static deltas once; route all entry validation through preflight. Ship the added module and a replayable diff for original source files. Existing non-atomic node entry points reject unsupported mixed deltas rather than silently accepting them.

**Tech Stack:** Existing Python3.13.14 / torch2.14.1+cpu environment, stdlib unittest, local git snapshot branch. No installation/downloads.

**Spec:** `docs/task-designs/LVA-07-02-fix-design.md`; current user-authorized amendment in `LVA-07-02-design.md`.

## Global Constraints

- Independent source copy: `E:/VideoAI/scratch/benchmarks/LVA-07-02-fix/wrapper`; original 18 snapshots remain unchanged. This is a partial audited snapshot, not a complete upstream checkout.
- No production changes, GPU, Comfy service, model downloads, new dependency installs, remote fork/push or old-run writes.
- Constant finite scalar strengths only. Exact shapes and finite CPU data. Fail closed on unknown payloads, schedule, aliasing, unsupported quantization/dtypes or unresolved targets.
- Preflight happens once before private mutation; no checks added to each frame/step. Deep CPU clones only under a bounded memory budget; do not claim 14B residency feasible.
- Static updates once; repeated application to an already prepared model is rejected. Remove/reconfigure from independent original bases, not floating-point subtraction.
- Full model/payload/registration/merged/GPU compatibility requires separate evidence.

## Review Focus

- Prepared objects must not expose or mutate original owners on errors or removal.
- Patch payload validation must reject unsupported alpha/DoRA/offset/scheduling instead of silently dropping information.
- Normalization collisions must fail before dictionary overwrite.
- Scaled linear math must apply delta in the dequantized domain, including the input-scaling optimization branch.
- Entry-point guards must prevent mixed patches bypassing the private pair API.

### Task 1: Independent snapshot and RED tests

**Files:** `tests/experiments/test_lva07_wrapper_fix.py`; source-copy metadata/ledger in scratch.

**Interfaces:** Tests import complete real `custom_linear` and new `lva07_mixed_delta` modules from `LVA07_FIX_SOURCE`, using a namespace for path resolution only.

- [x] Copy/hash-check the 18 reviewed source snapshots, initialize local git and commit the baseline. Preserve all original sources.
- [x] Add literal numerical tests for block/head modulation, bias forward, norm and unchanged weight diff; use float32/float64 and the original three expected values.
- [x] Add ordinary LoRA alpha/rank tests, High-only/Low-only plans, unknown/shape/dtype/nonfinite/schedule/collision/alias rejection, once-only/removal and injected low-side failure tests.
- [x] Add source-normalizer collision tests invoking its complete AST-extracted function (explicitly not full loader import).
- [x] Run the opt-in CPU unittest module before implementation; observe missing pair API and scaled-delta failure. Save log and status.

### Task 2: Minimal implementation and GREEN

**Files:** `patches/wanvideo-wrapper/lva07_mixed_delta.py`, `patches/wanvideo-wrapper/mixed-delta.patch`; independent `wrapper/custom_linear.py`, `wrapper/nodes_model_loading.py`.

**Interfaces:** `prepare_lora_pair(high, low, high_patches, low_patches, strengths=(1.0,1.0)) -> PreparedLoraPair`; `apply_static_deltas(private_model, static_plan)`; `remove_lora_pair(prepared) -> (high, low)`; `UnsupportedPatch(ValueError)`.

- [x] Implement exact target/payload classification and validation, retaining full patch tuples and rejecting unsupported branches before clone/mutation.
- [x] Deep-copy CPU originals/bases, apply static delta once on private copies, install original CustomLinear dynamic patches, and return only after both sides succeed.
- [x] Implement repeat rejection and independent-base removal; unsupported ordinary adapters or FP8 formats remain explicit errors.
- [x] Correct scale-versus-delta order in CustomLinear only when dynamic patches are active; retain no-LoRA scaling behavior. Validate supported scalar scale against independent arithmetic.
- [x] Reject normalized-key overwrite and unsafe mixed node paths before existing mutation. Keep guards out of per-step/frame paths.
- [x] Run the same tests; expected GREEN for supported cases and strict rejection for the rest. Run the original upstream baseline only if changed evidence requires it; prior RED remains preserved.

### Task 3: Reproducible patch, review and report

**Files:** `scripts/prepare_lva07_wrapper_fix.py`, `scripts/verify_lva07_wrapper_fix.py`, `docs/task-designs/LVA-07-02-fix-results.json/.md`, current board/results/handoff.

- [x] Generate a patch from baseline local source commit; ship the added module separately with hashes. Builder checks original identities and applies the patch without remote code fetching.
- [x] Verify replay into another independent directory and targeted CPU tests; run repository checks appropriate to the experiment tooling, reporting pre-existing failures rather than changing unrelated work.
- [x] Obtain one fresh read-only code review and fix Important/Critical findings with targeted RED/GREEN tests. Record review/rulings in the ledger.
- [x] Commit the independent source repair locally and record full commit/file identities. Do not commit/push unrelated project working-tree changes.
- [x] Report repaired CPU behavior and all unsupported/full-model limits; update task status only to the extent the actual full acceptance supports. No GPU claim or automatic successor preparation.
