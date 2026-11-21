# LVA-07-05 head full-delta adapter

## Goal

Resolve the actual head.head.weight admission refusal by applying its full additive delta without dropping it, changing the original model, or requantizing FP8 storage; then continue the already-authorized minimal experiment.

## Scope

User2026-11-20 “继续吧” follows the explicit head-compatibility next step. Keep fixed upstream files/repair/applicability policy and original six model/input identities. Keep14GiB RAM/21GiB free VRAM admission,8GiB private/24GiB RSS/20GiB allocator caps, no total deadline, max2 actual videos and real control acceptance before fast. Preserve previous failed groups/IDs. CPU proof first; no repeat old GPU matrix.

## Approach

Chosen approach: an experiment-only dynamic installation adapter. Head source metadata has BF16 full-delta[64,5120], FP8_E4M3 base plus scalar scale; no head rank adapters. Fixed CustomLinear.forward already computes effective W=(FP8->inputdtype)*scale+delta*strength before linear, with existing rounding and bias handling. Static dequantized merging was considered and rejected because it could change runtime dtype/rounding; changing fixed Wrapper/repair files was rejected to retain immutable upstream evidence.

New wan_wrapper_head.py interfaces: HEAD_KEY exact diffusion_model.head.head.weight; preflight_head(owner, parsed, parameters) validates only this exact full-diff entry, CPU/dense/finite exact shape, one entry, strengths1/1, offset/functionNone, target actual CustomLinear, nongguf, FP8_E4M3, computeFP16, finite positive scalar scale; other parsed targets use unchanged repair._preflight. Source and parser payload objects remain retained under the same trace/lease. Unsupported head payload or alternate head key rejects.

install_head(owner, patches) uses unchanged target.set_lora_diffs([diff_tuple],device=target.weight.device), set_lora_strengths([1]), step0; keeps original weight/scale unmodified and checks one installed slot. Admission calls fixed ordinary installation then this adapter, and existing probe_dynamic executes the real head forward with four independent effective coordinates. Include head in CertifiedPair.dynamic and witness; never mark it excluded/static or omit it.

head_reload_scope(owner,sampler_module) wraps only the sampler's imported set_lora_params alias for a fast owner carrying HEAD_KEY. The wrapper calls original first, then install_head for that exact transformer and patch dict. A finally restores the original alias. This is essential because original sampler installation skips head again after load_weights and offload may clear buffers. No forward hook, stepwise scan, hash or extra matrix arithmetic is added. Control with no head patch is unchanged and takes the no-op scope. Existing single-owner/worker lock covers the scope.

## Files

Create src/video_ai/experiments/wan_wrapper_head.py. Modify wan_wrapper_lora.py to split validated head from fixed ordinary preflight, include/install/probe it; modify wan_wrapper_nodes.py to wrap the actual sampler invocation in head_reload_scope. Add focused cases in tests/experiments/test_lva07_wrapper_runtime.py and new protocol scope tests if needed. Save original executed source for later failures; new source requires new sealed root E:/VideoAI/scratch/benchmarks/LVA-07-05-low-20261120-01 before first request.

## Tests

Run scripts/verify_lva07_wrapper_runtime.py with existing fixed Wrapper/Comfy and independent CPU interpreter/site into fresh scratch output. Required RED then GREEN: actual head FP8+scale+BF16diff forward uses delta, source unmoved; wrongshape/nonfinite/schedule/rankpayload rejects before static writes; fixed original setter demonstrably drops head; adapter restores it after original setter and after reload/meta, without accumulation or source mutation; scope restores after exception, refuses foreign transformer, control stays zero. Existing12 CPU tests remain passing. Run existing44 Wrapper protocol tests only for changed behavior, no unrelated whole-repo suite.

## Acceptance

CPU tests and scoped review demonstrate exact head delta installation plus reload/offload invariants and unchanged control. This resolves implementation blocker only; full actual pair/high+low witnesses still required before any video POST. New comparison/authorization binds existing real user messages and head adapter change. Run original-ID admission; unknown GET only; stop on new actual failure; then one control and actual human review before fast.

## Risks

Actual full pair may expose other issues; CPU fixture is not14B success. Global sampler alias must always restore and stay single-owner. Head original dtype/scale must remain unchanged; no silent fallback/patch omission. Existing14GiB floor may still fail on current available capacity; reobserve once before launch.
