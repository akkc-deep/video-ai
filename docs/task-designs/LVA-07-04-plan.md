# LVA-07-04 Isolated Wrapper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Complete the isolated Wrapper worker/workflow/recovery harness without real checkpoint loading, GPU sampling or production changes.

**Architecture:** Seal a shared comparison plus two exact mode profiles; use native text encoding and the existing Wrapper bridge; construct one unpatched owner at a time and apply a private small static overlay only for fast. Reuse the existing durable Comfy protocol and media validation primitives, with fresh owned-process attestation and fail-closed admission.

**Tech Stack:** Python3.12 orchestration/pytest, existing Python3.13 CPU torch fixture runtime and installed independent Wrapper runtime, Windows Jobs, local HTTP, FFmpeg.

**Spec:** `docs/task-designs/LVA-07-04-design.md`, machine values `LVA-07-04-contract.json`.

## Global Constraints

- Original user request to complete LVA-07-04 and repeated continue requests authorize the scoped reversible implementation; no repeated implementation consent. Exact installation and CPU service approvals already recorded; GPU/full checkpoint operations remain unauthorized here.
- Preserve all fixed upstream/repair/policy bytes, native workflows, production defaults, Jimeng files and old runs. No new dependencies/downloads.
- Control has zero LoRA; fast uses exact2959 applicable/290 excluded accounting and strengths1/1.
- One comparison root, two different sealed mode-profile hashes; control acceptance binds control profile and comparison, pair receipt fast profile/current epoch.
- 768x432/93frames/16fps; exact40/high15-low25 and4/high2-low2 arrays from contract; actual int timesteps and non-equivalence explicit.
- CPU fixture/probe4GiB private budget; new fixture disk512MiB. Future real-model limits are code guards, not operations to run now: available RAM26GiB/VRAM22GiB, private8GiB/RSS24GiB/GPU allocator20GiB.
- Tests are targeted and use fresh fixtures. Do not rerun old CPU payloads, old GPU runs or unrelated full repository suites.
- Work in `E:/VideoAI/scratch/benchmarks/LVA-07-04-implementation`, branch codex/lva07-04 from observed v2 HEAD75c45cbf; this does not switch/reset the user workspace. Source/run profiles bind their actual paths. Keep a durable progress ledger in task scratch.

## Review Focus

1. Control accidentally receives fast overlays; task2 tests zero control math and rejection of nonempty control patches.
2. Different mode hashes prevent or loosen control/fast acceptance; task1 tests exact common comparison and fixed allowed recipe differences.
3. Read-only mapped static tensors alias canonical source/cached overlays through reload/offload; task2 tests source immutability, two reloads and meta restoration with real pinned function bodies.
4. Lost response or stale owner produces a second generation; task1/3 tests original-only recovery and live owner epoch with conflict/unknown rejection.
5. Completed media/proof after restart reuses an invalid cache or decodes twice; task3/4 tests process-proof expiry and single RGB decode for frame/black/last-frame data.

---

### Task 1: Profiles, graphs and durable recovery

**Files:** create `src/video_ai/experiments/wan_wrapper_backend.py`, template/mapping/provenance files, `tests/unit/test_wan_wrapper_backend.py`, `tests/integration/test_wan_wrapper_recovery.py`.

**Interfaces:** consumes existing `Artifact/digest/write_once`, `baseline_api().ExperimentClient`, fixed contract. Produces `WrapperProfile`, `freeze_comparison(root,profiles,fixture)`, `build_graph(profile,fixture)`, `WrapperExperimentClient.submit/recover/collect`, immutable comparison/request bindings and exact graph roles.

- [x] Write RED tests for profile/graph drift, exact control/fast arrays, zero control LoRA, mode hashes different/common comparison same, rejecting illegal common or recipe changes, invalid acceptance/unknown/duplicate receipt, completed0POST/0producer and parent binding.
- [x] Run targeted new tests; expected missing behavior/import FAIL, preserve RED log.
- [x] Implement pure stdlib profile/graph/client layer; no torch imports or real networking in fixture construction. Native durable protocol delegate has injected transport only in offline fixtures; real CLI rejects fixture profiles.
- [x] Run target tests plus existing fast protocol baseline; expected PASS, stable original IDs and no native workflow diff.
- [x] Commit only task files locally in isolated branch; ledger result and any ruling.

### Task 2: Bounded private expert preparation

**Files:** create `wan_wrapper_lora.py`, `tests/experiments/test_lva07_wrapper_runtime.py`, `scripts/verify_lva07_wrapper_runtime.py`.

