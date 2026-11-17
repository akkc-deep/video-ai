# LVA-07-02：Wrapper Mixed Delta CPU 负向复现与最小修复设计

## Goal

在真实固定版本 Wrapper 的真实转换/加载/patch 函数上，用小型 CPU 模型确认 LVA-04 两组 LightX2V LoRA 中 mixed delta 的实际映射、遗漏和数值语义；区分“源码静态风险”与“CPU 实际行为”，为是否维护独立 Wrapper fork 提供证据。

本任务先做**最小负向复现和修复设计**，不实现完整后端、不启动 Comfy、不做 GPU/视频生成。当前审查结论为 stop candidate preparation，因此本任务不是自动进入 fast 生成；若必须安装依赖，先准备最小隔离环境清单并等待用户明确授权。

## Inputs / frozen identity

- Wrapper repo: https://github.com/kijai/ComfyUI-WanVideoWrapper
- Wrapper commit: `a7439db30bed0c5b5fa437d77ae8a7bb220dfd00`（1.4.8）；不得使用浮动 main。若改 commit，建立新审查和新任务身份。
- Comfy source commit: `2c75dc1b379a59e0880619d029607af5169a62ef`；本机源码文件SHA以 LVA-07-01 JSON 为准。
- LVA-07-01 evidence: `docs/task-designs/LVA-07-environment-review.md/.json`。
- LoRA identity only from LVA-04 frozen research; do not redownload or rehash the 1.37GB files for this CPU task:
  - High: 634645944 bytes, SHA256 `887c3bdeb74e83859c920438e16ca31f39ab18ce189abc5f0e36f8348c5bbb19`
  - Low: 739472104 bytes, SHA256 `8833bd4fd7c8eabebf0bc8ee5cfaf47f4f310ce116928a02c1adf8941dd4b0f1`
- Existing base header audit is bounded only; it does not prove full model loading or identical High/Low payloads.

## Scope

1. Verify the exact functions from the pinned Wrapper source using an isolated CPU-only environment or a minimal import harness. Do not execute arbitrary latest remote source.
2. Reproduce the identified cases with small synthetic modules whose names/parameter structure match the actual Wrapper Wan block/head:
   - ordinary linear LoRA;
   - `.diff` on linear weight and non-linear/norm weight;
   - `.diff_b` on linear bias;
   - `.diff_m` mapped to block modulation `[1,6,dim]` and head modulation `[1,2,dim]`;
   - both experts independently and atomically as a pair.
3. Exercise the actual Wrapper key standardization, key mapping, converter, loader and merge/unmerge application functions wherever importable. A reimplementation of the logic in a test helper is not evidence that Wrapper supports it.
4. Compare expected tensor values against actual model parameter/buffer values after application. Include strength, alpha/rank, dtype conversion, FP8 scale behavior, merge/unmerge and repeated application/removal where relevant.
5. Produce a minimal patch design only after the failing path is reproduced. Do not modify the Wrapper checkout or production code in this task.
6. If the real functions cannot be imported because dependencies are missing, do not silently replace them with mocks and claim CPU validation. Deliver an exact isolated CPU environment plan and mark actual execution blocked pending approval.

## Explicit questions to answer

- Does `standardize_lora_key_format` preserve unique identities, or can two source keys collide after normalization and overwrite each other?
- For every tensor in both fixed LoRAs, what is the normalized key, resolved model target, target parameter/buffer shape and dtype, patch kind, consumed status, applied status and reason?
- Does unmerged `CustomLinear` apply only matrix weight deltas? Are bias, norm and modulation deltas omitted?
- Does merged `utils.apply_lora` skip modules with both own parameters and child modules? What exact block/head modulation targets are skipped?
- Does `load_lora_for_models_mod` warn and continue when keys are not applied, and can callers mistake this for success?
- Do layer filters, img filtering, low_mem_load, merge_loras and FP8 fast matmul alter or silently drop any input tensor?
- Can High and Low be applied atomically, such that a partial success never produces a usable pair?
- Are repeated application, removal and clone semantics mathematically correct and free from double application?

## CPU test design (RED first)

Create small deterministic tensors with hand-computable values and use float64 or float32 reference math.

For a standard rank-r LoRA:
`W_out = W_base + strength * alpha/r * (up @ down)`.

For additive `.diff` and `.diff_b`, test the exact intended target and broadcast/shape semantics against the source format specification; do not assume they share ordinary LoRA scaling unless the converter/source establishes it.

