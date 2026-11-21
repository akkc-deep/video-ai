# LVA-07-05 T5 memory and original long-context repair

## Goal

Complete original664-token positive and512-token negative native T5 preparation without overlapping retained Wan certificates, and preserve all tokens through Wrapper sampling.

## Scope

User “继续修复吧” authorizes this repair and continued minimal experiment; original models/image/prompt/seeds/93frames768x432/16fps and human control acceptance remain. Previous failed control stays terminal and archived. No actual Wan sampling occurred before its failure; count it as a failed preparation POST, never hide it. New repaired group gets one control and only after actual acceptance one fast; no model swap/download/quality reduction.

## Approach

Use an explicit prepare-text phase on the same owned GPU worker BEFORE full pair admission. Native CLIPLoader/CLIPTextEncode/unchanged WanVideoTextEmbedBridge produce CPU tensors once; release encoder in finally on both success and failure, before VAE or any Wan owner. Store exact tensors to text/embeddings.safetensors and a receipt binding comparison, control profile, original fixture/prompt digest, T5 descriptor and current epoch. Keep a private in-process cache, do not auto-trust/reload disk across restarts. A prepare-text original UUID intent uses POST once, then GET only on unknown, matching admission recovery.

Acquire original six-model deny-write leases and full hashes once in prepare-text; admission reuses that live protected window (verify metadata only), not a second full read. Admission refuses before model construction unless text is ready in this epoch. Real text validation succeeds before another full pair run; existing prior pair remains historical, never copied as a live certificate. No mathematical head changes or repeated old GPU matrix.

Raise future worker private commit hard cap8->12GiB (12884901888), justified by measured8GiB-20KiB peak while host had16GiB free. Keep RAM14GiB/freeVRAM21GiB admission, RSS24GiB/GPU allocator20GiB/single owner; CPU probe remains4GiB/180s. Initial startup/text-prep floor14/21 stays; after bound text-ready, admission phase uses4GiB available RAM workspace/20GiB free VRAM. Previous actual T5 initialized driver retained enough VRAM to leave20.89GiB free, so reapplying launch21GiB incorrectly refuses its own initialized context. Phase gate is only reachable after current text binding and keeps all allocation/RSS caps. Controller reads the cap from the sealed contract instead of hardcoding8. Same source/contract change requires new root E:/VideoAI/scratch/benchmarks/LVA-07-05-low-20261120-02.

Validate original native conditioning batch1, tokens1..664, dim4096, finite; existing unscheduled metadata rules remain. Real original cache must have664 positive and512 negative, checked before accepting prepare-text. No token truncation. During each existing observed transformer.forward call set text_len=max(512, actual current context rows) for one context only, bounded664. Actual call may use context keyword or positional index2; no full tensor/hash check per forward. Record lengths and restore property in finally. This preserves negative512 padding independently of positive664; do not pad both to664.

LVA07Prepare reads only same-epoch prepared tensors and verifies exact prompt digest; no lazy T5 fallback after pair. Stage text preparation belongs to group setup; cache binding is separate from video sampling. Fresh context without preparation rejects. Text failure stops before full pair and before video POST.

## Files

Create src/video_ai/experiments/wan_wrapper_text.py for native encoder lifecycle, validation, receipt/cache output and dynamic context length. Modify wan_wrapper_nodes.py for durable prepare-text, existing cache use, lease reuse, token-length forward hook. Modify wan_wrapper_backend.py and scripts/benchmark_wan_wrapper.py for original-ID prepare-text transport. Modify scripts/observe_wan_wrapper_comfy.py for route and contract-driven cap; update contract and explicit text_path setting. Add focused text/protocol tests and update former inline-prepare lifecycle test to assert two-phase ordering.

## Tests

Focused pytest RED before code:664 accepted665 rejected, actual padding preserves all664 rows and resets negative512; no cached text means no VAE or admission; native encoder released before VAE and on encode failure; original prompt binding, no cross-epoch cache; lost prepare-text POST response yields only GET same UUID; new private cap12 while other caps unchanged and controller uses it. Then existing Wrapper protocol tests only when affected. Do not rerun15 old head CPU fixtures or unrelated production matrix because head/math files unchanged.

Real verification: new isolated root, same user authorization plus repair note, owned GPU --max-seconds0; prepare-text only first. Check native664/512 F32 shapes, finite tensor output, bound receipt and native encoder released. If it fails stop before full pair; if it passes, one current-epoch actual pair then control. No unknown repost or old-root restart.

## Acceptance

Text tests and scoped review pass; actual native original text preparation succeeds under12GiB and preserves664/512; no T5 model stays with pair/VAE. Then actual control/fast and human quality remain required for LVA-07-05 completion; successful text alone is not completed video experiment.

## Risks

Transient CPU commit/RSS and VAE/Wan GPU peaks may still fail; bound observations and stop. Model text_len has only fixed text padding uses for this non-audio/non-NAG profile. Whole upstream files and head code remain pinned. A future standalone proof-cache reuse across epochs is outside this repair; do not treat old epoch pair as current.
