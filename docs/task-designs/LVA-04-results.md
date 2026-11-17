# LVA-04 results

**COMPLETED as an experimental rejection. The pinned fast candidate is incompatible with the designed strict native adapter. Fast is not validated or adopted; default quality is unchanged.**

## Actual outcome

The user authorized the fixed download/GPU manifest. Both official LoRAs were downloaded, fully checked and promoted without overwriting original models. Four quality low-motion native clips completed (cold1/warm3). The first fast graph was accepted as `66cd1918-4276-4ee6-ac84-8d6235b70ba3`, then failed at `LVA04LoraPair` with `incompatible_lora: unsupported patch kind/key`. It never reached the sampler and produced no video. Both owned services exited normally (code 0, no timeout, finalized metrics). No retry, alternative engine, model merge, package install or old production resume occurred.

The selected official weights contain mixed deltas beyond ordinary rank64 linear LoRA:

| Weight | LoRA tensors | diff_b | diff | diff_m |
| --- | ---: | ---: | ---: | ---: |
| high | 810 | 447 | 202 | 41 |
| low | 974 | 531 | 244 | 0 |

These are bounded safetensors-header counts, not applied-patch counts. The strict first adapter rejects non-ordinary patch forms; the native loader also logged the 41 high diff_m keys as unloaded. High admission failed before returning a pair, so low runtime admission was not reached. This rejects this pinned recipe/adapter combination; it is not a universal claim about fast Wan support. Supporting mixed deltas requires a revised adapter design and real quality validation.

## Measurements

| Quality trial | Submit to output s | Technical s | Total s |
| --- | ---: | ---: | ---: |
| cold_1 | 474.792 | 4.440 | 479.232 |
| warm_1 | 466.628 | 3.975 | 470.604 |
| warm_2 | 466.526 | 3.937 | 470.463 |
| warm_3 | 466.665 | 3.933 | 470.598 |

All four preserve 93 generated/retained frames at 768x432/16fps, valid full PTS, pre-uint8 finite IMAGE checks and a single normal full RGB decode per encoded media. No suspect-black signal was found. Retained videos and tails match each other and the prior LVA-01 reference exactly; no new human acceptance was fabricated from this equality.

Warm total-wall P50: **470.598s**. Cold device-sampled peak: 22,034 MiB. Raw CPU node/model method intervals and device-wide samples remain available; they do not establish physical transfer counts or exclusive-process CUDA peaks.

The failed fast graph log reports **26.33s**, which is failure latency, never generation throughput. Fast actual sigma, applied-patch counts, frame/PTS, visual quality, continuity, usable-video cost and speedup are unavailable. Remaining warm/high/parent/child attempts stopped after incompatibility as the design requires; unused prepared roots contain no submissions. No child borrowed a quality parent or bypassed review.

## Decisions

| Factor | Result |
| --- | --- |
| distill | failed: pinned mixed-delta recipe rejected by current strict native adapter |
| sage | unsupported: sageattention absent; prerequisite candidate rejected |
| cache | rejected_unsupported: no verified native dual-expert implementation |
| compile | unsupported: Triton absent; no compile/residency claim |
| combination | rejected: no independently accepted accelerated factors |

Fast human quality is `not_evaluable_no_candidate_video`, not accepted or pending a nonexistent artifact. The task's experiment has a negative conclusion; a usable fast mode remains unvalidated.

## Verification and artifacts

- Final targeted suite: **79 passed in 5.00s**. Three Important independent-review identity findings were reproduced RED and fixed GREEN; no remaining Critical/Important or deferred Minor was recorded.
- Actual stopped-service recovery: all four quality completions reused and original failed fast ID preserved, **0 HTTP / 0 media producers**. Receipt `E:/VideoAI/scratch/benchmarks/LVA-04-real-recovery-receipt.json`.
- `docs/task-designs/LVA-04-gpu-results.json`: actual timings, identities, full media checks, finite checks, service outcomes and candidate failure.
- `docs/task-designs/LVA-04-native-rejection-evidence.json`: bounded header-only diagnosis of already pinned weights; no inference or repeat full-weight hash.
- `docs/task-designs/LVA-04-gpu-run-state.json`: final closed state and authorization.
- `docs/task-designs/LVA-04-completion.json`: outcome-level completion evidence.
- `docs/task-designs/LVA-04-review.md`: review and regression corrections.
- Offline simulation remains separate at `E:/VideoAI/scratch/benchmarks/LVA-04-offline-final-results.json`.

Manifest SHA256 remains `54ea929f38a033fb6960bf96857f75d1ee20047a8452a1e7b715ec550979b50d`. Environment: RTX 5090 D v2 / driver 610.88 / Python 3.13.14 / torch 2.14.1+cu130 / CUDA 13.0 / Comfy 0.44.0. Official weights total 1,374,118,048 bytes and are retained. Historical baseline base evidence held path/size/mtime stamps; current full SHA admission cannot retroactively prove historical full-content equality.

Original quality workflow SHA: `5f3768f6e83bf6be21287457c7c15e811d8f6949b7b5c5ac5460c267c8f98666`. Original mapping SHA: `a3ea755e0fa5fb5413151ee9a551467b6fc0359e2a56a48312a9830316abb437`. Old requests and production settings are unchanged. Native diagnostics are not whole-film throughput.