For `.diff_m`, first establish the source format's intended modulation operation from the pinned LightX2V conversion/reference implementation and actual tensor shapes. Do not invent a formula from the suffix. If source semantics cannot be established, report `semantics_unknown` and stop rather than patching by guess.

Test matrix:
- key conversion and collision detection;
- key mapping for every tensor category;
- consumed vs applied accounting (input tensor count alone is insufficient);
- merge path parameter mutation and exact expected output;
- unmerge path forward output and exact expected output;
- bias/norm/block modulation/head modulation;
- FP8 scaled base with merge and unmerge paths, including scale tensors;
- High-only, Low-only, High+Low atomic admission;
- unknown key, duplicate normalized key, shape mismatch, dtype mismatch, nonfinite value, missing dependency and injected exception;
- no partial model mutation if either expert fails.

Each test must first fail against the pinned unmodified Wrapper implementation where a defect is expected (RED), then pass only for the specific minimal patch. Preserve an untouched copy/hash of the upstream source for comparison. The tests must call actual Wrapper functions/classes, not a handwritten duplicate implementation.

## Dependency and environment gate

LVA-07-01 found missing declared dependencies including accelerate, diffusers, peft, ftfy, gguf, pyloudnorm, protobuf and opencv-python. It also found mandatory import paths, so do not assume optional usage means safe omission.

Before any install:
1. identify the smallest set of modules required to import the exact converter/loader/patch functions;
2. resolve and pin exact versions compatible with Windows AMD64 / Python 3.13.14 and the required CPU-only torch path;
3. create an isolated CPU venv outside the production Comfy embedded Python and outside its custom_nodes;
4. provide exact install commands, wheel sources/hashes, disk use and any torch wheel implications;
5. run resolver dry-run only if it does not mutate the environment; do not download/install until separately approved.

If the Wrapper import graph requires CUDA-only custom ops, importing full nodes is not necessary if the exact underlying converter/patch modules can be exercised without them; but do not replace the functions under test. Any adapter/shim must be thin, documented and preserve exact implementation bytes. If not feasible, report blocked.

## Deliverables

- `docs/task-designs/LVA-07-02-results.json`: per tensor/category source key, normalized key, target, shape/dtype, consumed/applied/rejection reason, exact code path, expected/actual CPU values and error tolerance; separate evidence levels.
- `docs/task-designs/LVA-07-02-results.md`: conclusion and known limitations.
- `docs/task-designs/LVA-07-02-fix-design.md`: minimal patch proposal with affected functions, invariants, migration/rebase strategy, upstream fork strategy, test list and failure modes. Create only if actual reproduction supports a fix.
- Optional isolated CPU test harness and tests, only after exact dependency/runtime is authorized.
- Update LVA-07-02 task state and board with actual results. Do not create a successor handoff if the gate fails.

## Acceptance

1. All examined inputs in both fixed LoRAs have a complete per-tensor accounting trail; no tensor disappears silently.
2. Real pinned Wrapper functions are exercised on CPU. Mock-only or static-only findings remain explicitly unverified.
3. Every supported delta type matches an independently derived expected mathematical result; unsupported/unknown semantics fail closed.
4. High/Low are atomic: failure in either expert leaves both original model copies unchanged and no pair is returned.
5. Merged/unmerged paths either agree within justified numerical tolerance where semantically equivalent or document exact supported differences.
6. FP8 scale behavior is explicit; no false claim of compatibility from metadata/header-only checks.
7. No production code, production Comfy, custom_nodes, original LoRA files, workflows, old tasks or media are modified.
8. No GPU, service, video POST, model download or production recovery occurs.
9. If dependencies prevent actual execution, report BLOCKED and deliver a concrete isolated CPU environment/authorization request, not a false pass.

## Stop conditions

- Unknown `.diff_m` semantics: stop; do not invent broadcast or parameter update.
- Any unconsumed/unapplied tensor, key collision, partial expert, silent warning, mutation before pair success or FP8 scale mismatch: stop and design explicit fix.
- Required install touches production Python/Comfy or upgrades torch/CUDA: reject; require isolated runtime.
- Source revision drift: stop and re-review under a new identity.
- No CPU numerical proof: do not proceed to LVA-07-03 as “compatible” and do not authorize Wrapper GPU/video generation.