**Interfaces:** consumes task1 profile/contract and real pinned normalizer/mapper/parser/CustomLinear/repair. Produces `admit_pair(factory,fast_profile,leases)`, `prepare_control_expert`, `prepare_expert`, `release_expert`, private overlays, immutable witnesses and fail-closed full-model factory path.

- [x] Write RED unittest fixtures: actual read-only source/static parameters; bias/norm/modulation/patch_embedding target conversions; rank/alpha/scale true forward; malformed/collision/NaN/unknown inputs; sequential high/low, low failure/no pair, owner leak, no whole-model deepcopy, repeated/removal behavior.
- [x] Use existing CPU interpreter/site with actual pinned function bodies; RED must be observed before helper code. No original LoRA/base payload reads.
- [x] Implement source classification/runtime schema checks, private static clones, dynamic-only patches, cached prepared SD, bounded real factory and sequential pair publication. Control goes through a separate clean owner path with no certified fast data.
- [x] Real pinned `load_weights` reload twice and offload/meta restore must preserve exactly one static update and dynamic scale semantics; owner disposal permits only one expert. GREEN CPU fixture output must distinguish fixture/full-model evidence.
- [x] Commit task files and record source identities/results; do not change existing patch artifacts or raise old helper limits.

### Task 3: Composite nodes, media and owned worker

**Files:** create `wan_wrapper_nodes.py`, `wan_wrapper_media.py`, `scripts/observe_wan_wrapper_comfy.py`, unit media/worker integration tests.

**Interfaces:** consumes task1 sealed graph/request and task2 owner/certificates. Produces three node registrations (`LVA07Prepare`, `LVA07Sampler`, `LVA07SaveVideo`), current CPU HTTP capability attestation, original-ID admission routes gated off in CPU mode, owned start/stop and media receipts.

- [x] RED tests assert dependency ordering and separate T5 lifetime, finite frames before uint8, overlay reload path, original first LATENT, actual forwards/recipe agreement, blocked CPU admission/generation, wrong owner/port/source failures and deadline cleanup.
- [x] Implement serial prepare/native-T5 bridge, isolated node registration and worker mode/Job limits. No actual checkpoint load in CPU tests/probes; real GPU mode remains gated by explicit LVA-07-05 authorization and resource checks.
- [x] Implement raw RGB encoder and one RGB inspection shared for black/PTS/last PNG. Generate one93-frame synthetic fixture; fresh validation exactly once, completed path no producer/HTTP, restore proof expiry leads to one fresh validation, corruption rejects.
- [x] Run targeted tests and one bounded actual CPU owned worker GET for used delegate/three new class schemas; save actual PID/start/port/exit and error notes, not GPU quality claims.
- [x] Commit task files and ledger source/observed capability distinctions.

### Task 4: CLI, evidence and integration

**Files:** create `scripts/benchmark_wan_wrapper.py`, result JSON/Markdown, update scoped design/board/manifest/handoff as actual outcomes permit.

**Interfaces:** consumes tasks1–3. CLI init/graph/offline-selftest/probe-cpu/recover only in this task; future admit-pair/run paths refuse absent real GPU authorization. Profiles and graphs seal both modes in one comparison root.

- [x] RED tests for CLI non-submission, incorrect profile kind, empty/unknown recovery, ready graph identity, no accidental install/download or production path writes.
- [x] Implement CLI and actual JSON/Markdown reporting. Preserve negative/unverified facts and current memory availability; no fabricated full model counts or speedups.
- [x] Run the spec's targeted suites/CPU runner and meaningful existing fast-profile/media/recovery neighbors once; expected PASS,0 actual generation POST/GPU/checkpoint payload.
- [x] Request one fresh final code review as required by executing-plans/requesting-code-review, with spec/plan/base/head and the five Review Focus lines. Fix important findings with reproducing tests; do not re-dispatch repeated reviews without new unresolved concerns.
- [x] Verify final code scope and map every acceptance condition to evidence. Copy only new task files back to the shared user workspace without replacing any existing user files; path-bound smoke only if it resolves integration concerns.
- [x] Record LVA-07-04 completion only if all outcome-level CPU/offline/worker/media requirements hold. Prepare LVA-07-05 design/handoff from actual code and fixed inputs; never start its GPU work or invent readiness/authorization.

## Execution Method

Execute inline in this session, with a single fresh final reviewer. Existing user completion/continue authorization covers this routine method choice; no additional permission loop. Local commits are limited to this isolated feature branch and no push/merge is requested. Record all progress/rulings at `E:/VideoAI/scratch/benchmarks/LVA-07-04-progress.md`.
